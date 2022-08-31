#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys
# import visit_utils, we will use it to help encode our movie
from visit_utils import *

print("Running VisIt example script: ", sys.argv[0], "\n")

# Open the compute engine
OpenComputeEngine("localhost",("-l", "mpirun",
                               "-p", "batch",
                               "-nn", sys.argv[1],
                               "-np", sys.argv[2],
                               "-t", sys.argv[3]))

def fly(): 
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
    
    # Create the control points for the views.
    c0 = View3DAttributes()
    c0.viewNormal = (0, 0, 1)
    c0.focus = (0, 0, 0)
    c0.viewUp = (0, 1, 0)
    c0.viewAngle = 30
    c0.parallelScale = 17.3205
    c0.nearPlane = 17.3205
    c0.farPlane = 81.9615
    c0.perspective = 1
 
    c1 = View3DAttributes()
    c1.viewNormal = (-0.499159, 0.475135, 0.724629)
    c1.focus = (0, 0, 0)
    c1.viewUp = (0.196284, 0.876524, -0.439521)
    c1.viewAngle = 30
    c1.parallelScale = 14.0932
    c1.nearPlane = 15.276
    c1.farPlane = 69.917
    c1.perspective = 1
 
    c2 = View3DAttributes()
    c2.viewNormal = (-0.522881, 0.831168, -0.189092)
    c2.focus = (0, 0, 0)
    c2.viewUp = (0.783763, 0.556011, 0.27671)
    c2.viewAngle = 30
    c2.parallelScale = 11.3107
    c2.nearPlane = 14.8914
    c2.farPlane = 59.5324
    c2.perspective = 1
 
    c3 = View3DAttributes()
    c3.viewNormal = (-0.438771, 0.523661, -0.730246)
    c3.focus = (0, 0, 0)
    c3.viewUp = (-0.0199911, 0.80676, 0.590541)
    c3.viewAngle = 30
    c3.parallelScale = 8.28257
    c3.nearPlane = 3.5905
    c3.farPlane = 48.2315
    c3.perspective = 1
 
    c4 = View3DAttributes()
    c4.viewNormal = (0.286142, -0.342802, -0.894768)
    c4.focus = (0, 0, 0)
    c4.viewUp = (-0.0382056, 0.928989, -0.36813)
    c4.viewAngle = 30
    c4.parallelScale = 10.4152
    c4.nearPlane = 1.5495
    c4.farPlane = 56.1905
    c4.perspective = 1
 
    c5 = View3DAttributes()
    c5.viewNormal = (0.974296, -0.223599, -0.0274086)
    c5.focus = (0, 0, 0)
    c5.viewUp = (0.222245, 0.97394, -0.0452541)
    c5.viewAngle = 30
    c5.parallelScale = 1.1052
    c5.nearPlane = 24.1248
    c5.farPlane = 58.7658
    c5.perspective = 1
 
    c6 = c0
 
    # Create a tuple of camera values and x values. The x values are weights
    # that help to determine where in [0,1] the control points occur.
    cpts = (c0, c1, c2, c3, c4, c5, c6)
    x=[]
    for i in range(7):
        x = x + [float(i) / float(6.)]
 
    # Animate the camera. Note that we use the new built-in EvalCubicSpline
    # function which takes a t value from [0,1] a tuple of t values and a tuple
    # of control points. In this case, the control points are View3DAttributes
    # objects that we are using to animate the camera but they can be any object
    # that supports +, * operators.
    nsteps = 100
    for i in range(nsteps):
        t = float(i) / float(nsteps - 1)
        c = EvalCubicSpline(t, x, cpts)
        c.nearPlane = -34.461
        c.farPlane = 34.461
        SetView3D(c)
        swatts.fileName = "ex02_visit_%04d.png" % i
        SetSaveWindowAttributes(swatts)
        SaveWindow()


# Open file and add basic plot
OpenDatabase("localhost:../data/noise.silo", 0)
AddPlot("Pseudocolor", "hardyglobal", 1, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)
DrawPlots()

fly()


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
input_pattern = "ex02_visit_%04d.png"
output_movie = "ex02_visit.mp4"
encoding.encode(input_pattern,output_movie,fdup=4)


print("\nFinished VisIt example script\n")
exit()
