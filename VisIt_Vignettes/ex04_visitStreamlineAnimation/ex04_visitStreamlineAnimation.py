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

# Open the compute engine if running on cluster
if len(sys.argv)  < 4:
    print("Running script locally, not launching a batch job\n")
elif sys.argv[4] == "shaheen":
    OpenComputeEngine("localhost",("-l", "srun",
                                   "-nn", sys.argv[1],
                                   "-np", sys.argv[2],
                                   "-t", sys.argv[3]))

elif sys.argv[4] == "ibex":
    OpenComputeEngine("localhost",("-l", "mpirun",
                                   "-p", "batch",
                                   "-nn", sys.argv[1],
                                   "-np", sys.argv[2],
                                   "-t", sys.argv[3]))


# Open file and add basic plot
OpenDatabase("localhost:../../data/noise.silo", 0)
AddPlot("Pseudocolor", "hardyglobal", 1, 0)
AddOperator("ThreeSlice", 0)
ThreeSliceAtts = ThreeSliceAttributes()
ThreeSliceAtts.x = -10
ThreeSliceAtts.y = -10
ThreeSliceAtts.z = -10
SetOperatorOptions(ThreeSliceAtts, 0, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)
DrawPlots()


# Set a better camera view
ResetView()
View3DAtts = View3DAttributes()
View3DAtts.viewNormal = (0.361327, 0.263368, 0.894472)
View3DAtts.focus = (0, 0, 0)
View3DAtts.viewUp = (-0.0658267, 0.964093, -0.257277)
View3DAtts.viewAngle = 30
View3DAtts.parallelScale = 17.3205
View3DAtts.nearPlane = -34.641
View3DAtts.farPlane = 34.641
View3DAtts.imagePan = (0, 0)
View3DAtts.imageZoom = 1
View3DAtts.perspective = 1
View3DAtts.eyeAngle = 2
View3DAtts.centerOfRotationSet = 0
View3DAtts.centerOfRotation = (0, 0, 0)
View3DAtts.axis3DScaleFlag = 0
View3DAtts.axis3DScales = (1, 1, 1)
View3DAtts.shear = (0, 0, 1)
View3DAtts.windowValid = 1
SetView3D(View3DAtts)

 
# Disable annotations
aatts = AnnotationAttributes()
aatts.axes3D.visible = 0
aatts.axes3D.triadFlag = 0
aatts.axes3D.bboxFlag = 0
aatts.userInfoFlag = 0
aatts.databaseInfoFlag = 0
aatts.legendInfoFlag = 0
SetAnnotationAttributes(aatts)
 

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


# Create a streamline plot that follows the gradient
AddPlot("Pseudocolor", "operators/IntegralCurve/grad", 1, 0)
iatts = IntegralCurveAttributes()
iatts.sourceType = iatts.SpecifiedBox
iatts.sampleDensity0 = 7
iatts.sampleDensity1 = 7
iatts.sampleDensity2 = 7
iatts.dataValue = iatts.SeedPointID
iatts.integrationType = iatts.DormandPrince
iatts.issueStiffnessWarnings = 0
iatts.issueCriticalPointsWarnings = 0
SetOperatorOptions(iatts)
DrawPlots()



# set style of streamlines
patts = PseudocolorAttributes()
patts.lineType = patts.Tube 
patts.tailStyle = patts.Spheres
patts.headStyle = patts.Cones
patts.endPointRadiusBBox = 0.01
SetPlotOptions(patts)
DrawPlots()

 
# Crop streamlines to render them at increasing time values
iatts.cropValue = iatts.Time 
iatts.cropEndFlag = 1
iatts.cropBeginFlag = 1
iatts.cropBegin = 0
for ts in range(0,125):
    # set the integral curve attributes to change the where we crop the streamlines
    iatts.cropEnd = (ts + 1) * .5
    
    # update streamline attributes and draw the plot
    SetOperatorOptions(iatts)
    DrawPlots()
    swatts.fileName = "ex04_visit_%04d.png" % ts
    SetSaveWindowAttributes(swatts)
    SaveWindow()


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
input_pattern = "ex04_visit_%04d.png"
output_movie = "ex04_visit.mp4"
encoding.encode(input_pattern,output_movie,fdup=3)


print("\nFinished VisIt example script\n")
exit()
