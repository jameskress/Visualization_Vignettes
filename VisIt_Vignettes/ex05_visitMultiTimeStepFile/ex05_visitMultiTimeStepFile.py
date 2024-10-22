#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import os
import sys
# import visit_utils, we will use it to help encode our movie
from visit_utils import *

print("Running VisIt example script: ", sys.argv[0], "\n")

#
# Get directory of this script
#
script_dir = os.path.abspath( os.path.dirname( __file__ ) )
print("Running script from: ",  script_dir )

#
# Open the compute engine if running on cluster
#
if len(sys.argv)  < 4:
    print("Running script locally, not launching a batch job\n")
elif sys.argv[4] == "shaheen":
    OpenComputeEngine("localhost",("-l", "srun",
                                   "-p", sys.argv[1], 
                                   "-nn", sys.argv[2],
                                   "-np", sys.argv[3],
                                   "-t", sys.argv[4]))

elif sys.argv[4] == "ibex":
    OpenComputeEngine("localhost",("-l", "srun",
                                   "-p", "batch",
                                   "-nn", sys.argv[1],
                                   "-np", sys.argv[2],
                                   "-t", sys.argv[3]))

#
# Open file and add basic plot
#
dataFile = script_dir + "/../../data/varying.visit"
OpenDatabase("localhost:" + dataFile, 0)
AddPlot("Pseudocolor", "temp", 1, 0)
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
encoding.encode(input_pattern,output_movie,fdup=4)


print("\nFinished VisIt example script\n")

# If on Windows wait for user input so that output does not disapear
if os.name == 'nt':
    input("Press any key to close")
exit()
