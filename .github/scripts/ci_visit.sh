#!/bin/bash
#
# Visualization Vignettes -- VisIt CI job body.
#
# In a file rather than inline in the workflow, for the reason given at the
# top of ci_paraview.sh. Run it locally exactly as CI does:
#
#     docker run --rm -v "$PWD":/workdir -v "$CACHE_DIR":/data-cache:ro \
#         -e VISIT_TARBALL=visit-3.4.1.tar.gz visit-test-env \
#         bash /workdir/.github/scripts/ci_visit.sh
#
set -e

# Resolved before the job cds anywhere, so Scripts/ is found from Testing/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

VISIT_VERSION="${VISIT_VERSION:-3.4.1}"
VISIT_TARBALL="${VISIT_TARBALL:-visit-${VISIT_VERSION}.tar.gz}"

echo "Running VisIt Tests..."
python3 -m venv test-venv
# shellcheck disable=SC1091  # created on the line above
source test-venv/bin/activate
pip3 install pandas matplotlib pillow psutil scipy

echo "Extracting VisIt from cache..."
df -h /workdir .
cp "/data-cache/${VISIT_TARBALL}" visit.tar.gz

# Same guard as the ParaView job: a full disk truncates this copy and tar
# then exits 2 saying nothing about why.
bytes=$(stat -c%s visit.tar.gz)
echo "visit.tar.gz: ${bytes} bytes"
if [ "${bytes}" -lt 100000000 ]; then
    echo "FATAL: expected about 1 GB, got ${bytes} bytes." >&2
    echo "Either the runner ran out of disk or the host cache copy is bad." >&2
    df -h . >&2
    exit 1
fi

mkdir visit
tar xf visit.tar.gz -C visit --strip-components 1
VISIT_DIR="${PWD}/visit/bin"
export VISIT_DIR
export PATH="${VISIT_DIR}:${PATH}"
"${VISIT_DIR}/visit" -version

cd Testing
python3 prepare_machine.py --tool VisIt

# This job ran only ex00 for a long time, which meant it never compared a
# single image: ex00 is a query vignette and has no baseline PNGs.
#
# Left out: ex02 and ex04, the two long animations, 46 s and 82 s locally on
# a GPU and several times that under llvmpipe. Add "2 4" if the runner has
# the time. ex05 is left out for the same reason as in the ParaView job, its
# text annotation does not survive a change of font rasterizer.
#
# ex06 is in the list on purpose and costs about two seconds. Nothing here
# runs data/fetchData.sh and prepare_machine refuses to start that 4.3 GB
# download itself, so ex06 reports SKIPPED and that path gets exercised.
#
# No --non_gpu_machine, unlike the ParaView job. VisIt does not lean on the
# GPU the way ParaView does, and its ex08 demands a hardware context only
# when given --hw-accel, which the .sbat scripts add for a GPU queue and
# this does not. The flag would downgrade a real ex08 failure to a warning.
#
# ex09 and ex12 are absent because this image has no ParaView. They read
# data/topologies/ and the XML time series, and both of those are written by
# pvbatch (data/make_topology_datasets.py, data/make_time_series.py).
# prepare_machine skips those steps when pvbatch is not on the machine, so in
# this container the files never exist and both vignettes die with
# "Required dataset not found". That is the container, not the vignettes:
# they run for real on the workstation, Ibex and Shaheen, where ParaView is
# installed beside VisIt. Putting ParaView into this image to satisfy them
# would add an 866 MB download to a job whose whole point is to be quick.
python3 test_suite.py ../ --test_type VisIt \
    --visit_version "${VISIT_VERSION}" \
    --image-tolerance 0.0075 \
    --test_number 0 1 3 6 7 8 10

# ex11 restores a saved session and covers the display path. VisIt only
# warns without a display rather than failing, but warning and rendering
# something else is the case worth avoiding.
XVFB_SCREEN=1024x1024x24 \
    "${REPO_ROOT}/Scripts/run_with_display.sh" \
    python3 test_suite.py ../ --test_type VisIt \
        --visit_version "${VISIT_VERSION}" \
        --image-tolerance 0.0075 \
        --test_number 11

echo "VisIt tests complete"
