#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys
import os
from os.path import join as pjoin
import visit
import json
import math
from visit_utils import *
import visit_utils.builtin 
#from PySide2.QtCore import *
#from PySide2.QtWidgets import *
#import visit_utils.builtin.pyside_support as pyside_support
from vtk import *
#from vtk.qt import *
#from PySide.QtUiTools import *
from visit_utils.qplot import *

# open database and do main vis op
def openFile(databaseName, variable):
    # Open the database and create the plots.
    OpenDatabase(databaseName, 0)
    AddPlot("Pseudocolor", variable, 1, 0)
    PseudocolorAtts = PseudocolorAttributes()
    PseudocolorAtts.colorTableName = "hot_desaturated"
    SetPlotOptions(PseudocolorAtts)
    AddOperator("Isovolume", 1)
    SetActivePlots(0)
    IsovolumeAtts = IsovolumeAttributes()
    IsovolumeAtts.lbound = 15
    IsovolumeAtts.ubound = 1e+37
    IsovolumeAtts.variable = variable
    SetOperatorOptions(IsovolumeAtts, 0, 0)
    DrawPlots()

# close an open database
def closeFile(databaseName):
    CloseDatabase(databaseName)


# create a json file with the time for each sim step
def createJSON(databaseName, variable, outputName):
    openFile(databaseName, variable)
    
    # Get the times from the database metadata.
    def get_times(database_name):
        meta_data = GetMetaData(databaseName)
        times    = meta_data.GetTimes()
        return times

    # Create a json file of the times in a database.
    def create_json_file(database_name, output_name, scale=1, shift=0):
        times = get_times(database_name)
        times2 = [times[0] / scale + shift,]
        for i in range(1, len(times)):
            times2.append(times[i] / scale + shift)

        if not output_name is None:
            json.dump(times2, open(output_name, "w"), indent=2)

    # Process the command line options.
    output_name = None
    scale = 1.
    shift = 0.
    create_json_file(databaseName, outputName, scale, shift)
    DeleteAllPlots()
    closeFile(databaseName)
    

# create curve files that contain the points for the volume over time and 
# surface area over time
def createCurves(databaseName, variable):
    # Create the output directory structure.
    outputDir = "output"
    volumeName = pjoin(outputDir, "volume")
    surfaceName = pjoin(outputDir, "surface")

    openFile(databaseName, variable)
    
    #
    # Do the volume query over time.
    #
    SetActiveWindow(1)
    SetQueryFloatFormat("%g")
    QueryOverTime("Volume", end_time=199, start_time=0, stride=1)

    #
    # Save the curve.
    #
    SetActiveWindow(2)
    saveAtts = SaveWindowAttributes()
    saveAtts.outputToCurrentDirectory = 1
    saveAtts.outputDirectory = "."
    saveAtts.fileName = volumeName
    saveAtts.family = 0
    saveAtts.format = saveAtts.CURVE
    saveAtts.width = 1024
    saveAtts.height = 1024
    saveAtts.screenCapture = 0
    saveAtts.saveTiled = 0
    saveAtts.quality = 80
    saveAtts.progressive = 0
    saveAtts.binary = 0
    saveAtts.stereo = 0
    saveAtts.compression = saveAtts.PackBits
    saveAtts.forceMerge = 0
    saveAtts.resConstraint = saveAtts.NoConstraint
    saveAtts.advancedMultiWindowSave = 0
    SetSaveWindowAttributes(saveAtts)
    SaveWindow()
    DeleteAllPlots()

    #
    # Do the surface area over time query.
    #
    SetActiveWindow(1)
    QueryOverTime("3D surface area", end_time=199, start_time=0, stride=1)

    #
    # Save the curve.
    #
    SetActiveWindow(2)
    saveAtts = SaveWindowAttributes()
    saveAtts.outputToCurrentDirectory = 1
    saveAtts.outputDirectory = "."
    saveAtts.fileName = surfaceName
    saveAtts.family = 0
    saveAtts.format = saveAtts.CURVE
    saveAtts.width = 1024
    saveAtts.height = 1024
    saveAtts.screenCapture = 0
    saveAtts.saveTiled = 0
    saveAtts.quality = 80
    saveAtts.progressive = 0
    saveAtts.binary = 0
    saveAtts.stereo = 0
    saveAtts.compression = saveAtts.PackBits
    saveAtts.forceMerge = 0
    saveAtts.resConstraint = saveAtts.NoConstraint
    saveAtts.advancedMultiWindowSave = 0
    SetSaveWindowAttributes(saveAtts)
    SaveWindow()
    DeleteWindow()
    DeleteAllPlots()
    closeFile(databaseName)
    
