#!/bin/bash
# Run the Gray-Scott sanitizer build (host-cpu-asan preset) on N ranks (#13).
#   tests/sanitizers/run_sanitized.sh <build dir> <ranks> [settings file]
# Exits 0 and prints nothing from the sanitizers on a clean run.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=${1:?build dir, e.g. build/my-host-asan}; RANKS=${2:-1}
SETTINGS=${3:-$HERE/../../configs/miniapp-settings/settings-none.json}
SHIM=$BUILD/dlclose_noop.so
[ -f "$SHIM" ] || cc -shared -fPIC -o "$SHIM" "$HERE/dlclose_noop.c"
# fast_unwind_on_malloc=0: the fast unwinder stops inside libc, which hides the
#   Open MPI caller of small strdup leaks and defeats the suppressions.
# verify_asan_link_order=0: the dlclose shim is preloaded ahead of the ASan runtime.
export ASAN_OPTIONS=detect_leaks=1:halt_on_error=1:verify_asan_link_order=0:fast_unwind_on_malloc=0
export UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1
export LSAN_OPTIONS=suppressions=$HERE/lsan.supp:print_suppressions=0
exec mpirun --oversubscribe -np "$RANKS" -x LD_PRELOAD="$SHIM" -x ASAN_OPTIONS -x UBSAN_OPTIONS -x LSAN_OPTIONS \
    "$BUILD/gray-scott" --settings-file="$SETTINGS"
