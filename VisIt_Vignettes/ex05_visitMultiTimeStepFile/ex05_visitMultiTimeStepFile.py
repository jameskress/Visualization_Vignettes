#
# Visualization Vignettes
#
# ex05_visitMultiTimeStepFile -- read a multi-timestep database, query it, and save each step
#
# Walks a 20-step time series, running the full query set and saving a
# window at every step.
#
# Its known_good_value.txt baseline pins the exact per-step query
# output for all twenty steps, so the print statements below must not
# be reworded and the query order must not change.
#
# RUNNING IT
#
#   Locally:
#     visit -cli -nowin -s ex05_visitMultiTimeStepFile.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --machine_name my-machine
#
#   On a cluster:
#     sbatch ex05_ibex_runScript.sbat
#     sbatch ex05_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex05_visitMultiTimeStepFile_results.json for the harness to compare numerically,
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

VIGNETTE = "ex05_visitMultiTimeStepFile"
TOOL = "VisIt"

_args = vc.parse_args(
    VIGNETTE,
    TOOL,
    description="read a multi-timestep database, query it, and save each step",
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

# Launch the compute engine when a site was named on the command line.
#
# This replaces a positional-argument block that read sys.argv[4] to pick the
# machine. The Shaheen submission script passes five positional arguments, so
# argv[4] held the walltime string and neither branch ever matched:
# OpenComputeEngine was skipped and every Shaheen run executed serially on one
# core while reporting success. Named flags remove the whole class of bug.
vc.open_visit_engine(ctx, OpenComputeEngine)

#
# Open file and add basic plot
#
# The XML series, not data/varying.visit. This vignette turns VisIt's time
# annotation on (annotationAtts.timeInfoFlag below), so the time is burned
# into every frame -- and over the legacy series that annotation reads "0"
# for all twenty frames on VisIt 3.4.2, because the legacy files carry no
# time for the reader to report. The XML series carries TIME and CYCLE in
# each file's FieldData. See vc.time_series_index().
dataFile = ctx.time_series_index()
OpenDatabase("localhost:" + dataFile, 0)
AddPlot("Pseudocolor", "temp", 1, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)
DrawPlots()

#
# Make the image nicer
#
annotationAtts = AnnotationAttributes()
annotationAtts.axes2D.visible = 0
annotationAtts.axes3D.visible = 0
annotationAtts.axes3D.triadFlag = 0
annotationAtts.axes3D.bboxFlag = 0
annotationAtts.userInfoFlag = 0
annotationAtts.databaseInfoFlag = 0
annotationAtts.timeInfoFlag = 1
annotationAtts.legendInfoFlag = 0
annotationAtts.backgroundColor = (0, 0, 0, 255)
annotationAtts.foregroundColor = (255, 255, 255, 255)
annotationAtts.backgroundMode = annotationAtts.Solid
annotationAtts.axesArray.visible = 1
SetAnnotationAttributes(annotationAtts)

#
# Put the cycle and the time on the frame.
#
# This vignette's whole subject is a multi-timestep database, and without
# this its twenty frames differ only in the data -- nothing in the picture
# says which timestep it is. $cycle and $time are VisIt's own macros,
# expanded at render time from whatever the reader reported, so this is also
# the most direct way to SEE what the reader made of the series: over the
# legacy varying*.vtk files it reads "Time: 0" on all twenty frames under
# VisIt 3.4.2, because those files carry no time. Over the XML series
# (vc.time_series_index, and data/make_time_series.py for why) it reads the
# real values.
#
# databaseInfoFlag stays off. VisIt's built-in database annotation would say
# the same thing, but it also prints the database path, which is
# machine-specific and would put this machine's directory layout into every
# blessed baseline.
timeAnnotation = CreateAnnotationObject("Text2D")
timeAnnotation.text = "Cycle: $cycle    Time: $time"
timeAnnotation.position = (0.02, 0.94)
timeAnnotation.height = 0.03
timeAnnotation.useForegroundForTextColor = 1

#
# Set what we are looking at
#
View3DAtts = View3DAttributes()
View3DAtts.viewNormal = (0.155693, -0.913673, 0.375447)
View3DAtts.focus = (0, 0, 0)
View3DAtts.viewUp = (-0.0889586, 0.365569, 0.926524)
View3DAtts.viewAngle = 30
View3DAtts.parallelScale = 17.3205
View3DAtts.nearPlane = -34.641
View3DAtts.farPlane = 34.641
View3DAtts.imagePan = (0, 0)
View3DAtts.imageZoom = 1.00
View3DAtts.perspective = 1
View3DAtts.eyeAngle = 2
View3DAtts.centerOfRotationSet = 0
View3DAtts.centerOfRotation = (0, 0, 0)
View3DAtts.axis3DScaleFlag = 0
View3DAtts.axis3DScales = (1, 1, 1)
View3DAtts.shear = (0, 0, 1)
View3DAtts.windowValid = 1
SetView3D(View3DAtts)

#
# Set the basic save options.
#
saveAtts = SaveWindowAttributes()
saveAtts.family = 0
saveAtts.format = saveAtts.PNG
saveAtts.resConstraint = saveAtts.NoConstraint
saveAtts.width = 2048
saveAtts.height = 1532

#
# Create the output directory structure.
#
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass
saveAtts.outputToCurrentDirectory = 0
saveAtts.outputDirectory = saveDir
outputName = "ex05_visit_%04d.png"

#
# Loop over the time states
#
nTimeSteps = TimeSliderGetNStates()

for timeStep in range(0, nTimeSteps):
    # Save an image each step
    print("\nSaving image for timestep: ", timeStep, flush=True)
    TimeSliderSetState(timeStep)
    saveAtts.fileName = outputName % timeStep
    SetSaveWindowAttributes(saveAtts)
    SaveWindow()

    # Query stats about data each step
    SetQueryFloatFormat("%g")
    print("\n")
    print("Queries for timestep: ", timeStep)
    print("3D surface area: ", Query("3D surface area"))
    print("Average Value  : ", Query("Average Value"))
    print("Centroid:        ", Query("Centroid"))
    print("GridInformation: ", Query("Grid Information"))
    print("MinMax:          ", Query("MinMax", use_actual_data=1))
    print("NumNodes:        ", Query("NumNodes", use_actual_data=1))
    print("NumZones:        ", Query("NumZones", use_actual_data=1))
    print("Volume:          ", Query("Volume"))
    print("Volume:          ", Query("Sample Statistics"))

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
input_pattern = script_dir + "/output/ex05_visit_%04d.png"
output_movie = script_dir + "/ex05_visit.mp4"
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
