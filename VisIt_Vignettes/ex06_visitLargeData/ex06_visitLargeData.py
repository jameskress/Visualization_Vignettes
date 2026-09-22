#
# Visualization Vignettes
#
# ex06_visitLargeData -- render a large dataset from a saved session
#
# Restores visitCyclone.session and renders the cyclone dataset.
#
# Requires the large dataset. Fetch it once with data/fetchData.sh.
#
# ex11_visitStateVerification is the vignette that tests session
# restoration itself, with assertions on what came back.
#
# RUNNING IT
#
#   Locally:
#     visit -cli -nowin -s ex06_visitLargeData.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --machine_name my-machine
#
#   On a cluster:
#     sbatch ex06_ibex_runScript.sbat
#     sbatch ex06_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex06_visitLargeData_results.json for the harness to compare numerically,
#   alongside the existing image and known_good_value.txt comparisons.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys

# import visit_utils, we will use it to help encode our movie
from visit_utils import *


# --------------------------------------------------------------------------
# Shared vignette scaffolding: CLI parsing, logging, structured results.
# Added without altering the pipeline below, so every committed baseline --
# images and known_good_value.txt alike -- keeps passing unchanged.
# --------------------------------------------------------------------------
def _bootstrap_common():
    """Put Testing/ on sys.path so vignette_common can be imported."""
    here = None
    try:
        here = os.path.abspath(os.path.dirname(__file__))
    except NameError:  # pragma: no cover
        here = None
    if not here and sys.argv and sys.argv[0]:
        here = os.path.abspath(os.path.dirname(sys.argv[0]))
    if not here:
        here = os.getcwd()
    testing = os.path.abspath(os.path.join(here, "..", "..", "Testing"))
    if testing not in sys.path:
        sys.path.insert(0, testing)
    return here


SCRIPT_DIR = _bootstrap_common()

import vignette_common as vc  # noqa: E402

VIGNETTE = "ex06_visitLargeData"
TOOL = "VisIt"

_args = vc.parse_args(
    VIGNETTE, TOOL, description="render a large dataset from a saved session"
)
ctx = vc.VignetteContext(VIGNETTE, TOOL, _args, script_dir=SCRIPT_DIR)

# This vignette writes its images through literal "<script-dir>/output" paths
# in the pipeline below. Rewriting all of them would mean touching hundreds of
# lines and re-blessing every baseline, so --output-dir is pinned instead and
# the caller is told rather than being silently ignored.
_fixed_output = os.path.join(SCRIPT_DIR, "output")
if os.path.abspath(ctx.output_dir) != _fixed_output:
    ctx.warn(
        "--output-dir is not honoured by this vignette; images are written "
        "to " + _fixed_output
    )
    ctx.output_dir = _fixed_output
os.makedirs(ctx.output_dir, exist_ok=True)
# --------------------------------------------------------------------------

print("Running VisIt example script: ", sys.argv[0], "\n")

#
# Get directory of this script
#
script_dir = os.path.abspath(os.path.dirname(__file__))
print("Running script from: ", script_dir)

# This is the one vignette whose inputs are not in the repository. The cyclone
# multiblock and the rainfall silo are 5.7 GB extracted, fetched once by
# data/fetchData.sh, and deliberately not committed. A clone that has not run
# that script, and CI, which has no business downloading it, are both expected
# states, so say so and stop.
#
# Before the compute engine is opened, deliberately: there is nothing to close
# down on this path, so the plain exit ctx.skip() uses is the right one.
for _required in (
    "cyclone-chapala-2015-11-02_00-00-00-mb.vtm",
    "currentRainfall.silo",
):
    if ctx.dataset(_required, required=False) is None:
        ctx.skip(
            "{0} is not present. This vignette needs the 5.7 GB extracted "
            "dataset; run data/fetchData.sh once to get it.".format(_required)
        )

