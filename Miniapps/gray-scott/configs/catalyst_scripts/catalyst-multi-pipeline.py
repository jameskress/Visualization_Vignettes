from paraview import catalyst
from paraview.simple import *
from paraview.catalyst import get_args, get_execute_params
import time
import os


paraview.simple._DisableFirstRenderCameraReset()

# ----------------------------------------------------------------
# setup views used in the visualization
# ----------------------------------------------------------------

# get the material library
materialLibrary1 = GetMaterialLibrary()

# Create a new 'Render View'
renderView1 = CreateView("RenderView")
renderView1.ViewSize = [2113, 1338]
renderView1.AxesGrid = "GridAxes3DActor"
renderView1.CenterOfRotation = [3.25, 3.25, 3.25]
renderView1.StereoType = "Crystal Eyes"
renderView1.CameraPosition = [13.66154553783134, 19.16943565344975, -7.295554885765629]
renderView1.CameraFocalPoint = [
    3.2500000000000044,
    3.250000000000006,
    3.250000000000006,
]
renderView1.CameraViewUp = [
    -0.621575432095255,
    -0.10749140160884736,
    -0.7759443155251301,
]
renderView1.CameraFocalDisk = 1.0
renderView1.CameraParallelScale = 5.629165124598851
renderView1.BackEnd = "OSPRay raycaster"
renderView1.OSPRayMaterialLibrary = materialLibrary1

SetActiveView(None)

# ----------------------------------------------------------------
# setup view layouts
# ----------------------------------------------------------------

# create new layout object 'Layout #1'
layout1 = CreateLayout(name="Layout #1")
layout1.AssignView(0, renderView1)
layout1.SetSize(2113, 1338)

# ----------------------------------------------------------------
# restore active view
SetActiveView(renderView1)
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# setup the data processing pipelines
# ----------------------------------------------------------------

# print values for parameters passed via adaptor (note these don't change,
# and hence must be created as command line params)
args = get_args()
for arg in args:
    if "channel-name" in arg:
        channel_name = arg.split("=")[1]
print("executing catalyst_pipeline")
print("===================================")
print("pipeline args={}".format(get_args()))
print("===================================")

# registrationName must match the channel name used in the 'CatalystAdaptor'.
producer = TrivialProducer(registrationName=channel_name)
producer.UpdatePipeline()

# example of how to query the pipeline to see what data we are getting
numPointArrays = producer.GetPointDataInformation().GetNumberOfArrays()
print("=======================================================")
print("The catalyst stream contains the following arrays---")
print("Number of point arrays = {}".format(numPointArrays))
for i in range(numPointArrays):
    currentArray = producer.GetPointDataInformation().GetArray(i)
    print("Array = {}, name = {}".format(i, currentArray.GetName()))
print("=======================================================")
producer.PointArrayStatus = ["v", "u"]

# create a new 'Extract Subset'
extractSubset1 = ExtractSubset(registrationName="ExtractSubset1", Input=producer)
extractSubset1.VOI = [0, 65, 0, 65, 0, 65]

# create a new 'Clip'
clip1 = Clip(registrationName="Clip1", Input=producer)
clip1.ClipType = "Plane"
clip1.HyperTreeGridClipper = "Plane"
clip1.Scalars = ["POINTS", "u"]
clip1.Value = 0.5724891890196234

# init the 'Plane' selected for 'ClipType'
clip1.ClipType.Origin = [2.626584119477097, 3.250000048428774, 3.250000048428774]

# init the 'Plane' selected for 'HyperTreeGridClipper'
clip1.HyperTreeGridClipper.Origin = [
    3.250000048428774,
    3.250000048428774,
    3.250000048428774,
]

# ----------------------------------------------------------------
# setup the visualization in view 'renderView1'
# ----------------------------------------------------------------

# show data from grid
gridDisplay = Show(producer, renderView1, "UniformGridRepresentation")

