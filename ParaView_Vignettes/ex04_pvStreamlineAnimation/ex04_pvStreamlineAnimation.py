#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import os
import sys
import pathlib
import paraview
import subprocess
from paraview.simple import *
paraview.compatibility.major = 5
paraview.compatibility.minor = 10

print("Running ParaView example script: ", sys.argv[0], "\n")

# Get directory of this script
script_dir = os.path.abspath( os.path.dirname( __file__ ) )
print("Running script from: ",  script_dir )

#### disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()

# ----------------------------------------------------------------
# setup views used in the visualization
# ----------------------------------------------------------------

# get the material library
materialLibrary1 = GetMaterialLibrary()

# Create a new 'Render View'
renderView1 = CreateView('RenderView')
renderView1.ViewSize = [2334, 1863]
renderView1.AxesGrid = 'GridAxes3DActor'
renderView1.OrientationAxesVisibility = 0
renderView1.StereoType = 'Crystal Eyes'
renderView1.CameraPosition = [13.669840312083075, 14.763893194463204, 51.59045789536233]
renderView1.CameraFocalPoint = [-0.015402677710824217, -2.6004421659710117, 0.8948655523251257]
renderView1.CameraViewUp = [-0.0736869301049068, 0.9494013496431565, -0.3052987285061431]
renderView1.CameraFocalDisk = 1.0
renderView1.CameraParallelScale = 17.320508075688775
renderView1.UseColorPaletteForBackground = 0
renderView1.BackgroundColorMode = 'Gradient'
renderView1.BackEnd = 'OSPRay raycaster'
renderView1.OSPRayMaterialLibrary = materialLibrary1

SetActiveView(None)

# ----------------------------------------------------------------
# setup view layouts
# ----------------------------------------------------------------

# create new layout object 'Layout #1'
layout1 = CreateLayout(name='Layout #1')
layout1.AssignView(0, renderView1)
layout1.SetSize(2334, 1863)

# ----------------------------------------------------------------
# restore active view
SetActiveView(renderView1)
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# setup the data processing pipelines
# ----------------------------------------------------------------

# create a new 'Data Object Generator'
dataObjectGenerator1 = DataObjectGenerator(registrationName='DataObjectGenerator1')

# create a new 'VisItSiloReader'
noisesilo = VisItSiloReader(registrationName='noise.silo', FileName=[script_dir + '/../../data/noise.silo'])
noisesilo.MeshStatus = ['Mesh']
noisesilo.MaterialStatus = ['1 air', '2 chrome']
noisesilo.CellArrayStatus = ['airVf', 'airVfGradient', 'chromeVf']
noisesilo.PointArrayStatus = ['PointVar', 'grad', 'hardyglobal', 'hgslice', 'radial', 'shepardglobal', 'tensor_comps/grad_tensor_ii', 'tensor_comps/grad_tensor_ij', 'tensor_comps/grad_tensor_ik', 'tensor_comps/grad_tensor_ji', 'tensor_comps/grad_tensor_jj', 'tensor_comps/grad_tensor_jk', 'tensor_comps/grad_tensor_ki', 'tensor_comps/grad_tensor_kj', 'tensor_comps/grad_tensor_kk', 'x']

# create a new 'Transform'
transform1 = Transform(registrationName='Transform1', Input=dataObjectGenerator1)
transform1.Transform = 'Transform'

# init the 'Transform' selected for 'Transform'
transform1.Transform.Translate = [-10.0, -10.0, -10.0]
transform1.Transform.Scale = [20.0, 20.0, 20.0]

# create a new 'Resample To Image'
resampleToImage1 = ResampleToImage(registrationName='ResampleToImage1', Input=transform1)
resampleToImage1.SamplingDimensions = [7, 7, 7]
resampleToImage1.SamplingBounds = [-10.0, 10.0, -10.0, 10.0, -10.0, 10.0]

