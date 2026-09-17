#
# Visualization Vignettes
#
# ex01_visitScreenshot -- render a single screenshot
#
# The smallest useful VisIt vignette: open a database, add a plot, draw
# it, and save one window. Start here when you want the minimum viable
# VisIt CLI script.
#
# RUNNING IT
#
#   Locally:
#     visit -cli -nowin -s ex01_visitScreenshot.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --machine_name my-machine
#
#   On a cluster:
#     sbatch ex01_ibex_runScript.sbat
#     sbatch ex01_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex01_visitScreenshot_results.json for the harness to compare numerically,
#   alongside the existing image and known_good_value.txt comparisons.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys


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

VIGNETTE = "ex01_visitScreenshot"
TOOL = "VisIt"

_args = vc.parse_args(VIGNETTE, TOOL, description="render a single screenshot")
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

# Get directory of this script
script_dir = os.path.abspath(os.path.dirname(__file__))
print("Running script from: ", script_dir)

# Launch the compute engine when a site was named on the command line.
#
# This replaces a positional-argument block that read sys.argv[4] to pick the
# machine. The Shaheen submission script passes five positional arguments, so
# argv[4] held the walltime string and neither branch ever matched:
# OpenComputeEngine was skipped and every Shaheen run executed serially on one
# core while reporting success. Named flags remove the whole class of bug.
vc.open_visit_engine(ctx, OpenComputeEngine)


# Open file and add basic plot
dataFile = script_dir + "/../../data/noise.silo"
OpenDatabase("localhost:" + dataFile, 0)
AddPlot("Pseudocolor", "hardyglobal", 1, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)
DrawPlots()

# Change the annotations on the window
AnnotationAtts = AnnotationAttributes()
AnnotationAtts.userInfoFlag = 0
SetAnnotationAttributes(AnnotationAtts)

SaveWindowAtts = SaveWindowAttributes()
try:
    saveDir = script_dir + "/output"
    os.mkdir(saveDir)
except FileExistsError:
    pass
SaveWindowAtts.outputToCurrentDirectory = 0
SaveWindowAtts.outputDirectory = saveDir
SaveWindowAtts.fileName = "ex01_visit"
SaveWindowAtts.family = 0
SaveWindowAtts.format = (
    SaveWindowAtts.PNG
)  # BMP, CURVE, JPEG, OBJ, PNG, POSTSCRIPT, POVRAY, PPM, RGB, STL, TIFF, ULTRA, VTK, PLY, EXR
SaveWindowAtts.width = 2048
SaveWindowAtts.height = 2048
SaveWindowAtts.screenCapture = 0
SaveWindowAtts.saveTiled = 0
SaveWindowAtts.quality = 80
SaveWindowAtts.progressive = 0
SaveWindowAtts.binary = 0
SaveWindowAtts.stereo = 0
SaveWindowAtts.compression = SaveWindowAtts.NONE  # NONE, PackBits, Jpeg, Deflate, LZW
SaveWindowAtts.forceMerge = 0
SaveWindowAtts.resConstraint = (
    SaveWindowAtts.EqualWidthHeight
)  # NoConstraint, EqualWidthHeight, ScreenProportions
SetSaveWindowAttributes(SaveWindowAtts)
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