# get 2D transfer function for 'u'
uTF2D = GetTransferFunction2D("u")
uTF2D.ScalarRangeInitialized = 1
uTF2D.Range = [0.1449777870244238, 1.000000591014823, 0.0, 1.0]

# get color transfer function/color map for 'u'
uLUT = GetColorTransferFunction("u")
uLUT.TransferFunction2D = uTF2D
uLUT.RGBPoints = [
    0.1449777870244238,
    0.231373,
    0.298039,
    0.752941,
    0.5724891890196234,
    0.865003,
    0.865003,
    0.865003,
    1.000000591014823,
    0.705882,
    0.0156863,
    0.14902,
]
uLUT.ScalarRangeInitialized = 1.0

# get opacity transfer function/opacity map for 'u'
uPWF = GetOpacityTransferFunction("u")
uPWF.Points = [0.1449777870244238, 1.0, 0.5, 0.0, 1.000000591014823, 0.0, 0.5, 0.0]
uPWF.ScalarRangeInitialized = 1

# trace defaults for the display properties.
gridDisplay.Representation = "Volume"
gridDisplay.ColorArrayName = ["POINTS", "u"]
gridDisplay.LookupTable = uLUT
gridDisplay.SelectTCoordArray = "None"
gridDisplay.SelectNormalArray = "None"
gridDisplay.SelectTangentArray = "None"
gridDisplay.OSPRayScaleArray = "u"
gridDisplay.OSPRayScaleFunction = "PiecewiseFunction"
gridDisplay.SelectOrientationVectors = "None"
gridDisplay.ScaleFactor = 0.6500000096857548
gridDisplay.SelectScaleArray = "None"
gridDisplay.GlyphType = "Arrow"
gridDisplay.GlyphTableIndexArray = "None"
gridDisplay.GaussianRadius = 0.032500000484287736
gridDisplay.SetScaleArray = ["POINTS", "u"]
gridDisplay.ScaleTransferFunction = "PiecewiseFunction"
gridDisplay.OpacityArray = ["POINTS", "u"]
gridDisplay.OpacityTransferFunction = "PiecewiseFunction"
gridDisplay.DataAxesGrid = "GridAxesRepresentation"
gridDisplay.PolarAxes = "PolarAxesRepresentation"
gridDisplay.ScalarOpacityUnitDistance = 0.17320508333784457
gridDisplay.ScalarOpacityFunction = uPWF
gridDisplay.TransferFunction2D = uTF2D
gridDisplay.OpacityArrayName = ["POINTS", "u"]
gridDisplay.ColorArray2Name = ["POINTS", "u"]
gridDisplay.SliceFunction = "Plane"
gridDisplay.Slice = 32
gridDisplay.SelectInputVectors = [None, ""]
gridDisplay.WriteLog = ""

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
gridDisplay.ScaleTransferFunction.Points = [
    0.1449777870244238,
    0.0,
    0.5,
    0.0,
    1.000000591014823,
    1.0,
    0.5,
    0.0,
]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
gridDisplay.OpacityTransferFunction.Points = [
    0.1449777870244238,
    0.0,
    0.5,
    0.0,
    1.000000591014823,
    1.0,
    0.5,
    0.0,
]

# init the 'Plane' selected for 'SliceFunction'
gridDisplay.SliceFunction.Origin = [
    3.250000048428774,
    3.250000048428774,
    3.250000048428774,
]

# show data from clip1
clip1Display = Show(clip1, renderView1, "UnstructuredGridRepresentation")

