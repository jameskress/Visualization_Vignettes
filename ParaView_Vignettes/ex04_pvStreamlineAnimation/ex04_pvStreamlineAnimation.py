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

print("\nFinished ParaView example script\n")
