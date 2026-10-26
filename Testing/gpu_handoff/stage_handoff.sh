#!/bin/bash
# Assemble the folder an admin copies to the air-gapped GPU system (see README.md here).
#   bash stage_handoff.sh /scratch/$USER/vv_gpu_handoff [source clone]
# Run on Shaheen, from a connected clone that has data/fetchData.sh already run.
set -e
OUT=${1:?target folder}; SRC=${2:-$(cd "$(dirname "$0")/../.." && pwd)}
WHEELS_FROM=${WHEELS_FROM:-$SRC/offline_bundle}        # wheelhouse_<arch>_py3.x and pv_numpy_<arch>_py3.x dirs, built on a connected machine
BUNDLE_FILE=${BUNDLE_FILE:-}                             # a git bundle made elsewhere (e.g. the workstation); default: made from $SRC
mkdir -p "$OUT"
echo "source clone: $SRC  ->  $OUT"
if [ -n "$BUNDLE_FILE" ]; then cp "$BUNDLE_FILE" "$OUT/vignettes.bundle"; else git -C "$SRC" bundle create "$OUT/vignettes.bundle" --all; fi
rm -rf "$OUT/Visualization_Vignettes"
git clone -q "$OUT/vignettes.bundle" "$OUT/Visualization_Vignettes" && git -C "$OUT/Visualization_Vignettes" checkout -q master
mkdir -p "$OUT/data_large"
for f in cyclone-chapala-2015-11-02_00-00-00-mb cyclone-chapala-2015-11-02_00-00-00-mb.vtm currentRainfall.silo; do
    [ -e "$SRC/data/$f" ] && cp -r "$SRC/data/$f" "$OUT/data_large/" || echo "WARNING: $SRC/data/$f missing (run data/fetchData.sh first)"
done
for d in "$WHEELS_FROM"/wheelhouse_* "$WHEELS_FROM"/pv_numpy_*; do [ -d "$d" ] && cp -r "$d" "$OUT/"; done
cp "$(dirname "$0")/README.md" "$OUT/README.md"      # from this kit, not from $SRC (which may predate it)
echo "== contents:"; du -sh "$OUT"/* | sed 's#'"$OUT"'/##'
echo "== bundle:"; git bundle verify "$OUT/vignettes.bundle" 2>&1 | tail -1