# create a new 'Stream Tracer With Custom Source'
streamTracerWithCustomSource1 = StreamTracerWithCustomSource(registrationName='StreamTracerWithCustomSource1', Input=noisesilo,
    SeedSource=resampleToImage1)
streamTracerWithCustomSource1.Vectors = ['POINTS', 'grad']
streamTracerWithCustomSource1.IntegrationDirection = 'FORWARD'
streamTracerWithCustomSource1.IntegrationStepUnit = 'Length'
streamTracerWithCustomSource1.MinimumStepLength = 0.1
streamTracerWithCustomSource1.MaximumStepLength = 0.1
streamTracerWithCustomSource1.MaximumSteps = 100
streamTracerWithCustomSource1.MaximumStreamlineLength = 20.0

# create a new 'Slice'
slice3 = Slice(registrationName='Slice3', Input=noisesilo)
slice3.SliceType = 'Plane'
slice3.HyperTreeGridSlicer = 'Plane'
slice3.SliceOffsetValues = [0.0]

# init the 'Plane' selected for 'SliceType'
slice3.SliceType.Origin = [0.0, 0.0, -9.9]
slice3.SliceType.Normal = [0.0, 0.0, 1.0]

# create a new 'Slice'
slice1 = Slice(registrationName='Slice1', Input=noisesilo)
slice1.SliceType = 'Plane'
slice1.HyperTreeGridSlicer = 'Plane'
slice1.SliceOffsetValues = [0.0]

# init the 'Plane' selected for 'SliceType'
slice1.SliceType.Origin = [-9.9, 0.0, 0.0]

# create a new 'Slice'
slice2 = Slice(registrationName='Slice2', Input=noisesilo)
slice2.SliceType = 'Plane'
slice2.HyperTreeGridSlicer = 'Plane'
slice2.SliceOffsetValues = [0.0]

# init the 'Plane' selected for 'SliceType'
slice2.SliceType.Origin = [0.0, -9.9, 0.0]
slice2.SliceType.Normal = [0.0, 1.0, 0.0]

# create a new 'Contour'
contour1 = Contour(registrationName='Contour1', Input=streamTracerWithCustomSource1)
contour1.ContourBy = ['POINTS', 'IntegrationTime']
contour1.Isosurfaces = [0.01]
contour1.PointMergeMethod = 'Uniform Binning'

# ----------------------------------------------------------------
# setup the visualization in view 'renderView1'
# ----------------------------------------------------------------

# show data from slice1
slice1Display = Show(slice1, renderView1, 'GeometryRepresentation')

# get 2D transfer function for 'hardyglobal'
hardyglobalTF2D = GetTransferFunction2D('hardyglobal')
hardyglobalTF2D.ScalarRangeInitialized = 1
hardyglobalTF2D.Range = [1.0955432653427124, 5.889651775360107, 0.0, 1.0]

# get color transfer function/color map for 'hardyglobal'
hardyglobalLUT = GetColorTransferFunction('hardyglobal')
hardyglobalLUT.TransferFunction2D = hardyglobalTF2D
hardyglobalLUT.RGBPoints = [1.0955432653427124, 0.278431372549, 0.278431372549, 0.858823529412, 1.7811007822751999, 0.0, 0.0, 0.360784313725, 2.46186419069767, 0.0, 1.0, 1.0, 3.152215816140175, 0.0, 0.501960784314, 0.0, 3.832979224562645, 1.0, 1.0, 0.0, 4.518536741495133, 1.0, 0.380392156863, 0.0, 5.20409425842762, 0.419607843137, 0.0, 0.0, 5.889651775360107, 0.878431372549, 0.301960784314, 0.301960784314]
hardyglobalLUT.ColorSpace = 'RGB'
hardyglobalLUT.ScalarRangeInitialized = 1.0

