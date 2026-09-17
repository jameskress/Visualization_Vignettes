#!/bin/bash
#
# Visualization Vignettes -- In Situ Vignettes
#
# is00_zeroCopyAdapter -- local developer run.
#
set -euo pipefail

BUILD_DIR="${BUILD_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/build-insitu}"
RANKS="${RANKS:-2}"
SIZE="${SIZE:-48}"
CYCLES="${CYCLES:-200}"

BIN="$BUILD_DIR/is00_zeroCopyAdapter/is00_zeroCopyAdapter"

if [ ! -x "$BIN" ]; then
  echo "error: $BIN not found. Configure and build first:" >&2
  echo "  cmake -S In_Situ_Vignettes -B $BUILD_DIR -DConduit_DIR=..." >&2
  echo "  cmake --build $BUILD_DIR -j" >&2
  exit 1
fi

echo "Running is00_zeroCopyAdapter on $RANKS rank(s), ${SIZE}^3 per rank, $CYCLES cycles"
mpiexec -n "$RANKS" "$BIN" --size="$SIZE" --cycles="$CYCLES"
