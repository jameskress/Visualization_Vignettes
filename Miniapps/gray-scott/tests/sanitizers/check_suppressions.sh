#!/bin/bash
# Check that lsan.supp does not hide leaks from our own code (#13): build
# mpi_leak_probe.c with ASan, run it under the same settings as
# run_sanitized.sh, and expect a report from each of its leaking functions.
#   tests/sanitizers/check_suppressions.sh [work dir]
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${1:-$(mktemp -d)}
mkdir -p "$WORK"
mpicc -fsanitize=address -fno-omit-frame-pointer -g -O0 "$HERE/mpi_leak_probe.c" -o "$WORK/mpi_leak_probe"
cc -shared -fPIC -o "$WORK/dlclose_noop.so" "$HERE/dlclose_noop.c"
export ASAN_OPTIONS=detect_leaks=1:verify_asan_link_order=0:fast_unwind_on_malloc=0
export LSAN_OPTIONS=suppressions=$HERE/lsan.supp:print_suppressions=0
LD_PRELOAD="$WORK/dlclose_noop.so" "$WORK/mpi_leak_probe" > "$WORK/probe.log" 2>&1 || true
status=0
for f in leak_datatype leak_info leak_mpi_buffer leak_heap; do
    if grep -q "in $f " "$WORK/probe.log"; then
        echo "reported: $f"
    else
        echo "HIDDEN:   $f (lsan.supp is too broad; see $WORK/probe.log)"
        status=1
    fi
done
[ $status -eq 0 ] && echo "PASSED" || echo "FAILED"
exit $status
