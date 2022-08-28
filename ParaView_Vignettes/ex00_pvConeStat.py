#
# KAUST Visualization Vignettes
#     ParaView example script
#
import sys
from paraview.simple import *

print("Running ParaView example script: ", sys.argv[0], "\n")

#Create a simple cone object and query it's properties
cone = Cone()
print("Cone Resolution: ", cone.Resolution)
print("Cone Height:     ", cone.Height)
print("Cone Radius:     ", cone.Radius)
print("Cone Center:     ", cone.Center)
print("Cone Direction:  ", cone.Direction)

print("\nFinished ParaView example script\n")
