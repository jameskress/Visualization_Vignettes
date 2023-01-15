#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys

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
exit()
