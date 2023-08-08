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

# create a new 'Sphere'
sphere1 = Sphere(registrationName='Sphere1')

# set active source
SetActiveSource(sphere1)

# get active view
renderView1 = GetActiveViewOrCreate('RenderView')

# show data in view
sphere1Display = Show(sphere1, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
sphere1Display.Representation = 'Surface'
sphere1Display.ColorArrayName = [None, '']
sphere1Display.SelectTCoordArray = 'None'
sphere1Display.SelectNormalArray = 'Normals'
sphere1Display.SelectTangentArray = 'None'
sphere1Display.OSPRayScaleArray = 'Normals'
sphere1Display.OSPRayScaleFunction = 'PiecewiseFunction'
sphere1Display.SelectOrientationVectors = 'None'
sphere1Display.ScaleFactor = 0.1
sphere1Display.SelectScaleArray = 'None'
sphere1Display.GlyphType = 'Arrow'
sphere1Display.GlyphTableIndexArray = 'None'
sphere1Display.GaussianRadius = 0.005
sphere1Display.SetScaleArray = ['POINTS', 'Normals']
sphere1Display.ScaleTransferFunction = 'PiecewiseFunction'
sphere1Display.OpacityArray = ['POINTS', 'Normals']
sphere1Display.OpacityTransferFunction = 'PiecewiseFunction'
sphere1Display.DataAxesGrid = 'GridAxesRepresentation'
sphere1Display.PolarAxes = 'PolarAxesRepresentation'

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
sphere1Display.ScaleTransferFunction.Points = [-0.9749279022216797, 0.0, 0.5, 0.0, 0.9749279022216797, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
sphere1Display.OpacityTransferFunction.Points = [-0.9749279022216797, 0.0, 0.5, 0.0, 0.9749279022216797, 1.0, 0.5, 0.0]

# get the material library
materialLibrary1 = GetMaterialLibrary()

# reset view to fit data
renderView1.ResetCamera(False)

# set scalar coloring
ColorBy(sphere1Display, ('POINTS', 'Normals', 'Magnitude'))

# rescale color and/or opacity maps used to include current data range
sphere1Display.RescaleTransferFunctionToDataRange(True, False)

# show color bar/color legend
sphere1Display.SetScalarBarVisibility(renderView1, True)

# get color transfer function/color map for 'Normals'
normalsLUT = GetColorTransferFunction('Normals')

# get opacity transfer function/opacity map for 'Normals'
normalsPWF = GetOpacityTransferFunction('Normals')

# Properties modified on sphere1
sphere1.ThetaResolution = 50
sphere1.PhiResolution = 50

# show data in view
sphere1Display = Show(sphere1, renderView1, 'GeometryRepresentation')

# reset view to fit data
renderView1.ResetCamera(False)

# show color bar/color legend
sphere1Display.SetScalarBarVisibility(renderView1, True)

# update the view to ensure updated data information
renderView1.Update()

# Rescale transfer function
normalsLUT.RescaleTransferFunction(0.9999999650440644, 1.0000000378054452)

# Rescale transfer function
normalsPWF.RescaleTransferFunction(0.9999999650440644, 1.0000000378054452)

# create a new 'Ellipse'
ellipse1 = Ellipse(registrationName='Ellipse1')

# set active source
SetActiveSource(ellipse1)

# show data in view
ellipse1Display = Show(ellipse1, renderView1, 'GeometryRepresentation')

# trace defaults for the display properties.
ellipse1Display.Representation = 'Surface'
ellipse1Display.ColorArrayName = [None, '']
ellipse1Display.SelectTCoordArray = 'Texture Coordinates'
ellipse1Display.SelectNormalArray = 'None'
ellipse1Display.SelectTangentArray = 'None'
ellipse1Display.OSPRayScaleArray = 'Texture Coordinates'
ellipse1Display.OSPRayScaleFunction = 'PiecewiseFunction'
ellipse1Display.SelectOrientationVectors = 'None'
ellipse1Display.ScaleFactor = 0.2
ellipse1Display.SelectScaleArray = 'None'
ellipse1Display.GlyphType = 'Arrow'
ellipse1Display.GlyphTableIndexArray = 'None'
ellipse1Display.GaussianRadius = 0.01
ellipse1Display.SetScaleArray = ['POINTS', 'Texture Coordinates']
ellipse1Display.ScaleTransferFunction = 'PiecewiseFunction'
ellipse1Display.OpacityArray = ['POINTS', 'Texture Coordinates']
ellipse1Display.OpacityTransferFunction = 'PiecewiseFunction'
ellipse1Display.DataAxesGrid = 'GridAxesRepresentation'
ellipse1Display.PolarAxes = 'PolarAxesRepresentation'

# init the 'PiecewiseFunction' selected for 'ScaleTransferFunction'
ellipse1Display.ScaleTransferFunction.Points = [0.0, 0.0, 0.5, 0.0, 0.9900000095367432, 1.0, 0.5, 0.0]

# init the 'PiecewiseFunction' selected for 'OpacityTransferFunction'
ellipse1Display.OpacityTransferFunction.Points = [0.0, 0.0, 0.5, 0.0, 0.9900000095367432, 1.0, 0.5, 0.0]

# set scalar coloring
ColorBy(ellipse1Display, ('POINTS', 'Texture Coordinates', 'Magnitude'))

# rescale color and/or opacity maps used to include current data range
ellipse1Display.RescaleTransferFunctionToDataRange(True, False)

# show color bar/color legend
ellipse1Display.SetScalarBarVisibility(renderView1, True)

# get color transfer function/color map for 'TextureCoordinates'
textureCoordinatesLUT = GetColorTransferFunction('TextureCoordinates')

# get opacity transfer function/opacity map for 'TextureCoordinates'
textureCoordinatesPWF = GetOpacityTransferFunction('TextureCoordinates')

# get animation scene
animationScene1 = GetAnimationScene()

# Properties modified on animationScene1
animationScene1.NumberOfFrames = 100

# get the time-keeper
timeKeeper1 = GetTimeKeeper()

# find source
sphere1 = FindSource('Sphere1')

# get animation track
sphere1RadiusTrack = GetAnimationTrack('Opacity', index=0, proxy=sphere1)

# create keyframes for this animation track

# create a key frame
keyFrame9780 = CompositeKeyFrame()

# create a key frame
keyFrame9781 = CompositeKeyFrame()
keyFrame9781.KeyTime = 1.0
keyFrame9781.KeyValues = [1]

# initialize the animation track
sphere1RadiusTrack.KeyFrames = [keyFrame9780, keyFrame9781]


# get camera animation track for the view
cameraAnimationCue1 = GetCameraTrack(view=renderView1)

# create keyframes for this animation track

# create a key frame
keyFrame9743 = CameraKeyFrame()
keyFrame9743.Position = [0.5124365190760701, 2.8822860147173808, -2.7993943857293186]
keyFrame9743.FocalPoint = [0.12770339338804743, 0.11923099262182896, 0.12926511875899183]
keyFrame9743.ViewUp = [0.034049744214794064, -0.7291798571869401, -0.683474469743926]
keyFrame9743.ParallelScale = 0.8651599216465272
keyFrame9743.PositionPathPoints = [0.512437, 2.88229, -2.79939, 3.4534138309192324, 1.6447078576480396, -1.3325316771377511, 3.789516440030557, -0.7375065245330701, 1.2257328306683681, 1.2676527074293706, -2.4704971284433612, 2.9489781699546547, -2.213162539590435, -2.2492866827724, 2.539565452439721, -4.031804424331723, -0.24045116498116842, 0.3057908049097702, -2.8187985140505947, 2.0433153072567536, -2.070267902346319]
keyFrame9743.FocalPathPoints = [0.0, 0.0, 0.0]
keyFrame9743.ClosedPositionPath = 1

# create a key frame
keyFrame9744 = CameraKeyFrame()
keyFrame9744.KeyTime = 1.0
keyFrame9744.Position = [0.5124365190760701, 2.8822860147173808, -2.7993943857293186]
keyFrame9744.FocalPoint = [0.12770339338804743, 0.11923099262182896, 0.12926511875899183]
keyFrame9744.ViewUp = [0.034049744214794064, -0.7291798571869401, -0.683474469743926]
keyFrame9744.ParallelScale = 0.8651599216465272

# initialize the animation track
cameraAnimationCue1.Mode = 'Path-based'
cameraAnimationCue1.KeyFrames = [keyFrame9743, keyFrame9744]

# get layout
layout1 = GetLayout()

# layout/tab size in pixels
layout1.SetSize(2027, 1268)

# current camera placement for renderView1
renderView1.CameraPosition = [0.5124365190760701, 2.8822860147173808, -2.7993943857293186]
renderView1.CameraFocalPoint = [0.12770339338804743, 0.11923099262182896, 0.12926511875899183]
renderView1.CameraViewUp = [0.034049744214794064, -0.7291798571869401, -0.683474469743926]
renderView1.CameraParallelScale = 0.8651599216465272


# create folder to store images
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass


# save animation
SaveAnimation(saveDir + '/ex02_pv_png_sequence.png', renderView1, ImageResolution=[4054, 2536],
    FrameWindow=[0, 99])

# layout/tab size in pixels
layout1.SetSize(2027, 1268)

# current camera placement for renderView1
renderView1.CameraPosition = [0.512437, 2.88229, -2.79939]
renderView1.CameraViewUp = [0.034049744214794064, -0.7291798571869401, -0.683474469743926]
renderView1.CameraParallelScale = 0.8651599216465272

# ffmpeg create video
imageLoc = saveDir + '/ex02_pv_png_sequence.%04d.png'
movieLoc = script_dir + '/ex02_pvAnimationout.mp4'
cmd = 'ffmpeg -f image2 -framerate 6 -i ' + imageLoc + ' -qmin 1 -qmax 2 -g 100 -an -vcodec mpeg4 -flags +mv4+aic ' + movieLoc
subprocess.call(cmd, shell=True)

print("\nFinished ParaView example script\n")
