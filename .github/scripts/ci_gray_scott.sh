#!/bin/bash
#
# Visualization Vignettes -- Gray-Scott miniapp CI job body.
#
# Builds the miniapp from its host-cpu CMake preset and runs the numerical
# regression test (64^3, 500 steps, on 1, 2 and 4 ranks, plus the bitwise
# comparison across rank counts). See Miniapps/gray-scott/README.md, Testing.
#
# VTK comes from Debian's libvtk9-dev (built with MPI, which pulls in Open
# MPI). The ParaView binary tarball the other jobs use has no CMake config
# or headers, so it cannot be built against.
#
# It runs locally exactly as CI runs it:
#
#     docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
#         -t gray-scott-test-env -f .github/docker/Dockerfile.gray-scott.test .
#     docker run --rm --cpus=4 -v "$PWD":/workdir gray-scott-test-env \
#         bash /workdir/.github/scripts/ci_gray_scott.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}/Miniapps/gray-scott"

cmake --version | head -1
mpirun --version | head -1

# A stale build tree from an earlier run on this checkout would mask a
# preset change, so start clean.
rm -rf build/host-cpu

# --oversubscribe: the container is capped at 4 CPUs, and Open MPI counts
# slots from what it sees, which may be fewer than the 4 ranks the test uses.
cmake --preset host-cpu -DGS_TEST_MPIEXEC_PREFLAGS=--oversubscribe
cmake --build --preset host-cpu -j 4
ctest --test-dir build/host-cpu --output-on-failure
