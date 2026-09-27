#!/bin/bash
#
# Visualization Vignettes
#
# make_offline_bundle.sh -- collect the suite's Python dependencies as wheels
#
# Several of our machines have no network, so the Python environment has to be
# built somewhere connected and carried over. A virtual environment cannot be
# carried: it records absolute paths in bin/activate and in every console
# script's shebang, so one built at /home/you/env does not work at
# /scratch/you/env. It half-works, which is worse than failing outright.
#
# Wheels can be carried. This writes them next to the repository; on the
# offline machine you make a fresh venv and install from the directory with
# --no-index.
#
#   ./make_offline_bundle.sh
#   ./make_offline_bundle.sh --python-version 3.10
#
# Then, on the offline machine:
#
#   python3 -m venv $SCRATCH/testing_paraview_env
#   source $SCRATCH/testing_paraview_env/bin/activate
#   pip install --no-index --find-links=<bundle>/wheelhouse \
#       pandas numpy pillow matplotlib psutil
#
# See Testing/OFFLINE_SETUP.md for the data and the generated fixtures, which
# have their own rules.
#
# Author: James Kress, <james@jameskress.com>
#
set -euo pipefail

# pillow and psutil are not optional. Without pillow no image comparison runs
# at all; without psutil the peak-memory and CPU figures are omitted rather
# than guessed, so every run is missing a gate.
PACKAGES=(pandas numpy pillow matplotlib psutil)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="${HERE}/../offline_bundle"
WHEELHOUSE="${BUNDLE}/wheelhouse"

PYTHON_VERSION=""
PLATFORM="manylinux2014_x86_64"

while [ $# -gt 0 ]; do
    case "$1" in
        --python-version) PYTHON_VERSION="$2"; shift 2 ;;
        --platform)       PLATFORM="$2";       shift 2 ;;
        --output)         BUNDLE="$2"; WHEELHOUSE="$2/wheelhouse"; shift 2 ;;
        -h|--help)
            sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "${WHEELHOUSE}"
# Resolve away the "Testing/.." so every path printed below, and the one in
# INSTALL.txt, is the one someone would actually type.
BUNDLE="$(cd "${BUNDLE}" && pwd)"
WHEELHOUSE="${BUNDLE}/wheelhouse"

# The wheels have to match the interpreter that will run test_suite.py, which
# is whatever python3 built the venv. It is NOT ParaView's or VisIt's bundled
# Python: the vignettes run inside those and import nothing but the standard
# library, by design. So the trap is a login node whose default python3 is
# ancient: Shaheen's login5 is 3.6.15, which silently yields pandas 1.1.5 and
# matplotlib 3.3.4 from 2020 rather than anything current.
RUNNING_MAJOR="$(python3 -c 'import sys; print(sys.version_info[0])')"
RUNNING_MINOR="$(python3 -c 'import sys; print(sys.version_info[1])')"
if [ -z "${PYTHON_VERSION}" ] && [ "${RUNNING_MAJOR}" -eq 3 ] && [ "${RUNNING_MINOR}" -lt 9 ]; then
    cat >&2 <<EOF
Refusing to build a wheelhouse with $(python3 --version 2>&1).

That is old enough that pip resolves to 2020-era pandas and matplotlib, and
you would not find out until something behaved oddly on the offline machine.

Load a newer Python first and re-run:

    module avail python
    module load python/<newer>

Or, if the offline machine's interpreter really is this old, say so
explicitly and this will build for it:

    $0 --python-version ${RUNNING_MAJOR}.${RUNNING_MINOR}
EOF
    exit 2
fi

echo "Collecting wheels for: ${PACKAGES[*]}"
if [ -n "${PYTHON_VERSION}" ]; then
    # Cross-building for a different interpreter needs binary-only wheels:
    # pip cannot build a source distribution for a Python it is not running.
    echo "Target: Python ${PYTHON_VERSION} on ${PLATFORM}"
    python3 -m pip download -d "${WHEELHOUSE}" \
        --only-binary=:all: \
        --python-version "${PYTHON_VERSION}" \
        --platform "${PLATFORM}" \
        "${PACKAGES[@]}"
else
    echo "Target: this interpreter, $(python3 --version 2>&1)"
    echo "Pass --python-version if the offline machine differs."
    python3 -m pip download -d "${WHEELHOUSE}" "${PACKAGES[@]}"
fi

cat > "${BUNDLE}/INSTALL.txt" <<EOF
Built $(date -u +%Y-%m-%dT%H:%M:%SZ) by $(python3 --version 2>&1)
Wheels target: ${PYTHON_VERSION:-the interpreter above}

These wheels must match the python3 that creates the venv below. That is a
plain Python, not ParaView's or VisIt's: the harness (test_suite.py) imports
pandas, numpy, PIL, matplotlib and psutil, while the vignettes run inside
pvbatch or the VisIt CLI and import only the standard library. Load whatever
modern python module the machine has before creating the venv, and use the
same one for both suites.

    module load python/<version>     # if the default python3 is old
    python3 -m venv \$SCRATCH/testing_paraview_env
    source \$SCRATCH/testing_paraview_env/bin/activate
    pip install --no-index --find-links=${WHEELHOUSE} \\
        ${PACKAGES[*]}
    python -c "import pandas, numpy, PIL, matplotlib, psutil; print('deps ok')"

Repeat with testing_visit_env for the VisIt suite. The same wheels serve both,
provided both venvs are built from the same python3.
EOF

echo
echo "Wheels : $(find "${WHEELHOUSE}" -name '*.whl' | wc -l)"
# du -s on the directory reported 9.5K for 40 MB of wheels on Shaheen's
# scratch filesystem. Summing the files themselves is not filesystem-dependent.
echo "Size   : $(find "${WHEELHOUSE}" -name '*.whl' -exec du -ch {} + 2>/dev/null | tail -1 | cut -f1)"
echo "Bundle : ${BUNDLE}"
echo
echo "Copy that directory to the offline machine and follow INSTALL.txt."
