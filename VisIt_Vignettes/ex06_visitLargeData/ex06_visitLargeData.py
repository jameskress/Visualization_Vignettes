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
script_dir = os.path.abspath(os.path.dirname(__file__))
print("Running script from: ", script_dir)

#
# Open the compute engine if running on cluster
#
if len(sys.argv) < 4:
    print("Running script locally, not launching a batch job\n")
elif sys.argv[4] == "shaheen":
    OpenComputeEngine(
        "localhost",
        (
            "-l",
            "srun",
            "-p",
            sys.argv[1],
            "-nn",
            sys.argv[2],
            "-np",
            sys.argv[3],
            "-t",
            sys.argv[4],
        ),
    )

elif sys.argv[4] == "ibex":
    OpenComputeEngine(
        "localhost",
        (
            "-l",
            "srun",
            "-p",
            "batch",
            "-nn",
            sys.argv[1],
            "-np",
            sys.argv[2],
            "-t",
            sys.argv[3],
        ),
    )

dataFile = script_dir + "/visitCyclone.session"
# wrfFile = script_dir + "/../../data/cyclone-chapala-2015-11-02_00-00-00.vtr"
wrfFile = script_dir + "/../../data/cyclone-chapala-2015-11-02_00-00-00-mb.vtm"
rainFile = script_dir + "/../../data/currentRainfall.silo"
RestoreSessionWithDifferentSources(dataFile, 0, (rainFile, wrfFile))
# RestoreSessionWithDifferentSources("/home/kressjm/data/cyclone.session", 0, ("localhost:/mnt/5d22bac5-b323-4e21-96a7-929039418079/cyclone-chapala-2015-11-02_00-00-00.vtr","localhost:/mnt/5d22bac5-b323-4e21-96a7-929039418079/currentRainfall.vtp"))
# RestoreSession(dataFile, 0)


print("\nWindow one plots")
SetActiveWindow(1)
ListPlots()
DrawPlots()

# set basic save options
swatts = SaveWindowAttributes()
# The 'family' option controls if visit automatically adds a frame number to
# the rendered files.
swatts.family = 0
# select PNG as the output file format
swatts.format = swatts.JPEG
swatts.resConstraint = (
    swatts.NoConstraint
)  # NoConstraint, EqualWidthHeight, ScreenProportions
# set the width of the output image
swatts.width = 2850
# set the height of the output image
swatts.height = 1750
# change where images are saved
saveDir = script_dir + "/output"
try:
    os.mkdir(saveDir)
except FileExistsError:
    pass
swatts.outputToCurrentDirectory = 0
swatts.outputDirectory = saveDir
swatts.fileName = "ex06_visit.png"
SetSaveWindowAttributes(swatts)
SaveWindow()

print("\nFinished VisIt example script\n")

# If on Windows wait for user input so that output does not disapear
if os.name == "nt":
    input("Press any key to close")
exit()
