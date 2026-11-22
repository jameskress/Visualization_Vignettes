#!/bin/bash
# Pack a ParaView install's lib/ for node-local staging
# (generate_experiments.py --catalyst-stage; sites/shaheen/README.md,
# "Catalyst node-local staging"). Usage: build-catalyst-stage.sh <install>
# where <install> holds lib/catalyst, e.g.
# software/paraview-6.2.1-gcc13-build/install. Writes, beside the build
# directory that holds <install>:
#   <build dir>-lib.tar         lib/ without debug files and static archives
#   <build dir>-lib.tar.sha256  its checksum, recorded in each run's settings
# Run once per ParaView install; an existing tarball is never overwritten,
# since runs have recorded its checksum.
set -e
I=${1:?usage: build-catalyst-stage.sh <ParaView install with lib/catalyst>}
I=$(cd "$I" && pwd)
[ -d "$I/lib/catalyst" ] || { echo "$I/lib/catalyst not found" >&2; exit 1; }
T=$(dirname "$I")-lib.tar
if [ -e "$T" ]; then
    echo "$T exists; not overwriting a tarball runs may have used." >&2
    exit 1
fi
# Many reader nodes read the tarball at once: stripe it over 16 OSTs so the
# reads spread (lfs is absent off Lustre; the tar then lands unstriped).
lfs setstripe -c 16 -S 4M "$T.tmp" 2>/dev/null || true
# .debug (separate debug info) and *.a (static archives) are never loaded at
# run time and more than double the size (2.4 GB with them, 1.1 GB without).
tar -C "$I" -cf "$T.tmp" --exclude=.debug --exclude='*.a' lib
(cd "$(dirname "$T")" && sha256sum "$(basename "$T.tmp")" | sed 's/\.tmp$//' > "$(basename "$T").sha256")
mv "$T.tmp" "$T"
echo "Wrote $T ($(du -h "$T" | cut -f1)) and $T.sha256:"
cat "$T.sha256"
