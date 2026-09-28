#!/usr/bin/env bash
#
# Run a command under a private Xvfb display.
#
# xvfb-run is deliberately not used. The CI image ships Xvfb but not xauth,
# and xvfb-run requires xauth unconditionally, so it aborts with
#
#     xvfb-run: error: xauth command not found
#
# before the command ever starts. The image also runs as an unprivileged uid,
# so apt-get install xauth is not available to fix it from inside the job.
# Driving Xvfb directly needs neither xauth nor root.
#
# usage: run_with_display.sh <command> [args...]
# env:   XVFB_SCREEN, default 1280x1280x24

set -u

if [ "$#" -lt 1 ]; then
    echo "usage: run_with_display.sh <command> [args...]" >&2
    exit 2
fi

: "${XVFB_SCREEN:=1280x1280x24}"

# Pick a display that is not already taken. A fresh container always lands on
# :99, but the loop keeps this usable on a developer workstation that has a
# real session on :0 and possibly other Xvfb instances running.
display_num=99
while [ -e "/tmp/.X${display_num}-lock" ] || [ -e "/tmp/.X11-unix/X${display_num}" ]; do
    display_num=$((display_num + 1))
    if [ "${display_num}" -gt 130 ]; then
        echo "run_with_display.sh: no free X display between :99 and :130" >&2
        exit 1
    fi
done

xvfb_log="$(mktemp -t xvfb_XXXXXX.log)"
Xvfb ":${display_num}" -screen 0 "${XVFB_SCREEN}" -nolisten tcp \
    >"${xvfb_log}" 2>&1 &
xvfb_pid=$!

# Xvfb writes its lock file before it starts accepting clients, so wait for
# the socket itself. 20 seconds is far longer than the ~0.3s it actually
# takes and still fails fast if the server dies on startup.
ready=0
for _ in $(seq 1 100); do
    if [ -e "/tmp/.X11-unix/X${display_num}" ]; then
        ready=1
        break
    fi
    if ! kill -0 "${xvfb_pid}" 2>/dev/null; then
        break
    fi
    sleep 0.2
done

if [ "${ready}" -ne 1 ]; then
    echo "run_with_display.sh: Xvfb never came up on :${display_num}" >&2
    cat "${xvfb_log}" >&2 || true
    rm -f "${xvfb_log}"
    kill "${xvfb_pid}" 2>/dev/null || true
    exit 1
fi

echo "run_with_display.sh: Xvfb running on :${display_num} (${XVFB_SCREEN})"

rc=0
DISPLAY=":${display_num}" "$@" || rc=$?

kill "${xvfb_pid}" 2>/dev/null || true
wait "${xvfb_pid}" 2>/dev/null || true

if [ "${rc}" -ne 0 ]; then
    echo "run_with_display.sh: command exited ${rc}; Xvfb log follows" >&2
    cat "${xvfb_log}" >&2 || true
fi
rm -f "${xvfb_log}"

exit "${rc}"
