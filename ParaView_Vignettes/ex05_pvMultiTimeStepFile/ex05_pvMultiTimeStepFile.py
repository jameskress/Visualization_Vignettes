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
renderView1.ViewSize = [2082, 924]
renderView1.AxesGrid = 'GridAxes3DActor'
renderView1.StereoType = 'Crystal Eyes'
renderView1.CameraPosition = [-40.02967480143397, -19.396555422671625, 49.99859740142211]
renderView1.CameraViewUp = [0.22243375416581943, -0.9557185249379747, -0.1926793349014932]
renderView1.CameraFocalDisk = 1.0
renderView1.CameraParallelScale = 17.320508075688775
renderView1.OSPRayMaterialLibrary = materialLibrary1

SetActiveView(None)

# ----------------------------------------------------------------
# setup view layouts
# ----------------------------------------------------------------

# create new layout object 'Layout #1'
layout1 = CreateLayout(name='Layout #1')
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
varying00vtk = LegacyVTKReader(registrationName='varying00.vtk*', FileNames=[
script_dir + '/../../data/varying_data/varying00.vtk', script_dir + '/../../data/varying_data/varying01.vtk', script_dir  + '/../../data/varying_data/varying02.vtk', script_dir  + '/../../data/varying_data/varying03.vtk', script_dir  + '/../../data/varying_data/varying04.vtk', script_dir  + '/../../data/varying_data/varying05.vtk', script_dir  + '/../../data/varying_data/varying06.vtk', script_dir  + '/../../data/varying_data/varying07.vtk', script_dir  + '/../../data/varying_data/varying08.vtk', script_dir  + '/../../data/varying_data/varying09.vtk', script_dir  + '/../../data/varying_data/varying10.vtk', script_dir  + '/../../data/varying_data/varying11.vtk', script_dir  + '/../../data/varying_data/varying12.vtk', script_dir  + '/../../data/varying_data/varying13.vtk', script_dir  + '/../../data/varying_data/varying14.vtk', script_dir  + '/../../data/varying_data/varying15.vtk', script_dir  + '/../../data/varying_data/varying16.vtk', script_dir  + '/../../data/varying_data/varying17.vtk', script_dir  + '/../../data/varying_data/varying18.vtk', script_dir  + '/../../data/varying_data/varying19.vtk'])

# ----------------------------------------------------------------
# setup the visualization in view 'renderView1'
# ----------------------------------------------------------------

# show data from varying00vtk
varying00vtkDisplay = Show(varying00vtk, renderView1, 'UniformGridRepresentation')

# get 2D transfer function for 'temp'
tempTF2D = GetTransferFunction2D('temp')
tempTF2D.ScalarRangeInitialized = 1
tempTF2D.Range = [1.779039978981018, 27.403499603271484, 0.0, 1.0]

# get color transfer function/color map for 'temp'
tempLUT = GetColorTransferFunction('temp')
tempLUT.TransferFunction2D = tempTF2D
tempLUT.RGBPoints = [1.779039978981018, 0.231373, 0.298039, 0.752941, 14.591269791126251, 0.865003, 0.865003, 0.865003, 27.403499603271484, 0.705882, 0.0156863, 0.14902]
tempLUT.ScalarRangeInitialized = 1.0

# get opacity transfer function/opacity map for 'temp'
tempPWF = GetOpacityTransferFunction('temp')
tempPWF.Points = [1.779039978981018, 0.0, 0.5, 0.0, 27.403499603271484, 1.0, 0.5, 0.0]
tempPWF.ScalarRangeInitialized = 1

# trace defaults for the display properties.
varying00vtkDisplay.Representation = 'Surface'
varying00vtkDisplay.ColorArrayName = ['POINTS', 'temp']
varying00vtkDisplay.LookupTable = tempLUT
varying00vtkDisplay.SelectTCoordArray = 'None'
varying00vtkDisplay.SelectNormalArray = 'None'
varying00vtkDisplay.SelectTangentArray = 'None'
varying00vtkDisplay.OSPRayScaleArray = 'temp'
varying00vtkDisplay.OSPRayScaleFunction = 'PiecewiseFunction'
varying00vtkDisplay.SelectOrientationVectors = 'None'
varying00vtkDisplay.ScaleFactor = 2.0
varying00vtkDisplay.SelectScaleArray = 'temp'
varying00vtkDisplay.GlyphType = 'Arrow'
varying00vtkDisplay.GlyphTableIndexArray = 'temp'
varying00vtkDisplay.GaussianRadius = 0.1
varying00vtkDisplay.SetScaleArray = ['POINTS', 'temp']
varying00vtkDisplay.ScaleTransferFunction = 'PiecewiseFunction'
varying00vtkDisplay.OpacityArray = ['POINTS', 'temp']
varying00vtkDisplay.OpacityTransferFunction = 'PiecewiseFunction'
varying00vtkDisplay.DataAxesGrid = 'GridAxesRepresentation'
varying00vtkDisplay.PolarAxes = 'PolarAxesRepresentation'
varying00vtkDisplay.ScalarOpacityUnitDistance = 0.7069595132934193
varying00vtkDisplay.ScalarOpacityFunction = tempPWF
varying00vtkDisplay.TransferFunction2D = tempTF2D
varying00vtkDisplay.OpacityArrayName = ['POINTS', 'temp']
varying00vtkDisplay.ColorArray2Name = ['POINTS', 'temp']
varying00vtkDisplay.IsosurfaceValues = [14.591269791126251]
varying00vtkDisplay.SliceFunction = 'Plane'
varying00vtkDisplay.Slice = 24
varying00vtkDisplay.SelectInputVectors = [None, '']
varying00vtkDisplay.WriteLog = ''

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
varying00vtkDisplay.ScaleTransferFunction.Points = [1.779039978981018, 0.0, 0.5, 0.0, 27.403499603271484, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
varying00vtkDisplay.OpacityTransferFunction.Points = [1.779039978981018, 0.0, 0.5, 0.0, 27.403499603271484, 1.0, 0.5, 0.0]

# setup the color legend parameters for each legend in this view

# get color legend/bar for tempLUT in view renderView1
tempLUTColorBar = GetScalarBar(tempLUT, renderView1)
tempLUTColorBar.Title = 'temp'
tempLUTColorBar.ComponentTitle = ''

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
jPG1 = CreateExtractor('JPG', renderView1, registrationName='JPG1')
# trace defaults for the extractor.
jPG1.Trigger = 'TimeStep'

# init the 'JPG' selected for 'Writer'
jPG1.Writer.FileName = 'ex05_{timestep:06d}.jpg'
jPG1.Writer.ImageResolution = [2082, 924]
jPG1.Writer.Format = 'JPEG'

# ----------------------------------------------------------------
# restore active source
SetActiveSource(jPG1)
# ----------------------------------------------------------------


if __name__ == '__main__':
    # generate extracts
    SaveExtracts(ExtractsOutputDirectory='extracts')


# ffmpeg create video
imageLoc = script_dir + '/extracts/ex05_%06d.jpg'
movieLoc = script_dir + '/ex05_pvMultiTimeSteps.mp4'
cmd = 'ffmpeg -f image2 -framerate 6 -i ' + imageLoc + ' -qmin 1 -qmax 2 -g 100 -an -vcodec mpeg4 -flags +mv4+aic ' + movieLoc
subprocess.call(cmd, shell=True)

print("\nFinished ParaView example script\n")
