#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys
import pathlib
from paraview.simple import *
paraview.simple._DisableFirstRenderCameraReset()

print("Running ParaView example script: ", sys.argv[0], "\n")

#Create a simple cone object
cone = Cone()

# get active view
renderView1 = GetActiveViewOrCreate('RenderView')
renderView1.ViewSize = [2048, 2048]

# get directory where script is stored
fileDir = str(pathlib.Path(__file__).parent.resolve())

# show data in view
cone1Display = Show(cone, renderView1)
SaveScreenshot(fileDir + "/ex01_pvScreenshot.png", renderView1)

print("\nFinished ParaView example script\n")
