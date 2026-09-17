# state file generated using paraview version 6.0.1
import paraview
paraview.compatibility.major = 6
paraview.compatibility.minor = 0

#### import the simple module from the paraview
from paraview.simple import *
#### disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()

# ----------------------------------------------------------------
# setup views used in the visualization
# ----------------------------------------------------------------

# get the material library
materialLibrary1 = GetMaterialLibrary()

# Create a new 'Render View'
renderView1 = CreateView('RenderView')
renderView1.Set(
    ViewSize=[2260, 1806],
    CameraPosition=[62.58892487212335, 23.672202823103955, -71.5697709665284],
    CameraViewUp=[0.7618017795619137, -0.33151517011805287, 0.5565570416748853],
    CameraFocalDisk=1.0,
    CameraParallelScale=17.320508075688775,
    OSPRayMaterialLibrary=materialLibrary1,
)

SetActiveView(None)

# ----------------------------------------------------------------
# setup view layouts
# ----------------------------------------------------------------

# create new layout object 'Layout #1'
layout1 = CreateLayout(name='Layout #1')
layout1.AssignView(0, renderView1)
layout1.SetSize(2260, 1806)

# ----------------------------------------------------------------
# restore active view
SetActiveView(renderView1)
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# setup the data processing pipelines
# ----------------------------------------------------------------

# create a new 'Vis It Silo Reader'
noisesilo = VisItSiloReader(registrationName='noise.silo', FileName=['/Users/kressjm/Dropbox/noise.silo'])
noisesilo.Set(
    MeshStatus=['Mesh'],
    MaterialStatus=[],
    CellArrayStatus=[],
    PointArrayStatus=['PointVar', 'grad', 'hardyglobal', 'hgslice', 'radial', 'shepardglobal', 'tensor_comps/grad_tensor_ii', 'tensor_comps/grad_tensor_ij', 'tensor_comps/grad_tensor_ik', 'tensor_comps/grad_tensor_ji', 'tensor_comps/grad_tensor_jj', 'tensor_comps/grad_tensor_jk', 'tensor_comps/grad_tensor_ki', 'tensor_comps/grad_tensor_kj', 'tensor_comps/grad_tensor_kk', 'x'],
)

# create a new 'Contour'
contour1 = Contour(registrationName='Contour1', Input=noisesilo)
contour1.Set(
    ContourBy=['POINTS', 'radial'],
    Isosurfaces=[0.0, 3.849001990424262, 7.698003980848524, 11.547005971272785, 15.396007961697048, 19.24500995212131, 23.09401194254557, 26.943013932969833, 30.792015923394096, 34.64101791381836],
)

# ----------------------------------------------------------------
# setup the visualization in view 'renderView1'
# ----------------------------------------------------------------

# show data from contour1
contour1Display = Show(contour1, renderView1, 'GeometryRepresentation')

# get color transfer function/color map for 'radial'
radialLUT = GetColorTransferFunction('radial')
radialLUT.Set(
    RGBPoints=GenerateRGBPoints(
        range_min=0.0,
        range_max=34.64101791381836,
    ),
    ScalarRangeInitialized=1.0,
)

# trace defaults for the display properties.
contour1Display.Set(
    Representation='Surface',
    ColorArrayName=['POINTS', 'radial'],
    LookupTable=radialLUT,
    SelectNormalArray='Normals',
    Assembly='Hierarchy',
)

# init the 'Piecewise Function' selected for 'ScaleTransferFunction'
contour1Display.ScaleTransferFunction.Points = [0.1387956142425537, 0.0, 0.5, 0.0, 1.237539529800415, 1.0, 0.5, 0.0]

# init the 'Piecewise Function' selected for 'OpacityTransferFunction'
contour1Display.OpacityTransferFunction.Points = [0.1387956142425537, 0.0, 0.5, 0.0, 1.237539529800415, 1.0, 0.5, 0.0]

# setup the color legend parameters for each legend in this view

# get color legend/bar for radialLUT in view renderView1
radialLUTColorBar = GetScalarBar(radialLUT, renderView1)
radialLUTColorBar.Set(
    Title='radial',
    ComponentTitle='',
)

# set color bar visibility
radialLUTColorBar.Visibility = 1

# show color legend
contour1Display.SetScalarBarVisibility(renderView1, True)

# ----------------------------------------------------------------
# setup color maps and opacity maps used in the visualization
# note: the Get..() functions create a new object, if needed
# ----------------------------------------------------------------

# get opacity transfer function/opacity map for 'radial'
radialPWF = GetOpacityTransferFunction('radial')
radialPWF.Set(
    Points=[0.0, 0.0, 0.5, 0.0, 34.64101791381836, 1.0, 0.5, 0.0],
    ScalarRangeInitialized=1,
)

# ----------------------------------------------------------------
# setup animation scene, tracks and keyframes
# note: the Get..() functions create a new object, if needed
# ----------------------------------------------------------------

# get the time-keeper
timeKeeper1 = GetTimeKeeper()

# initialize the timekeeper

# get time animation track
timeAnimationCue1 = GetTimeTrack()

# initialize the animation track

# get animation scene
animationScene1 = GetAnimationScene()

# initialize the animation scene
animationScene1.Set(
    ViewModules=renderView1,
    Cues=timeAnimationCue1,
    AnimationTime=0.0,
    PlayMode='Snap To TimeSteps',
)

# initialize the animation scene

# ----------------------------------------------------------------
# setup extractors
# ----------------------------------------------------------------

# create extractor
pNG1 = CreateExtractor('PNG', renderView1, registrationName='PNG1')
# trace defaults for the extractor.
# init the 'PNG' selected for 'Writer'
pNG1.Writer.Set(
    FileName='RenderView1_{timestep:06d}{camera}.png',
    ImageResolution=[2260, 1806],
    Format='PNG',
)

# ----------------------------------------------------------------
# restore active source
SetActiveSource(pNG1)
# ----------------------------------------------------------------


##--------------------------------------------
## You may need to add some code at the end of this python script depending on your usage, eg:
#
## Render all views to see them appears
# RenderAllViews()
#
## Interact with the view, usefull when running from pvpython
# Interact()
#
## Save a screenshot of the active view
# SaveScreenshot("path/to/screenshot.png")
#
## Save a screenshot of a layout (multiple splitted view)
# SaveScreenshot("path/to/screenshot.png", GetLayout())
#
## Save all "Extractors" from the pipeline browser
SaveExtracts()
#
## Save a animation of the current active view
# SaveAnimation()
#
## Please refer to the documentation of paraview.simple
## https://www.paraview.org/paraview-docs/nightly/python/
##--------------------------------------------