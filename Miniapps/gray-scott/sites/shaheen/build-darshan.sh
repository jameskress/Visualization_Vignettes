#!/bin/bash
# Build Darshan 3.4.7 for --telemetry (sites/shaheen/README.md, Telemetry):
# the runtime with the miniapp's Cray modules, preloaded into the Gray-Scott
# jobs and logging to $DARSHAN_LOG_DIR_PATH with the Slurm job ID, and the
# utilities for darshan-parser. Usage: build-darshan.sh <software dir>
# Installs to darshan-3.4.7-gcc<major>-install, named for the compiler in
# MODULES.sh, so a rebuild with a newer compiler never overwrites an install
# that earlier telemetry ran with (the GCC 12.3 one is darshan-3.4.7-install).
set -e
S=${1:?usage: build-darshan.sh <software dir>}
mkdir -p "$S"
S=$(cd "$S" && pwd)  # absolute, so the later cd's do not change its meaning
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=/dev/null
source "$HERE/MODULES.sh"
cd "$S"
[ -d darshan-3.4.7 ] || git clone --depth 1 --branch darshan-3.4.7 https://github.com/darshan-hpc/darshan.git darshan-3.4.7
SRC=$S/darshan-3.4.7
GCC_MAJOR=$(gcc -dumpversion | cut -d. -f1)
P=$S/darshan-3.4.7-gcc$GCC_MAJOR-install
B=$S/darshan-3.4.7-gcc$GCC_MAJOR-build
if [ -e "$P" ]; then
    echo "$P exists; not overwriting an install earlier runs may have used." >&2
    exit 1
fi
(cd "$SRC" && ./prepare.sh)
mkdir -p "$B/runtime" "$B/util"
cd "$B/runtime"
"$SRC/darshan-runtime/configure" --prefix="$P" CC=cc \
    --with-log-path-by-env=DARSHAN_LOG_DIR_PATH --with-jobid-env=SLURM_JOB_ID \
    --enable-lustre-mod --disable-hdf5-mod
# Separate commands, so set -e stops the script if either fails.
make -j 16
make install
cd "$B/util"
"$SRC/darshan-util/configure" --prefix="$P" CC=gcc
make -j 16
make install
echo "Darshan installed in $P (generate_experiments.py --darshan-prefix $P)"
