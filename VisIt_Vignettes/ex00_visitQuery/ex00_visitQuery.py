#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import os
import sys

print("Running VisIt example script: ", sys.argv[0], "\n")

# Get directory of this script
script_dir = os.path.abspath(os.path.dirname(__file__))
print("Running script from: ", script_dir)

# Open the compute engine if running on cluster
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


# Open file and add basic plot
dataFile = script_dir + "/../../data/noise.silo"
OpenDatabase("localhost:" + dataFile, 0)
AddPlot("Pseudocolor", "hardyglobal", 1, 0)
DrawPlots()

# Query stats about data
SetQueryFloatFormat("%g")
print("\n")
print("3D surface area: ", Query("3D surface area"))
print("Average Value  : ", Query("Average Value"))
print("Centroid:        ", Query("Centroid"))
print("GridInformation: ", Query("Grid Information"))
print("MinMax:          ", Query("MinMax", use_actual_data=1))
print("NumNodes:        ", Query("NumNodes", use_actual_data=1))
print("NumZones:        ", Query("NumZones", use_actual_data=1))
print("Volume:          ", Query("Volume"))

print("\nFinished VisIt example script\n")

# If on Windows wait for user input so that output does not disapear
if os.name == "nt":
    input("Press any key to close")
exit()