# create the curve images animated over time
def animateCurve():
    output_dir = "output"

    # Create the images of the volume over time.
    def render_volume_plot(output_base, time_step, time):
        curve_name = pjoin(output_dir, "volume.curve")
        n_curves  = 1
        curves = [PropertyTree() for i in range(n_curves)]
        curves[0].file = curve_name
        curves[0].index = 0

        p = PropertyTree()
        p.size = (600, 250)
        p.view = (0., 200., 10000., 60000.)
        p.axes.x_ticks = 5
        p.axes.y_ticks = 0
        p.bg_color = (0, 0, 0, 255)
        p.axis.tick_width = 2
        p.axis.tick_length = .5
        p.right_margin = 8
        p.left_margin = 10
        p.bottom_margin = 35
        p.top_margin = 6
        p.labels.titles_font.name = "Times New Roman"
        p.labels.titles_font.size = 18
        p.labels.titles_font.bold = True
        p.labels.labels_font.name = "Times New Roman"
        p.labels.labels_font.size = 15
        p.labels.labels_font.bold = True
        p.labels.x_title = "Time  (\\0x03bcs)"
        p.labels.y_title = "Volume"
        p.labels.x_title_offset = 27
        p.labels.y_title_offset = 5
        p.labels.x_labels_offset = 0
        p.labels.y_labels_offset = 2
        p.labels.x_labels = p.axes.x_ticks
        p.labels.y_labels = p.axes.y_ticks
        p.plots = [PropertyTree() for i in range(n_curves)]
        p.plots[0].type = "line"
        p.plots[0].curve = curves[0]
        p.plots[0].color = (0, 185, 50, 255)
        # check for time step in the tracer range
        if time >= p.view[0] and time <= p.view[1]:
            tracer_dot = PropertyTree()
            tracer_dot.curve = curves[0]
            tracer_dot.type = "tracer_dot"
            tracer_dot.color = (0, 185, 50, 255)
            tracer_dot.point_size = 12
            tracer_dot.tracer_x = time
            tracer_line = PropertyTree()
            tracer_line.curve = curves[0]
            tracer_line.type = "tracer_line"
            tracer_line.color = (0, 185, 50, 255)
            tracer_line.tracer_x = time
            p.plots.append(tracer_dot)
            p.plots.append(tracer_line)

        p.annotations = [PropertyTree() for i in range(0)]
        scene = CurveScene(p)
        scene.render(output_base % time_step)
        return (output_base % time_step)

    # Create the images of the surface area over time.
    def render_surface_plot(output_base, time_step, time):
        curve_name = pjoin(output_dir, "surface.curve")
        n_curves  = 1
        curves = [PropertyTree() for i in range(n_curves)]
        curves[0].file = curve_name
        curves[0].index = 0

        p = PropertyTree()
        p.size = (600, 250)
        p.view = (0., 200., 5000., 12000.)
        p.axes.x_ticks = 5
        p.axes.y_ticks = 0
        p.bg_color = (0, 0, 0, 255)
        p.axis.tick_width = 2
        p.axis.tick_length = .5
        p.right_margin = 8
        p.left_margin = 10
        p.bottom_margin = 35
        p.top_margin = 6
        p.labels.titles_font.name = "Times New Roman"
        p.labels.titles_font.size = 18
        p.labels.titles_font.bold = True
        p.labels.labels_font.name = "Times New Roman"
        p.labels.labels_font.size = 15
        p.labels.labels_font.bold = True
        p.labels.x_title = "Time  (\\0x03bcs)"
        p.labels.y_title = "Surface Area"
        p.labels.x_title_offset = 27
        p.labels.y_title_offset = 5
        p.labels.x_labels_offset = 0
        p.labels.y_labels_offset = 2
        p.labels.x_labels = p.axes.x_ticks
        p.labels.y_labels = p.axes.y_ticks
        p.plots = [PropertyTree() for i in range(n_curves)]
        p.plots[0].type = "line"
        p.plots[0].curve = curves[0]
        p.plots[0].color = (180, 0, 50, 255)
        # check for time step in the tracer range
        if time >= p.view[0] and time <= p.view[1]:
            tracer_dot = PropertyTree()
            tracer_dot.curve = curves[0]
            tracer_dot.type = "tracer_dot"
            tracer_dot.color = (180, 0, 50, 255)
            tracer_dot.point_size = 12
            tracer_dot.tracer_x = time
            tracer_line = PropertyTree()
            tracer_line.curve = curves[0]
            tracer_line.type = "tracer_line"
            tracer_line.color = (180, 0, 50, 255)
            tracer_line.tracer_x = time
            p.plots.append(tracer_dot)
            p.plots.append(tracer_line)

        p.annotations = [PropertyTree() for i in range(0)]
        scene = CurveScene(p)
        scene.render(output_base % time_step)
        return (output_base % time_step)

    blobs_times_file = pjoin(output_dir, "blobs_times.json")
    times = json.load(open(blobs_times_file))

    # Create the volume curve images.
    volume_dir = pjoin(output_dir, "volume_curve")
    volume_base = pjoin(volume_dir, "volume%04d.png")
    if not os.path.isdir(volume_dir):
        os.mkdir(volume_dir)
    for time_step in range (0, len(times)):
        time = times[time_step]
        render_volume_plot(volume_base, time_step, time)

    # Create the surface curve images.
    surface_dir = pjoin(output_dir, "surface_curve")
    surface_base = pjoin(surface_dir, "surface%04d.png")
    if not os.path.isdir(surface_dir):
        os.mkdir(surface_dir)
    for time_step in range (0, len(times)):
        time = times[time_step]
        render_surface_plot(surface_base, time_step, time)



