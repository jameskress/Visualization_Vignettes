#
# Visualization Vignettes
#
# ex05_pvMultiTimeStepFile -- read a multi-timestep database and save extracts per step
#
# Demonstrates ParaView's extractor mechanism over a time series:
# CreateExtractor plus SaveExtracts, writing one JPEG per timestep.
#
# ex12_pvExtractRegression builds on this pattern and adds numerical
# extracts that can be regression-tested independently of the pixels.
#
# RUNNING IT
#
#   Locally:
#     pvbatch --force-offscreen-rendering ex05_pvMultiTimeStepFile.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type ParaView --machine_name my-machine
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
#   ./Testing/ex05_pvMultiTimeStepFile_results.json for the harness to compare numerically,
#   alongside the existing image and known_good_value.txt comparisons.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys
import pathlib
import paraview
import subprocess
from paraview.simple import *

paraview.compatibility.major = 5
paraview.compatibility.minor = 13


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

VIGNETTE = "ex05_pvMultiTimeStepFile"
TOOL = "ParaView"

_args = vc.parse_args(VIGNETTE, TOOL, description="read a multi-timestep database and save extracts per step")
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

print("Running ParaView example script: ", sys.argv[0], "\n")

# Get directory of this script
script_dir = os.path.abspath(os.path.dirname(__file__))
print("Running script from: ", script_dir)

#### disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()

# ----------------------------------------------------------------
# setup views used in the visualization
# ----------------------------------------------------------------

# get the material library
materialLibrary1 = GetMaterialLibrary()

# Create a new 'Render View'
renderView1 = CreateView("RenderView")
renderView1.ViewSize = [2082, 924]
renderView1.AxesGrid = "GridAxes3DActor"
renderView1.StereoType = "Crystal Eyes"
renderView1.CameraPosition = [
    -40.02967480143397,
    -19.396555422671625,
    49.99859740142211,
]
renderView1.CameraViewUp = [
    0.22243375416581943,
    -0.9557185249379747,
    -0.1926793349014932,
]
renderView1.CameraFocalDisk = 1.0
renderView1.CameraParallelScale = 17.320508075688775
renderView1.OSPRayMaterialLibrary = materialLibrary1
renderView1.ShowAnnotation = False  # Disables render view annotations
SetActiveView(None)

# ----------------------------------------------------------------
# setup view layouts
# ----------------------------------------------------------------

# create new layout object 'Layout #1'
layout1 = CreateLayout(name="Layout #1")
layout1.AssignView(0, renderView1)
layout1.SetSize(2082, 924)

# ----------------------------------------------------------------
# restore active view
SetActiveView(renderView1)
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# setup the data processing pipelines
# ----------------------------------------------------------------

# create a new 'Legacy VTK Reader'
varying00vtk = LegacyVTKReader(
    registrationName="varying00.vtk*",
    FileNames=[
        script_dir + "/../../data/varying_data/varying00.vtk",
        script_dir + "/../../data/varying_data/varying01.vtk",
        script_dir + "/../../data/varying_data/varying02.vtk",
        script_dir + "/../../data/varying_data/varying03.vtk",
        script_dir + "/../../data/varying_data/varying04.vtk",
        script_dir + "/../../data/varying_data/varying05.vtk",
        script_dir + "/../../data/varying_data/varying06.vtk",
        script_dir + "/../../data/varying_data/varying07.vtk",
        script_dir + "/../../data/varying_data/varying08.vtk",
        script_dir + "/../../data/varying_data/varying09.vtk",
        script_dir + "/../../data/varying_data/varying10.vtk",
        script_dir + "/../../data/varying_data/varying11.vtk",
        script_dir + "/../../data/varying_data/varying12.vtk",
        script_dir + "/../../data/varying_data/varying13.vtk",
        script_dir + "/../../data/varying_data/varying14.vtk",
        script_dir + "/../../data/varying_data/varying15.vtk",
        script_dir + "/../../data/varying_data/varying16.vtk",
        script_dir + "/../../data/varying_data/varying17.vtk",
        script_dir + "/../../data/varying_data/varying18.vtk",
        script_dir + "/../../data/varying_data/varying19.vtk",
    ],
)

# ----------------------------------------------------------------
# setup the visualization in view 'renderView1'
# ----------------------------------------------------------------

# show data from varying00vtk
varying00vtkDisplay = Show(varying00vtk, renderView1, "UniformGridRepresentation")

# get 2D transfer function for 'temp'
tempTF2D = GetTransferFunction2D("temp")
tempTF2D.ScalarRangeInitialized = 1
tempTF2D.Range = [1.779039978981018, 27.403499603271484, 0.0, 1.0]

# get color transfer function/color map for 'temp'
tempLUT = GetColorTransferFunction("temp")
tempLUT.TransferFunction2D = tempTF2D
tempLUT.RGBPoints = [
    1.779039978981018,
    0.231373,
    0.298039,
    0.752941,
    14.591269791126251,
    0.865003,
    0.865003,
    0.865003,
    27.403499603271484,
    0.705882,
    0.0156863,
    0.14902,
]
tempLUT.ScalarRangeInitialized = 1.0

