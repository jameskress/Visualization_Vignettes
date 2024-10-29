from paraview import catalyst
from paraview.simple import *
from paraview.catalyst import get_args, get_execute_params
import time
import os

# print values for parameters passed via adaptor (note these don't change,
# and hence must be created as command line params)
print("executing catalyst_pipeline")
print("===================================")
print("pipeline args={}".format(get_args()))
print("===================================")


# ----------------------------------------------------------------
# setup views used in the visualization
# ----------------------------------------------------------------

# Create a new 'Render View'
renderView1 = CreateView("RenderView")
renderView1.ViewSize = [2113, 1338]
renderView1.AxesGrid = "GridAxes3DActor"
renderView1.CenterOfRotation = [3.25, 3.25, 3.25]
renderView1.StereoType = "Crystal Eyes"
renderView1.CameraPosition = [16.22839398874534, 13.175585190880268, 17.60553858100882]
renderView1.CameraFocalPoint = [
    3.2500000000000013,
    3.250000000000001,
    3.2499999999999987,
]
renderView1.CameraViewUp = [
    -0.4761798412839785,
    0.8634421372548794,
    -0.16649454756084658,
]
renderView1.CameraFocalDisk = 1.0
renderView1.CameraParallelScale = 5.629165124598851

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


# registrationName must match the channel name used in the
# 'CatalystAdaptor'.
producer = TrivialProducer(registrationName="grid")


# ----------------------------------------------------------------
# setup the visualization in view 'renderView1'
# ----------------------------------------------------------------

# show data from grid
gridDisplay = Show(producer, renderView1, "UniformGridRepresentation")

# get 2D transfer function for 'v'
vTF2D = GetTransferFunction2D("v")
vTF2D.ScalarRangeInitialized = 1
vTF2D.Range = [0.0, 0.6006907877837987, 0.0, 1.0]

# get color transfer function/color map for 'v'
vLUT = GetColorTransferFunction("v")
vLUT.TransferFunction2D = vTF2D
vLUT.RGBPoints = [
    0.0,
    0.231373,
    0.298039,
    0.752941,
    0.30034539389189935,
    0.865003,
    0.865003,
    0.865003,
    0.6006907877837987,
    0.705882,
    0.0156863,
    0.14902,
]
vLUT.ScalarRangeInitialized = 1.0

# get opacity transfer function/opacity map for 'v'
vPWF = GetOpacityTransferFunction("v")
vPWF.Points = [0.0, 0.0, 0.5, 0.0, 0.6006907877837987, 1.0, 0.5, 0.0]
vPWF.ScalarRangeInitialized = 1

# trace defaults for the display properties.
gridDisplay.Representation = "Volume"
gridDisplay.ColorArrayName = ["POINTS", "v"]
gridDisplay.LookupTable = vLUT
gridDisplay.SelectTCoordArray = "None"
gridDisplay.SelectNormalArray = "None"
gridDisplay.SelectTangentArray = "None"
gridDisplay.OSPRayScaleArray = "u"
gridDisplay.OSPRayScaleFunction = "PiecewiseFunction"
gridDisplay.SelectOrientationVectors = "None"
gridDisplay.ScaleFactor = 0.6500000216066838
gridDisplay.SelectScaleArray = "None"
gridDisplay.GlyphType = "Arrow"
gridDisplay.GlyphTableIndexArray = "None"
gridDisplay.GaussianRadius = 0.032500001080334184
gridDisplay.SetScaleArray = ["POINTS", "u"]
gridDisplay.ScaleTransferFunction = "PiecewiseFunction"
gridDisplay.OpacityArray = ["POINTS", "u"]
gridDisplay.OpacityTransferFunction = "PiecewiseFunction"
gridDisplay.DataAxesGrid = "GridAxesRepresentation"
gridDisplay.PolarAxes = "PolarAxesRepresentation"
gridDisplay.ScalarOpacityUnitDistance = 0.1688917355325935
gridDisplay.ScalarOpacityFunction = vPWF
gridDisplay.TransferFunction2D = vTF2D
gridDisplay.OpacityArrayName = ["POINTS", "u"]
gridDisplay.ColorArray2Name = ["POINTS", "u"]
gridDisplay.SliceFunction = "Plane"
gridDisplay.Slice = 16
gridDisplay.SelectInputVectors = [None, ""]
gridDisplay.WriteLog = ""

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
gridDisplay.ScaleTransferFunction.Points = [
    0.09990542423657389,
    0.0,
    0.5,
    0.0,
    1.0000005863486756,
    1.0,
    0.5,
    0.0,
]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
gridDisplay.OpacityTransferFunction.Points = [
    0.09990542423657389,
    0.0,
    0.5,
    0.0,
    1.0000005863486756,
    1.0,
    0.5,
    0.0,
]

# init the 'Plane' selected for 'SliceFunction'
gridDisplay.SliceFunction.Origin = [
    3.2500001080334187,
    3.250000048428774,
    3.250000048428774,
]

# setup the color legend parameters for each legend in this view

# get color legend/bar for vLUT in view renderView1
vLUTColorBar = GetScalarBar(vLUT, renderView1)
vLUTColorBar.Title = "v"
vLUTColorBar.ComponentTitle = ""

# set color bar visibility
vLUTColorBar.Visibility = 1

# show color legend
gridDisplay.SetScalarBarVisibility(renderView1, True)

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
jPG1.Writer.FileName = "RenderView1_{timestep:06d}{camera}.jpg"
jPG1.Writer.ImageResolution = [2113, 1338]
jPG1.Writer.Format = "JPEG"

# ----------------------------------------------------------------
# restore active source
SetActiveSource(jPG1)
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
