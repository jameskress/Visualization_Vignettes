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

On the offline machine, with the visualization module already loaded so that
the right python3 is on PATH:

    python3 -m venv \$SCRATCH/testing_paraview_env
    source \$SCRATCH/testing_paraview_env/bin/activate
    pip install --no-index --find-links=\$(pwd)/wheelhouse \\
        ${PACKAGES[*]}
    python -c "import pandas, numpy, PIL, matplotlib, psutil; print('deps ok')"

Repeat with testing_visit_env for the VisIt suite. The wheels are the same.
EOF

echo
echo "Wheels : $(find "${WHEELHOUSE}" -name '*.whl' | wc -l)"
echo "Size   : $(du -sh "${WHEELHOUSE}" | cut -f1)"
echo "Bundle : ${BUNDLE}"
echo
echo "Copy that directory to the offline machine and follow INSTALL.txt."
