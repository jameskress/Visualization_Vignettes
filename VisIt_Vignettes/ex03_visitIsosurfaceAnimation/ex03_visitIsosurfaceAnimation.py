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

# Get directory of this script
script_dir = os.path.abspath( os.path.dirname( __file__ ) )
print("Running script from: ",  script_dir )

# Open the compute engine if running on cluster
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



# Open file and add basic plot
dataFile = script_dir + "/../../data/noise.silo"
OpenDatabase("localhost:" + dataFile, 0)
AddPlot("Pseudocolor", "hardyglobal", 1, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)

# Create the isosurface
iso_atts = IsosurfaceAttributes()
iso_atts.contourMethod = iso_atts.Value
iso_atts.variable = "hardyglobal"
AddOperator("Isosurface")
DrawPlots()


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
# change where images are saved
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass
swatts.outputToCurrentDirectory = 0
swatts.outputDirectory = saveDir
    

for i in range(35):
    iso_atts.contourValue = (2 + 0.1*i)
    SetOperatorOptions(iso_atts)
    swatts.fileName = "ex03_visit_%04d.png" % i
    SetSaveWindowAttributes(swatts)
    
    print("Saving Image ", i, " of 35")
    
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
input_pattern = script_dir + "/output/ex03_visit_%04d.png"
output_movie = script_dir + "/ex03_visit.mp4"
encoding.encode(input_pattern,output_movie,fdup=4)


print("\nFinished VisIt example script\n")

# If on Windows wait for user input so that output does not disapear
if os.name == 'nt':
    input("Press any key to close")
exit()
