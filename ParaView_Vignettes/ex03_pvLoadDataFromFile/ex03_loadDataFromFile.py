#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys
import pathlib
import paraview
from paraview.simple import *
paraview.compatibility.major = 5
paraview.compatibility.minor = 10

print("Running ParaView example script: ", sys.argv[0], "\n")

#### disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()

# get directory where script is stored
fileDir = str(pathlib.Path(__file__).parent.resolve())

# create a new 'VisItSiloReader'
noisesilo = VisItSiloReader(registrationName='noise.silo', FileName=[fileDir + '/../../data/noise.silo'])
noisesilo.MeshStatus = ['Mesh']
noisesilo.MaterialStatus = []
noisesilo.CellArrayStatus = []
noisesilo.PointArrayStatus = []

# Properties modified on noisesilo
noisesilo.MeshStatus = ['Mesh', 'Mesh2D', 'PointMesh']
noisesilo.MaterialStatus = ['1 air', '2 chrome']
noisesilo.CellArrayStatus = ['airVf', 'airVfGradient', 'chromeVf']
noisesilo.PointArrayStatus = ['PointVar', 'grad', 'hardyglobal', 'hgslice', 'radial', 'shepardglobal', 'tensor_comps/grad_tensor_ii', 'tensor_comps/grad_tensor_ij', 'tensor_comps/grad_tensor_ik', 'tensor_comps/grad_tensor_ji', 'tensor_comps/grad_tensor_jj', 'tensor_comps/grad_tensor_jk', 'tensor_comps/grad_tensor_ki', 'tensor_comps/grad_tensor_kj', 'tensor_comps/grad_tensor_kk', 'x']

# get active view
renderView1 = GetActiveViewOrCreate('RenderView')

