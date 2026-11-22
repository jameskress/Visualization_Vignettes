#!/bin/bash
# Build the Gray-Scott miniapp from this checkout with every backend the
# image provides, with the same options the image's own build uses
# (Dockerfile, "Build the user's application"). The build tree is under
# Miniapps/gray-scott/build/, which git ignores.
set -euo pipefail

src="$(cd "$(dirname "$0")/.." && pwd)/Miniapps/gray-scott"
build="$src/build/devcontainer"

cmake -S "$src" -B "$build" \
    -DENABLE_TIMERS=1 \
    -DBUILD_ANALYSIS_READER=ON \
    -DCMAKE_BUILD_TYPE=RELEASE \
    -DENABLE_ASCENT=ON \
    -DENABLE_CATALYST=ON \
    -DENABLE_ADIOS2=ON \
    -DENABLE_KOMBYNELITE=OFF
cmake --build "$build" -j"$(nproc)"

echo "Gray-Scott built: $build/gray-scott (see .devcontainer/README.md to run it)"