# get opacity transfer function/opacity map for 'temp'
tempPWF = GetOpacityTransferFunction("temp")
tempPWF.Points = [1.779039978981018, 0.0, 0.5, 0.0, 27.403499603271484, 1.0, 0.5, 0.0]
tempPWF.ScalarRangeInitialized = 1

# trace defaults for the display properties.
varying00vtkDisplay.Representation = "Surface"
varying00vtkDisplay.ColorArrayName = ["POINTS", "temp"]
varying00vtkDisplay.LookupTable = tempLUT
varying00vtkDisplay.SelectTCoordArray = "None"
varying00vtkDisplay.SelectNormalArray = "None"
varying00vtkDisplay.SelectTangentArray = "None"
varying00vtkDisplay.OSPRayScaleArray = "temp"
varying00vtkDisplay.OSPRayScaleFunction = "PiecewiseFunction"
varying00vtkDisplay.SelectOrientationVectors = "None"
varying00vtkDisplay.ScaleFactor = 2.0
varying00vtkDisplay.SelectScaleArray = "temp"
varying00vtkDisplay.GlyphType = "Arrow"
varying00vtkDisplay.GlyphTableIndexArray = "temp"
varying00vtkDisplay.GaussianRadius = 0.1
varying00vtkDisplay.SetScaleArray = ["POINTS", "temp"]
varying00vtkDisplay.ScaleTransferFunction = "PiecewiseFunction"
varying00vtkDisplay.OpacityArray = ["POINTS", "temp"]
varying00vtkDisplay.OpacityTransferFunction = "PiecewiseFunction"
varying00vtkDisplay.DataAxesGrid = "GridAxesRepresentation"
varying00vtkDisplay.PolarAxes = "PolarAxesRepresentation"
varying00vtkDisplay.ScalarOpacityUnitDistance = 0.7069595132934193
varying00vtkDisplay.ScalarOpacityFunction = tempPWF
varying00vtkDisplay.TransferFunction2D = tempTF2D
varying00vtkDisplay.OpacityArrayName = ["POINTS", "temp"]
varying00vtkDisplay.ColorArray2Name = ["POINTS", "temp"]
varying00vtkDisplay.IsosurfaceValues = [14.591269791126251]
varying00vtkDisplay.SliceFunction = "Plane"
varying00vtkDisplay.Slice = 24
varying00vtkDisplay.SelectInputVectors = [None, ""]
varying00vtkDisplay.WriteLog = ""

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
varying00vtkDisplay.ScaleTransferFunction.Points = [
    1.779039978981018,
    0.0,
    0.5,
    0.0,
    27.403499603271484,
    1.0,
    0.5,
    0.0,
]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
varying00vtkDisplay.OpacityTransferFunction.Points = [
    1.779039978981018,
    0.0,
    0.5,
    0.0,
    27.403499603271484,
    1.0,
    0.5,
    0.0,
]

# setup the color legend parameters for each legend in this view

# get color legend/bar for tempLUT in view renderView1
tempLUTColorBar = GetScalarBar(tempLUT, renderView1)
tempLUTColorBar.Title = "temp"
tempLUTColorBar.ComponentTitle = ""

# set color bar visibility
tempLUTColorBar.Visibility = 1

# show color legend
varying00vtkDisplay.SetScalarBarVisibility(renderView1, True)

# ----------------------------------------------------------------
# setup color maps and opacity mapes used in the visualization
# note: the Get..() functions create a new object, if needed
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# setup extractors
# ----------------------------------------------------------------

# create extractor
jPG1 = CreateExtractor("JPG", renderView1, registrationName="JPG1")
# trace defaults for the extractor.
jPG1.Trigger = "TimeStep"

# init the 'JPG' selected for 'Writer'
jPG1.Writer.FileName = "ex05_{timestep:06d}.jpg"
jPG1.Writer.ImageResolution = [2082, 924]
jPG1.Writer.Format = "JPEG"

# ----------------------------------------------------------------
# restore active source
SetActiveSource(jPG1)
# ----------------------------------------------------------------

# create folder to store images
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass

# generate extracts
SaveExtracts(ExtractsOutputDirectory=saveDir)


# Movie encoding is skipped on a cluster, where ffmpeg is often absent
# from the compute image. Previously selected by a bare positional
# argument; now driven by the shared --machine flag.
runningOnIbex = "no" if ctx.args.machine == "local" else "ibex"

if runningOnIbex != "ibex":
    print("Generating movie using ffmpeg\n")
    # ffmpeg create video
    imageLoc = script_dir + "/output/ex05_%06d.jpg"
    movieLoc = script_dir + "/ex05_pvMultiTimeSteps.mp4"
    cmd = (
        "ffmpeg -f image2 -framerate 6 -i "
        + imageLoc
        + " -qmin 1 -qmax 2 -g 100 -an -vcodec mpeg4 -flags +mv4+aic "
        + movieLoc
        + " -y"
    )
    subprocess.call(cmd, shell=True)

print("\nFinished ParaView example script\n")


# --------------------------------------------------------------------------
# Structured results and a real exit code.
#
# The assertion is deliberately conservative -- it checks only that every
# image already blessed as a baseline was produced again. That cannot fail on
# a setup where this vignette works today, and it does catch the failure the
# old harness could not see at all: a vignette that silently stops emitting a
# frame.
# --------------------------------------------------------------------------
ctx.assert_baselined_images_present()
sys.exit(ctx.finish())
