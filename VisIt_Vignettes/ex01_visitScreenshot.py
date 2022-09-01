#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys

print("Running VisIt example script: ", sys.argv[0:], "\n")

# Open the compute engine
if sys.argv[4] == "shaheen":
    OpenComputeEngine("localhost",("-l", "srun",
                                   "-nn", sys.argv[1],
                                   "-np", sys.argv[2],
                                   "-t", sys.argv[3]))

else:
    OpenComputeEngine("localhost",("-l", "mpirun",
                                   "-p", "batch",
                                   "-nn", sys.argv[1],
                                   "-np", sys.argv[2],
                                   "-t", sys.argv[3]))


# Open file and add basic plot
OpenDatabase("localhost:../data/noise.silo", 0)
AddPlot("Pseudocolor", "hardyglobal", 1, 0)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
SetPlotOptions(PseudocolorAtts)
DrawPlots()

SaveWindowAtts = SaveWindowAttributes()
SaveWindowAtts.outputToCurrentDirectory = 1
SaveWindowAtts.outputDirectory = "."
SaveWindowAtts.fileName = "ex01_visit"
SaveWindowAtts.family = 1
SaveWindowAtts.format = SaveWindowAtts.PNG  # BMP, CURVE, JPEG, OBJ, PNG, POSTSCRIPT, POVRAY, PPM, RGB, STL, TIFF, ULTRA, VTK, PLY, EXR
SaveWindowAtts.width = 2048
SaveWindowAtts.height = 2048
SaveWindowAtts.screenCapture = 0
SaveWindowAtts.saveTiled = 0
SaveWindowAtts.quality = 80
SaveWindowAtts.progressive = 0
SaveWindowAtts.binary = 0
SaveWindowAtts.stereo = 0
SaveWindowAtts.compression = SaveWindowAtts.NONE  # NONE, PackBits, Jpeg, Deflate, LZW
SaveWindowAtts.forceMerge = 0
SaveWindowAtts.resConstraint = SaveWindowAtts.ScreenProportions  # NoConstraint, EqualWidthHeight, ScreenProportions
SetSaveWindowAttributes(SaveWindowAtts)
SaveWindow()

print("\nFinished VisIt example script\n")
exit()
