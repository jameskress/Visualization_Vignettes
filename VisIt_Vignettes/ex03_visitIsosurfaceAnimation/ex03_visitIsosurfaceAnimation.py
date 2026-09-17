#
# Visualization Vignettes
#
# ex03_visitIsosurfaceAnimation -- sweep an isosurface value and render each frame
#
# Applies an Isosurface operator to a Pseudocolor plot and steps the
# contour value, rendering one frame per step before encoding a movie.
#
# RUNNING IT
#
#   Locally:
#     visit -cli -nowin -s ex03_visitIsosurfaceAnimation.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --machine_name my-machine
#
#   On a cluster:
#     sbatch ex03_ibex_runScript.sbat
#     sbatch ex03_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex03_visitIsosurfaceAnimation_results.json for the harness to compare numerically,
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

VIGNETTE = "ex03_visitIsosurfaceAnimation"
TOOL = "VisIt"

_args = vc.parse_args(VIGNETTE, TOOL, description="sweep an isosurface value and render each frame")
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

# Create the isosurface
iso_atts = IsosurfaceAttributes()
iso_atts.contourMethod = iso_atts.Value
iso_atts.variable = "hardyglobal"
AddOperator("Isosurface")
DrawPlots()

# Change the annotations on the window
AnnotationAtts = AnnotationAttributes()
AnnotationAtts.userInfoFlag = 0
SetAnnotationAttributes(AnnotationAtts)

# set basic save options
swatts = SaveWindowAttributes()
# The 'family' option controls if visit automatically adds a frame number to
# the rendered files.
swatts.family = 0
# select PNG as the output file format
swatts.format = swatts.PNG
# set the width of the output image
swatts.width = 2048
# set the height of the output image
swatts.height = 1784
# change where images are saved
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass
swatts.outputToCurrentDirectory = 0
swatts.outputDirectory = saveDir


for i in range(35):
    iso_atts.contourValue = 2 + 0.1 * i
    SetOperatorOptions(iso_atts)
    swatts.fileName = "ex03_visit_%04d.png" % i
    SetSaveWindowAttributes(swatts)

    print("Saving Image ", i, " of 35")

    SaveWindow()


################
# use visit_utils.encoding to encode these images into a "mp4" movie
#
# The encoder looks for a printf style pattern in the input path to identify the frames of the movie.
# The frame numbers need to start at 0.
#
# The encoder selects a set of decent encoding settings based on the extension of the
# the output movie file (second argument). In this case we will create a "mp4" file.
#
# Other supported options include ".mpg", ".mov".
#   "mp4" is usually the best choice and plays on all most all platforms (Linux ,OSX, Windows).
#   "mpg" is lower quality, but should play on any platform.
#
# 'fdup' controls the number of times each frame is duplicated.
#  Duplicating the frames allows you to slow the pace of the movie to something reasonable.
#
################
input_pattern = script_dir + "/output/ex03_visit_%04d.png"
output_movie = script_dir + "/ex03_visit.mp4"
encoding.encode(input_pattern, output_movie, fdup=4)


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