# trace defaults for the display properties.
clip1Display.Representation = "Surface"
clip1Display.ColorArrayName = ["POINTS", "u"]
clip1Display.LookupTable = uLUT
clip1Display.SelectTCoordArray = "None"
clip1Display.SelectNormalArray = "None"
clip1Display.SelectTangentArray = "None"
clip1Display.OSPRayScaleArray = "u"
clip1Display.OSPRayScaleFunction = "PiecewiseFunction"
clip1Display.SelectOrientationVectors = "None"
clip1Display.ScaleFactor = 0.6500000096857548
clip1Display.SelectScaleArray = "None"
clip1Display.GlyphType = "Arrow"
clip1Display.GlyphTableIndexArray = "None"
clip1Display.GaussianRadius = 0.032500000484287736
clip1Display.SetScaleArray = ["POINTS", "u"]
clip1Display.ScaleTransferFunction = "PiecewiseFunction"
clip1Display.OpacityArray = ["POINTS", "u"]
clip1Display.OpacityTransferFunction = "PiecewiseFunction"
clip1Display.DataAxesGrid = "GridAxesRepresentation"
clip1Display.PolarAxes = "PolarAxesRepresentation"
clip1Display.ScalarOpacityFunction = uPWF
clip1Display.ScalarOpacityUnitDistance = 0.1880288130154373
clip1Display.OpacityArrayName = ["POINTS", "u"]
clip1Display.SelectInputVectors = [None, ""]
clip1Display.WriteLog = ""

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
clip1Display.ScaleTransferFunction.Points = [
    0.1449777870244238,
    0.0,
    0.5,
    0.0,
    1.0000005816863944,
    1.0,
    0.5,
    0.0,
]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
clip1Display.OpacityTransferFunction.Points = [
    0.1449777870244238,
    0.0,
    0.5,
    0.0,
    1.0000005816863944,
    1.0,
    0.5,
    0.0,
]

# setup the color legend parameters for each legend in this view

# get color legend/bar for uLUT in view renderView1
uLUTColorBar = GetScalarBar(uLUT, renderView1)
uLUTColorBar.Title = "u"
uLUTColorBar.ComponentTitle = ""

# set color bar visibility
uLUTColorBar.Visibility = 1

# show color legend
gridDisplay.SetScalarBarVisibility(renderView1, True)

# show color legend
clip1Display.SetScalarBarVisibility(renderView1, True)

# ----------------------------------------------------------------
# setup color maps and opacity mapes used in the visualization
# note: the Get..() functions create a new object, if needed
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# setup extractors
# ----------------------------------------------------------------

# create extractor
pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
# trace defaults for the extractor.
pNG1.Trigger = "TimeStep"

# init the 'PNG' selected for 'Writer'
pNG1.Writer.FileName = "RenderView1_{timestep:06d}{camera}.png"
pNG1.Writer.ImageResolution = [2113, 1338]
pNG1.Writer.Format = "PNG"

# ----------------------------------------------------------------
# restore active source
SetActiveSource(extractSubset1)
# ----------------------------------------------------------------

# ------------------------------------------------------------------------------
# Catalyst options
from paraview import catalyst

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.EnableCatalystLive = 1
options.CatalystLiveTrigger = "TimeStep"

# --------------------------------------------------------------
# Dynamically determine client
clientport = 22222
clienthost = "localhost"
options.CatalystLiveURL = "localhost:22222"
if "CATALYST_CLIENT" in os.environ:
    clienthost = os.environ["CATALYST_CLIENT"]
options.CatalystLiveURL = str(clienthost) + ":" + str(clientport)


def catalyst_execute(info):
    global producer

    producer.UpdatePipeline()

    # get params as example of a parameter changing during the simulation
    params = get_execute_params()

    print("\n===================================")
    print("executing (cycle={}, time={})".format(info.cycle, info.time))
    print("-----")
    print("pipeline parameters:")
    print("\n".join(params))
    print("-----")
    print("bounds:", producer.GetDataInformation().GetBounds())
    print("v-range:", producer.PointData["v"].GetRange(-1))
    print("u-range:", producer.PointData["u"].GetRange(-1))
    print("===================================\n")
    # slow things down for live view
    time.sleep(1)


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions

    # Code for non in-situ environments; if executing in post-processing
    # i.e. non-Catalyst mode, let's generate extracts using Catalyst options
    SaveExtractsUsingCatalystOptions(options)