# create the main blob animation and save movie
def animateBlobs(databaseName, variable):
    openFile(databaseName, variable)
    
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

    View3DAtts = View3DAttributes()
    View3DAtts.viewNormal = (0.155693, -0.913673, 0.375447)
    View3DAtts.focus = (0, 0, 0)
    View3DAtts.viewUp = (-0.0889586, 0.365569, 0.926524)
    View3DAtts.viewAngle = 30
    View3DAtts.parallelScale = 17.3205
    View3DAtts.nearPlane = -34.641
    View3DAtts.farPlane = 34.641
    View3DAtts.imagePan = (0, 0)
    View3DAtts.imageZoom = 1.21
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
    outputDir = "output"
    timeAnimationDir = pjoin(outputDir, "time_animation")
    outputBase = pjoin(timeAnimationDir, "blobs%04d.png")

    if not os.path.isdir(outputDir):
        os.mkdir(outputDir)
    if not os.path.isdir(timeAnimationDir):
        os.mkdir(timeAnimationDir)

    #
    # Loop over the time states saving an image for each state.
    #
    nTimeSteps = TimeSliderGetNStates()

    for timeStep in range(0, nTimeSteps):
        TimeSliderSetState(timeStep)
        saveAtts.fileName = outputBase % timeStep
        SetSaveWindowAttributes(saveAtts)
        SaveWindow()

    #
    # Encode a movie of the raw images
    #
    movieName = pjoin(outputDir, "blobs_raw.mpg")
    encoding.encode(outputBase, movieName, fdup=10)

    DeleteAllPlots()
    closeFile(databaseName)

    return



if __name__ == '__main__':
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


    #animateBlobs("localhost:../../data/varying.visit", "temp")
    createJSON("localhost:../../data/varying.visit", "temp", "output/blobs_times.json")
    createCurves("localhost:../../data/varying.visit", "temp")
    animateCurve()

    print("\nFinished VisIt example script\n")
    exit()
