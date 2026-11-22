#!/bin/bash
# Pack a ParaView install's lib/ for node-local staging
# (generate_experiments.py --catalyst-stage; sites/shaheen/README.md,
# "Catalyst node-local staging"). Usage: build-catalyst-stage.sh <install>
# where <install> holds lib/catalyst, e.g.
# software/paraview-6.2.1-gcc13-build/install. Writes, beside the build
# directory that holds <install>:
#   <build dir>-lib.tar         lib/ without debug files and static archives,
#                               its library paths made relative (below)
#   <build dir>-lib.tar.sha256  its checksum, recorded in each run's settings
# Run once per ParaView install; an existing tarball is never overwritten,
# since runs have recorded its checksum. Needs chrpath.
set -e
I=${1:?usage: build-catalyst-stage.sh <ParaView install with lib/catalyst>}
I=$(cd "$I" && pwd)
L=$I/lib
[ -d "$L/catalyst" ] || { echo "$L/catalyst not found" >&2; exit 1; }
command -v chrpath >/dev/null || { echo "chrpath not found" >&2; exit 1; }
T=$(dirname "$I")-lib.tar
if [ -e "$T" ]; then
    echo "$T exists; not overwriting a tarball runs may have used." >&2
    exit 1
fi
W=$(mktemp -d "$T.work.XXXXXX")
trap 'rm -rf "$W" "$T.tmp"' EXIT
# .debug (separate debug info) and *.a (static archives) are never loaded at
# run time and more than double the size (2.4 GB with them, 0.9 GB without).
tar -C "$I" -cf - --exclude=.debug --exclude='*.a' lib | tar -C "$W" -xf -
# Some superbuild libraries (LLVM, OpenVKL, OSPRay's modules, Embree, Mesa,
# libcatalyst) name the install's lib/ by its absolute path in their
# DT_RPATH, which the loader searches before LD_LIBRARY_PATH: from a staged
# copy they would still load their dependencies from Lustre. Point those
# paths at the copy itself, relative to each library ($ORIGIN). The new path
# is shorter, so chrpath can rewrite it in place.
n=0
while IFS= read -r -d '' f; do
    rp=$(chrpath -l "$f" 2>/dev/null | sed -n 's/^.*: R\(UN\)\{0,1\}PATH=//p')
    case "$rp" in *"$L"*) ;; *) continue ;; esac
    rel=$(realpath --relative-to="$(dirname "$f")" "$W/lib")
    if [ "$rel" = . ]; then o="\$ORIGIN"; else o="\$ORIGIN/$rel"; fi
    chrpath -r "${rp//$L/$o}" "$f" >/dev/null
    n=$((n + 1))
done < <(find "$W/lib" -type f -name '*.so*' -print0)
left=$(find "$W/lib" -type f -name '*.so*' -exec chrpath -l {} + 2>/dev/null | grep -c "$L" || true)
if [ "$left" != 0 ]; then
    echo "$left libraries still name $L in their library path" >&2
    exit 1
fi
echo "Made the library path relative in $n libraries."
# Many reader nodes read the tarball at once: stripe it over 16 OSTs so the
# reads spread (lfs is absent off Lustre; the tar then lands unstriped).
lfs setstripe -c 16 -S 4M "$T.tmp" 2>/dev/null || true
tar -C "$W" -cf "$T.tmp" lib
(cd "$(dirname "$T")" && sha256sum "$(basename "$T.tmp")" | sed 's/\.tmp$//' > "$(basename "$T").sha256")
mv "$T.tmp" "$T"
echo "Wrote $T ($(du -h "$T" | cut -f1)) and $T.sha256:"
cat "$T.sha256"