# Launch the compute engine when a site was named on the command line.
#
# This replaces a positional-argument block that read sys.argv[4] to pick the
# machine. The Shaheen submission script passes five positional arguments, so
# argv[4] held the walltime string and neither branch ever matched:
# OpenComputeEngine was skipped and every Shaheen run executed serially on one
# core while reporting success. Named flags remove the whole class of bug.
vc.open_visit_engine(ctx, OpenComputeEngine)

# This scene is six overlapping Pseudocolor plots, two of them translucent
# (QICE and QRAIN carry a Constant opacity), so it is composited in an order
# that depends on how the data was partitioned. It renders the same at the
# same rank count and differently at a different one. The committed baseline
# is blessed at the rank count the .sbat scripts use; a run at any other rank
# count compares its numbers rather than its picture, and says so.
ctx.disable_image_gate_off_baseline_ranks("this cyclone scene")

dataFile = script_dir + "/visitCyclone.session"
# wrfFile = script_dir + "/../../data/cyclone-chapala-2015-11-02_00-00-00.vtr"
wrfFile = script_dir + "/../../data/cyclone-chapala-2015-11-02_00-00-00-mb.vtm"
rainFile = script_dir + "/../../data/currentRainfall.silo"
# The saved session colours its plots with VisIt colour tables that are not
# among the 18 compiled-in ones: plasma and Blues both ship as .ct files
# under the install's resources directory. The suite runs with -noconfig, so
# VisIt does not load that directory, and restoring the session without them
# silently falls back to defaults -- a washed-out grey frame that differs
# from the baseline in 99% of its pixels while raising nothing.
#
# Loading them first is what keeps -noconfig (no dependency on whose ~/.visit
# ran the suite) without giving up VisIt's own tables, which are the same on
# Shaheen and Ibex.
for _table in ("plasma", "Blues"):
    vc.ensure_color_table(
        ctx,
        _table,
        ColorTableNames,
        AddColorTable,
        ColorControlPointList,
        ColorControlPoint,
    )

RestoreSessionWithDifferentSources(dataFile, 0, (rainFile, wrfFile))
# RestoreSessionWithDifferentSources("/home/kressjm/data/cyclone.session", 0, ("localhost:/mnt/5d22bac5-b323-4e21-96a7-929039418079/cyclone-chapala-2015-11-02_00-00-00.vtr","localhost:/mnt/5d22bac5-b323-4e21-96a7-929039418079/currentRainfall.vtp"))
# RestoreSession(dataFile, 0)


print("\nWindow one plots")
SetActiveWindow(1)
ListPlots()
DrawPlots()

# set basic save options
swatts = SaveWindowAttributes()
# The 'family' option controls if visit automatically adds a frame number to
# the rendered files.
swatts.family = 0
# select PNG as the output file format
swatts.format = swatts.JPEG
swatts.resConstraint = (
    swatts.NoConstraint
)  # NoConstraint, EqualWidthHeight, ScreenProportions
# set the width of the output image
swatts.width = 2850
# set the height of the output image
swatts.height = 1750
# change where images are saved
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass
swatts.outputToCurrentDirectory = 0
swatts.outputDirectory = saveDir
swatts.fileName = "ex06_visit.png"
SetSaveWindowAttributes(swatts)
SaveWindow()

print("\nFinished VisIt example script\n")

# If on Windows wait for user input so that output does not disapear
if os.name == "nt":
    input("Press any key to close")


# --------------------------------------------------------------------------
# Structured results and a real exit code.
#
# The assertion is deliberately conservative -- it checks only that every
# image already blessed as a baseline was produced again. That cannot fail on
# a setup where this vignette works today, and it does catch the failure the
# old harness could not see at all: a vignette that silently stops emitting a
# frame.
#
# exit() is VisIt's, not Python's: it tears the viewer down before returning
# the status. Falling off the end of a VisIt CLI script leaves the client
# running and holding the compute engine's allocation open.
# --------------------------------------------------------------------------
ctx.assert_baselined_images_present()
_code = ctx.finish()
vc.finish_visit_session(
    ctx, _code, close_compute_engine=CloseComputeEngine, exit_func=exit
)
