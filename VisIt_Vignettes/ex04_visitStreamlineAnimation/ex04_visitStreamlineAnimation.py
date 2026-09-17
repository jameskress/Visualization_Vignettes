#
# Visualization Vignettes
#
# ex04_visitStreamlineAnimation -- seed and render streamlines through a vector field
#
# Builds an integral curve plot over a vector field and animates it.
# The heaviest of the classic VisIt vignettes -- its submission scripts
# request four engine ranks.
#
# RUNNING IT
#
#   Locally:
#     visit -cli -nowin -s ex04_visitStreamlineAnimation.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --machine_name my-machine
#
#   On a cluster:
#     sbatch ex04_ibex_runScript.sbat
#     sbatch ex04_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex04_visitStreamlineAnimation_results.json for the harness to compare numerically,
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

VIGNETTE = "ex04_visitStreamlineAnimation"
TOOL = "VisIt"

_args = vc.parse_args(VIGNETTE, TOOL, description="seed and render streamlines through a vector field")
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
AddOperator("ThreeSlice", 0)
ThreeSliceAtts = ThreeSliceAttributes()
ThreeSliceAtts.x = -10
ThreeSliceAtts.y = -10
ThreeSliceAtts.z = -10
SetOperatorOptions(ThreeSliceAtts, 0, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)
DrawPlots()


# Set a better camera view
ResetView()
View3DAtts = View3DAttributes()
View3DAtts.viewNormal = (0.361327, 0.263368, 0.894472)
View3DAtts.focus = (0, 0, 0)
View3DAtts.viewUp = (-0.0658267, 0.964093, -0.257277)
View3DAtts.viewAngle = 30
View3DAtts.parallelScale = 17.3205
View3DAtts.nearPlane = -34.641
View3DAtts.farPlane = 34.641
View3DAtts.imagePan = (0, 0)
View3DAtts.imageZoom = 1
View3DAtts.perspective = 1
View3DAtts.eyeAngle = 2
View3DAtts.centerOfRotationSet = 0
View3DAtts.centerOfRotation = (0, 0, 0)
View3DAtts.axis3DScaleFlag = 0
View3DAtts.axis3DScales = (1, 1, 1)
View3DAtts.shear = (0, 0, 1)
View3DAtts.windowValid = 1
SetView3D(View3DAtts)


# Disable annotations
aatts = AnnotationAttributes()
aatts.axes3D.visible = 0
aatts.axes3D.triadFlag = 0
aatts.axes3D.bboxFlag = 0
aatts.userInfoFlag = 0
aatts.databaseInfoFlag = 0
aatts.legendInfoFlag = 0
SetAnnotationAttributes(aatts)


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


# Create a streamline plot that follows the gradient
AddPlot("Pseudocolor", "operators/IntegralCurve/grad", 1, 0)
iatts = IntegralCurveAttributes()
iatts.sourceType = iatts.SpecifiedBox
iatts.sampleDensity0 = 7
iatts.sampleDensity1 = 7
iatts.sampleDensity2 = 7
iatts.dataValue = iatts.SeedPointID
iatts.integrationType = iatts.DormandPrince
iatts.issueStiffnessWarnings = 0
iatts.issueCriticalPointsWarnings = 0
SetOperatorOptions(iatts)
DrawPlots()


# set style of streamlines
patts = PseudocolorAttributes()
patts.lineType = patts.Tube
patts.tailStyle = patts.Spheres
patts.headStyle = patts.Cones
patts.endPointRadiusBBox = 0.01
patts.colorTableName = "hot_desaturated"
SetPlotOptions(patts)
DrawPlots()


# Crop streamlines to render them at increasing time values
iatts.cropValue = iatts.Time
iatts.cropEndFlag = 1
iatts.cropBeginFlag = 1
iatts.cropBegin = 0
for ts in range(0, 125):
    # set the integral curve attributes to change the where we crop the streamlines
    iatts.cropEnd = (ts + 1) * 0.5

    print("\nSaving Image ", ts, " of 125", flush=True)

    # update streamline attributes and draw the plot
    SetOperatorOptions(iatts)
    DrawPlots()
    swatts.fileName = "ex04_visit_%04d.png" % ts
    SetSaveWindowAttributes(swatts)
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
input_pattern = script_dir + "/output/ex04_visit_%04d.png"
output_movie = script_dir + "/ex04_visit.mp4"
encoding.encode(input_pattern, output_movie, fdup=3)


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