# trace defaults for the display properties.
slice1Display.Representation = 'Surface'
slice1Display.ColorArrayName = ['POINTS', 'hardyglobal']
slice1Display.LookupTable = hardyglobalLUT
slice1Display.SelectTCoordArray = 'None'
slice1Display.SelectNormalArray = 'None'
slice1Display.SelectTangentArray = 'None'
slice1Display.OSPRayScaleArray = 'grad'
slice1Display.OSPRayScaleFunction = 'PiecewiseFunction'
slice1Display.SelectOrientationVectors = 'None'
slice1Display.ScaleFactor = 2.0
slice1Display.SelectScaleArray = 'None'
slice1Display.GlyphType = 'Arrow'
slice1Display.GlyphTableIndexArray = 'None'
slice1Display.GaussianRadius = 0.1
slice1Display.SetScaleArray = ['POINTS', 'grad']
slice1Display.ScaleTransferFunction = 'PiecewiseFunction'
slice1Display.OpacityArray = ['POINTS', 'grad']
slice1Display.OpacityTransferFunction = 'PiecewiseFunction'
slice1Display.DataAxesGrid = 'GridAxesRepresentation'
slice1Display.PolarAxes = 'PolarAxesRepresentation'
slice1Display.SelectInputVectors = ['POINTS', 'grad']
slice1Display.WriteLog = ''

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
slice1Display.ScaleTransferFunction.Points = [-0.46863847970962524, 0.0, 0.5, 0.0, 0.17852503061294556, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
slice1Display.OpacityTransferFunction.Points = [-0.46863847970962524, 0.0, 0.5, 0.0, 0.17852503061294556, 1.0, 0.5, 0.0]

# show data from slice2
slice2Display = Show(slice2, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
slice2Display.Representation = 'Surface'
slice2Display.ColorArrayName = ['POINTS', 'hardyglobal']
slice2Display.LookupTable = hardyglobalLUT
slice2Display.SelectTCoordArray = 'None'
slice2Display.SelectNormalArray = 'None'
slice2Display.SelectTangentArray = 'None'
slice2Display.OSPRayScaleArray = 'grad'
slice2Display.OSPRayScaleFunction = 'PiecewiseFunction'
slice2Display.SelectOrientationVectors = 'None'
slice2Display.ScaleFactor = 2.0
slice2Display.SelectScaleArray = 'None'
slice2Display.GlyphType = 'Arrow'
slice2Display.GlyphTableIndexArray = 'None'
slice2Display.GaussianRadius = 0.1
slice2Display.SetScaleArray = ['POINTS', 'grad']
slice2Display.ScaleTransferFunction = 'PiecewiseFunction'
slice2Display.OpacityArray = ['POINTS', 'grad']
slice2Display.OpacityTransferFunction = 'PiecewiseFunction'
slice2Display.DataAxesGrid = 'GridAxesRepresentation'
slice2Display.PolarAxes = 'PolarAxesRepresentation'
slice2Display.SelectInputVectors = ['POINTS', 'grad']
slice2Display.WriteLog = ''

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
slice2Display.ScaleTransferFunction.Points = [-0.24874216318130493, 0.0, 0.5, 0.0, 0.24097084999084473, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
slice2Display.OpacityTransferFunction.Points = [-0.24874216318130493, 0.0, 0.5, 0.0, 0.24097084999084473, 1.0, 0.5, 0.0]

# show data from slice3
slice3Display = Show(slice3, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
slice3Display.Representation = 'Surface'
slice3Display.ColorArrayName = ['POINTS', 'hardyglobal']
slice3Display.LookupTable = hardyglobalLUT
slice3Display.SelectTCoordArray = 'None'
slice3Display.SelectNormalArray = 'None'
slice3Display.SelectTangentArray = 'None'
slice3Display.OSPRayScaleArray = 'grad'
slice3Display.OSPRayScaleFunction = 'PiecewiseFunction'
slice3Display.SelectOrientationVectors = 'None'
slice3Display.ScaleFactor = 2.0
slice3Display.SelectScaleArray = 'None'
slice3Display.GlyphType = 'Arrow'
slice3Display.GlyphTableIndexArray = 'None'
slice3Display.GaussianRadius = 0.1
slice3Display.SetScaleArray = ['POINTS', 'grad']
slice3Display.ScaleTransferFunction = 'PiecewiseFunction'
slice3Display.OpacityArray = ['POINTS', 'grad']
slice3Display.OpacityTransferFunction = 'PiecewiseFunction'
slice3Display.DataAxesGrid = 'GridAxesRepresentation'
slice3Display.PolarAxes = 'PolarAxesRepresentation'
slice3Display.SelectInputVectors = ['POINTS', 'grad']
slice3Display.WriteLog = ''

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
slice3Display.ScaleTransferFunction.Points = [-0.21827083826065063, 0.0, 0.5, 0.0, 0.5315131545066833, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
slice3Display.OpacityTransferFunction.Points = [-0.21827083826065063, 0.0, 0.5, 0.0, 0.5315131545066833, 1.0, 0.5, 0.0]

# show data from streamTracerWithCustomSource1
streamTracerWithCustomSource1Display = Show(streamTracerWithCustomSource1, renderView1, 'GeometryRepresentation')

# get 2D transfer function for 'SeedIds'
seedIdsTF2D = GetTransferFunction2D('SeedIds')

# get color transfer function/color map for 'SeedIds'
seedIdsLUT = GetColorTransferFunction('SeedIds')
seedIdsLUT.TransferFunction2D = seedIdsTF2D
seedIdsLUT.RGBPoints = [0.0, 0.278431372549, 0.278431372549, 0.858823529412, 48.906, 0.0, 0.0, 0.360784313725, 97.46999999999998, 0.0, 1.0, 1.0, 146.718, 0.0, 0.501960784314, 0.0, 195.28199999999998, 1.0, 1.0, 0.0, 244.188, 1.0, 0.380392156863, 0.0, 293.094, 0.419607843137, 0.0, 0.0, 342.0, 0.878431372549, 0.301960784314, 0.301960784314]
seedIdsLUT.ColorSpace = 'RGB'
seedIdsLUT.ScalarRangeInitialized = 1.0

# trace defaults for the display properties.
streamTracerWithCustomSource1Display.Representation = 'Surface'
streamTracerWithCustomSource1Display.ColorArrayName = ['CELLS', 'SeedIds']
streamTracerWithCustomSource1Display.LookupTable = seedIdsLUT
streamTracerWithCustomSource1Display.LineWidth = 7.0
streamTracerWithCustomSource1Display.RenderLinesAsTubes = 1
streamTracerWithCustomSource1Display.SelectTCoordArray = 'None'
streamTracerWithCustomSource1Display.SelectNormalArray = 'None'
streamTracerWithCustomSource1Display.SelectTangentArray = 'None'
streamTracerWithCustomSource1Display.OSPRayScaleArray = 'AngularVelocity'
streamTracerWithCustomSource1Display.OSPRayScaleFunction = 'PiecewiseFunction'
streamTracerWithCustomSource1Display.SelectOrientationVectors = 'Normals'
streamTracerWithCustomSource1Display.ScaleFactor = 1.9999980926513672
streamTracerWithCustomSource1Display.SelectScaleArray = 'AngularVelocity'
streamTracerWithCustomSource1Display.GlyphType = 'Arrow'
streamTracerWithCustomSource1Display.GlyphTableIndexArray = 'AngularVelocity'
streamTracerWithCustomSource1Display.GaussianRadius = 0.09999990463256836
streamTracerWithCustomSource1Display.SetScaleArray = ['POINTS', 'AngularVelocity']
streamTracerWithCustomSource1Display.ScaleTransferFunction = 'PiecewiseFunction'
streamTracerWithCustomSource1Display.OpacityArray = ['POINTS', 'AngularVelocity']
streamTracerWithCustomSource1Display.OpacityTransferFunction = 'PiecewiseFunction'
streamTracerWithCustomSource1Display.DataAxesGrid = 'GridAxesRepresentation'
streamTracerWithCustomSource1Display.PolarAxes = 'PolarAxesRepresentation'
streamTracerWithCustomSource1Display.SelectInputVectors = ['POINTS', 'Normals']
streamTracerWithCustomSource1Display.WriteLog = ''

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
streamTracerWithCustomSource1Display.ScaleTransferFunction.Points = [-0.19191565978292627, 0.0, 0.5, 0.0, 0.1842659855760513, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
streamTracerWithCustomSource1Display.OpacityTransferFunction.Points = [-0.19191565978292627, 0.0, 0.5, 0.0, 0.1842659855760513, 1.0, 0.5, 0.0]

# show data from contour1
contour1Display = Show(contour1, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
contour1Display.Representation = 'Surface'
contour1Display.ColorArrayName = ['CELLS', 'SeedIds']
contour1Display.LookupTable = seedIdsLUT
contour1Display.PointSize = 20.0
contour1Display.RenderPointsAsSpheres = 1
contour1Display.SelectTCoordArray = 'None'
contour1Display.SelectNormalArray = 'None'
contour1Display.SelectTangentArray = 'None'
contour1Display.OSPRayScaleFunction = 'PiecewiseFunction'
contour1Display.SelectOrientationVectors = 'None'
contour1Display.ScaleFactor = -0.2
contour1Display.SelectScaleArray = 'None'
contour1Display.GlyphType = 'Arrow'
contour1Display.GlyphTableIndexArray = 'None'
contour1Display.GaussianRadius = -0.01
contour1Display.SetScaleArray = [None, '']
contour1Display.ScaleTransferFunction = 'PiecewiseFunction'
contour1Display.OpacityArray = [None, '']
contour1Display.OpacityTransferFunction = 'PiecewiseFunction'
contour1Display.DataAxesGrid = 'GridAxesRepresentation'
contour1Display.PolarAxes = 'PolarAxesRepresentation'
contour1Display.SelectInputVectors = [None, '']
contour1Display.WriteLog = ''

# ----------------------------------------------------------------
# setup color maps and opacity mapes used in the visualization
# note: the Get..() functions create a new object, if needed
# ----------------------------------------------------------------

# get opacity transfer function/opacity map for 'hardyglobal'
hardyglobalPWF = GetOpacityTransferFunction('hardyglobal')
hardyglobalPWF.Points = [1.0955432653427124, 0.0, 0.5, 0.0, 5.889651775360107, 1.0, 0.5, 0.0]
hardyglobalPWF.ScalarRangeInitialized = 1

# get opacity transfer function/opacity map for 'SeedIds'
seedIdsPWF = GetOpacityTransferFunction('SeedIds')
seedIdsPWF.Points = [0.0, 0.0, 0.5, 0.0, 342.0, 1.0, 0.5, 0.0]
seedIdsPWF.ScalarRangeInitialized = 1

# ----------------------------------------------------------------
# restore active source
SetActiveSource(slice3)
# ----------------------------------------------------------------

# create folder to store images
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass

for ts in range(0,125):
    streamTracerWithCustomSource1.MaximumSteps = ts
    print("Saving Image ", ts, " of 125")
    # save screenshot
    SaveScreenshot(script_dir + '/output/ex04_%04d.png' % ts, renderView1, ImageResolution=[4054, 2536])

# ffmpeg create video
imageLoc = script_dir + '/output/ex04_%04d.png'
movieLoc = script_dir + '/ex04_pvStreamlineAnimation.mp4'
cmd = 'ffmpeg -f image2 -framerate 6 -i ' + imageLoc + ' -qmin 1 -qmax 2 -g 100 -an -vcodec mpeg4 -flags +mv4+aic ' + movieLoc
subprocess.call(cmd, shell=True)

print("\nFinished ParaView example script\n")