# show data in view
noisesiloDisplay = Show(noisesilo, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
noisesiloDisplay.Representation = 'Surface'
noisesiloDisplay.ColorArrayName = [None, '']
noisesiloDisplay.SelectTCoordArray = 'None'
noisesiloDisplay.SelectNormalArray = 'None'
noisesiloDisplay.SelectTangentArray = 'None'
noisesiloDisplay.OSPRayScaleArray = 'PointVar'
noisesiloDisplay.OSPRayScaleFunction = 'PiecewiseFunction'
noisesiloDisplay.SelectOrientationVectors = 'None'
noisesiloDisplay.ScaleFactor = 2.0
noisesiloDisplay.SelectScaleArray = 'None'
noisesiloDisplay.GlyphType = 'Arrow'
noisesiloDisplay.GlyphTableIndexArray = 'None'
noisesiloDisplay.GaussianRadius = 0.1
noisesiloDisplay.SetScaleArray = ['POINTS', 'PointVar']
noisesiloDisplay.ScaleTransferFunction = 'PiecewiseFunction'
noisesiloDisplay.OpacityArray = ['POINTS', 'PointVar']
noisesiloDisplay.OpacityTransferFunction = 'PiecewiseFunction'
noisesiloDisplay.DataAxesGrid = 'GridAxesRepresentation'
noisesiloDisplay.PolarAxes = 'PolarAxesRepresentation'
noisesiloDisplay.SelectInputVectors = ['POINTS', 'grad']
noisesiloDisplay.WriteLog = ''

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
noisesiloDisplay.ScaleTransferFunction.Points = [1.0779780149459839, 0.0, 0.5, 0.0, 5.925835132598877, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
noisesiloDisplay.OpacityTransferFunction.Points = [1.0779780149459839, 0.0, 0.5, 0.0, 5.925835132598877, 1.0, 0.5, 0.0]

# reset view to fit data
renderView1.ResetCamera(False)

# get the material library
materialLibrary1 = GetMaterialLibrary()

# update the view to ensure updated data information
renderView1.Update()

# set scalar coloring
ColorBy(noisesiloDisplay, ('FIELD', 'vtkBlockColors'))

# show color bar/color legend
noisesiloDisplay.SetScalarBarVisibility(renderView1, True)

# get color transfer function/color map for 'vtkBlockColors'
vtkBlockColorsLUT = GetColorTransferFunction('vtkBlockColors')

# get opacity transfer function/opacity map for 'vtkBlockColors'
vtkBlockColorsPWF = GetOpacityTransferFunction('vtkBlockColors')

# get 2D transfer function for 'vtkBlockColors'
vtkBlockColorsTF2D = GetTransferFunction2D('vtkBlockColors')

# set scalar coloring
ColorBy(noisesiloDisplay, ('POINTS', 'hardyglobal'))

# Hide the scalar bar for this color map if no visible data is colored by it.
HideScalarBarIfNotNeeded(vtkBlockColorsLUT, renderView1)

# rescale color and/or opacity maps used to include current data range
noisesiloDisplay.RescaleTransferFunctionToDataRange(True, False)

# show color bar/color legend
noisesiloDisplay.SetScalarBarVisibility(renderView1, True)

# get color transfer function/color map for 'hardyglobal'
hardyglobalLUT = GetColorTransferFunction('hardyglobal')

# get opacity transfer function/opacity map for 'hardyglobal'
hardyglobalPWF = GetOpacityTransferFunction('hardyglobal')

# create a new 'Contour'
contour1 = Contour(registrationName='Contour1', Input=noisesilo)
contour1.ContourBy = ['POINTS', 'hardyglobal']
contour1.Isosurfaces = [3.49259752035141]
contour1.PointMergeMethod = 'Uniform Binning'

# Properties modified on contour1
contour1.Isosurfaces = [1.0955432653427124, 1.6282219886779785, 2.1609007120132446, 2.6935794353485107, 3.226258158683777, 3.758936882019043, 4.291615605354309, 4.824294328689575, 5.356973052024841, 5.889651775360107]

# show data in view
contour1Display = Show(contour1, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
contour1Display.Representation = 'Surface'
contour1Display.ColorArrayName = ['POINTS', 'hardyglobal']
contour1Display.LookupTable = hardyglobalLUT
contour1Display.SelectTCoordArray = 'None'
contour1Display.SelectNormalArray = 'Normals'
contour1Display.SelectTangentArray = 'None'
contour1Display.OSPRayScaleArray = 'hardyglobal'
contour1Display.OSPRayScaleFunction = 'PiecewiseFunction'
contour1Display.SelectOrientationVectors = 'None'
contour1Display.ScaleFactor = 2.0
contour1Display.SelectScaleArray = 'hardyglobal'
contour1Display.GlyphType = 'Arrow'
contour1Display.GlyphTableIndexArray = 'hardyglobal'
contour1Display.GaussianRadius = 0.1
contour1Display.SetScaleArray = ['POINTS', 'hardyglobal']
contour1Display.ScaleTransferFunction = 'PiecewiseFunction'
contour1Display.OpacityArray = ['POINTS', 'hardyglobal']
contour1Display.OpacityTransferFunction = 'PiecewiseFunction'
contour1Display.DataAxesGrid = 'GridAxesRepresentation'
contour1Display.PolarAxes = 'PolarAxesRepresentation'

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
contour1Display.ScaleTransferFunction.Points = [1.6282219886779785, 0.0, 0.5, 0.0, 5.889651775360107, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
contour1Display.OpacityTransferFunction.Points = [1.6282219886779785, 0.0, 0.5, 0.0, 5.889651775360107, 1.0, 0.5, 0.0]

# hide data in view
Hide(noisesilo, renderView1)

# show color bar/color legend
contour1Display.SetScalarBarVisibility(renderView1, True)

# update the view to ensure updated data information
renderView1.Update()

# get layout
layout1 = GetLayout()

# layout/tab size in pixels
layout1.SetSize(2027, 1268)

# current camera placement for renderView1
renderView1.CameraPosition = [49.0381653030622, 3.083657606729836, -45.433581947240924]
renderView1.CameraViewUp = [-0.018686825287978125, 0.9986910201150085, 0.047613536964819486]
renderView1.CameraParallelScale = 17.320508075688775

# save screenshot
SaveScreenshot(fileDir + '/ex03_contour.png', renderView1, ImageResolution=[4054, 2536])


print("\nFinished ParaView example script\n")
