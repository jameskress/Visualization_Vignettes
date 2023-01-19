#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
import sys
import os
import subprocess
from os.path import join as pjoin
import visit
import json
import math
from visit_flow.core import *
from visit_flow.filters import file_ops, imagick, cmd
from visit_utils import *
from visit_utils.qannote import *
from visit_utils.qannote.items import Rect
import visit_utils.builtin 
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
    meta_data = GetMetaData(databaseName)
    times    = meta_data.GetTimes()
    QueryOverTime("Volume", end_time=len(times), start_time=0, stride=1)

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
    QueryOverTime("3D surface area", end_time=len(times), start_time=0, stride=1)

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
    def render_volume_plot(output_base, time_step, time, numTimeSteps):
        curve_name = pjoin(output_dir, "volume.curve")
        n_curves  = 1
        curves = [PropertyTree() for i in range(n_curves)]
        curves[0].file = curve_name
        curves[0].index = 0

        p = PropertyTree()
        p.size = (800, 350)
        # This sets the range of the displayed data values on x, y
        p.view = (0., numTimeSteps, -100., 1250.)
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
    def render_surface_plot(output_base, time_step, time, numTimeSteps):
        curve_name = pjoin(output_dir, "surface.curve")
        n_curves  = 1
        curves = [PropertyTree() for i in range(n_curves)]
        curves[0].file = curve_name
        curves[0].index = 0

        p = PropertyTree()
        p.size = (800, 350)
        # This sets the range of the displayed data values on x, y
        p.view = (0., numTimeSteps, -100., 1000.)
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
        render_volume_plot(volume_base, time_step, time, len(times))

    # Create the surface curve images.
    surface_dir = pjoin(output_dir, "surface_curve")
    surface_base = pjoin(surface_dir, "surface%04d.png")
    if not os.path.isdir(surface_dir):
        os.mkdir(surface_dir)
    for time_step in range (0, len(times)):
        time = times[time_step]
        render_surface_plot(surface_base, time_step, time, len(times))



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
    movieName = pjoin(outputDir, "blobs_raw.mp4")
    encoding.encode(outputBase, movieName, fdup=10)

    DeleteAllPlots()
    closeFile(databaseName)

    return


def composite():
    w = Workspace()
    w.register_filters(file_ops)
    w.register_filters(imagick)
    w.register_filters(cmd)
    ctx = w.add_context("imagick", "root")

    output_width = 2048
    output_height = 1920
    plots_width = 800
    plots_height = 350
    n_time_states = 20

    #
    # Set up some path information.
    #
    output_dir = "output"

    blobs_base    = pjoin(os.path.abspath("."), output_dir, "time_animation", "blobs%04d.png")
    volume_base  = pjoin(os.path.abspath("."), output_dir, "volume_curve", "volume%04d.png")
    surface_base = pjoin(os.path.abspath("."), output_dir, "surface_curve", "surface%04d.png")

    #
    # Create the output directory structure.
    #
    comp_dir    = pjoin(output_dir, "composite_animation")
    comp_tmp_dir = pjoin(output_dir, "_tmp")

    if not os.path.isdir(comp_dir):
        os.mkdir(comp_dir)
    if not os.path.isdir(comp_tmp_dir):
        os.mkdir(comp_tmp_dir)
    ctx.set_working_dir(comp_tmp_dir)

    output_base = pjoin(comp_dir, "blobs.%dx%d.%s.png" % (output_width, output_height, "%04d"))

    #
    # Create the data flow network. Note that we must use the name "svec"
    # below for things to work properly.
    #
    state_vector = StateVectorGenerator(StateSpace({"index": n_time_states}))
    svec = state_vector

    ctx.add_filter("fill", "background", {"width": output_width, "height": output_height, "color": "black"})
    ctx.add_filter("fill", "black_bar", {"width": output_width, "height": plots_height, "color": "black"})

    ctx.add_filter("over", "blobs_over")

    ctx.add_filter("over", "black_bar_over", {"x": 0, "y": 1400})
    ctx.add_filter("over", "volume_over", {"x": 200, "y": 1400})
    ctx.add_filter("over", "surface_over", {"x": 1000, "y": 1400})

    ctx.add_filter("file_name", "blobs_file", {"pattern": blobs_base})
    ctx.add_filter("file_name", "volume_file", {"pattern": volume_base})
    ctx.add_filter("file_name", "surface_file", {"pattern": surface_base})

    python_command = "visit -ni -nowin -cli -s"
    annotate_script = pjoin(os.path.abspath("."), "scripts", "annotate.py")
    ctx.add_filter("cmd", "annotate",
        {"cmd": "%s %s {index}" % (python_command, annotate_script),
         "obase": pjoin(comp_tmp_dir, "annotate_comp_%s.png")})

    ctx.add_filter("file_rename", "rename", {"pattern": output_base})

    w.connect("background", "blobs_over:under")
    w.connect("blobs_file", "blobs_over:over")

    w.connect("blobs_over", "black_bar_over:under")
    w.connect("black_bar", "black_bar_over:over")

    w.connect("black_bar_over", "volume_over:under")
    w.connect("volume_file", "volume_over:over")

    w.connect("volume_over", "surface_over:under")
    w.connect("surface_file", "surface_over:over")

    w.connect("surface_over", "annotate:in")

    w.connect("annotate", "rename:in")

    #
    # Execute the data flow network.
    #
    w.execute(svec)
    return


def createTitle():
    AUSPICES_TEXT  = "This work was performed under the auspices of the KAUST "
    AUSPICES_TEXT += "Visualization Core Laboratory (KVL)"

    images_dir = "images"
    output_dir = "output"

    width = 2048
    height = 1920

    def create_text_box(text, x_offset, y_offset, width, height, font_size,
        foreground, background):
        items = [
                TextBox( {"x": x_offset, "y": y_offset,
                          "width": width, "height": height,
                          "fg_color": foreground,
                          "text": text,
                          "font/bold": False,
                          "font/size": font_size})
                ]
        return items

    def title_items(foreground, background):
        # These images need to be in *.png format
        core_logo = pjoin(images_dir, "coreLabs.png")
        kvl_logo = pjoin(images_dir, "kvl.png")
        kaust_logo = pjoin(images_dir, "kaust.png")
        items = [
                Rect(  { "x": 0, "y": 0,
                         "width": width, "height": height,
                         "color": background}),
                Image( { "image": kaust_logo,
                         "x": 15, "y": height - 175,
                         "horz_align": "left",
                         "vert_align": "bottom"}),
                Image( { "image": core_logo,
                         "x": 550, "y": height - 175,
                         "horz_align": "left",
                         "vert_align": "bottom"}),
                Image( { "image": kvl_logo,
                         "x": 900, "y": height - 175,
                         "horz_align": "left",
                         "vert_align": "bottom"}),
                Text(  { "text": "KVL-VIDEO-000001",
                         "color": foreground,
                         "x": width - 10, "y": height - 5,
                         "horz_align": "right",
                         "vert_align": "bottom",
                         "font/size": 17}),
                Text(  { "text": "Blobs Flowing Through Space",
                         "color": foreground,
                         "x": width / 2, "y": height * .3,
                         "horz_align": "center",
                         "vert_align": "center",
                         "font/size": 35}),
                Text(  { "text": "VisIt Advanced Movie Making Tutorial",
                         "color": foreground,
                         "x": width / 2, "y": height * .4,
                         "horz_align": "center",
                         "vert_align": "center",
                         "font/size": 35})
                ]
        items.extend(create_text_box(AUSPICES_TEXT,
                                     610, height * .7,
                                     820, 25, 15, foreground, background))
        return items

    def render_title(foreground, background):
        items = title_items(foreground, background)
        output_file = pjoin(output_dir, "title.png")
        Canvas.render(items, (width, height), output_file)

    render_title((255, 255, 255, 255), (0, 0, 0, 255))
    return


def finalMovie():
    def hold(a, output_base, index):
        command = "cp %s %s" % (a, output_base % index)
        common.sexe(command, echo=True)

    def blend(a, b, percent, output_base, index):
        command = "composite %s -blend %f %s %s" % (b, percent, a, output_base % index)
        common.sexe(command, echo=True)

    def resize(a, output_base, percent, index):
        command = "convert %s -resize %d%% %s" % (a, percent, output_base % index)
        common.sexe(command, echo=True)

    #
    # Create the output directory.
    #
    output_dir = "output"
    movie_dir = pjoin(output_dir, "final_movie")
    low_res_movie_dir = pjoin(output_dir, "final_low_res_movie")

    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    if not os.path.isdir(movie_dir):
        os.mkdir(movie_dir)
    if not os.path.isdir(low_res_movie_dir):
        os.mkdir(low_res_movie_dir)

    title_name = pjoin(output_dir, "title.png")
    blobs_base = pjoin(output_dir, "composite_animation", "blobs.2048x1920.%04d.png")
    movie_name = pjoin(output_dir, "blobs_final.2048x1920.mp4")
    low_res_movie_name = pjoin(output_dir, "blobs_final.640x360.mp4")

    output_base = pjoin(movie_dir, "comp.final.%04d.png")
    low_res_output_base = pjoin(low_res_movie_dir, "comp.final.%04d.png")

    #
    # Hold the title.
    #
    index = 0
    for i in range(0, 100):
        hold(title_name, output_base, index)
        index += 1

    #
    # Blend the title to the first movie frame.
    #
    for i in range(0, 50):
        blend(title_name, blobs_base % 0, i * 2, output_base, index)
        index += 1

    #
    # Hold the first frame of the movie.
    #
    for i in range(0, 100):
        hold(blobs_base % 0, output_base, index)
        index += 1

    #
    # Do the movie, duplicating each image.
    #
    for i in range(0, 19):
        for w in range(0, 15):
            hold(blobs_base % i, output_base, index)
            index += 1

    #
    # Hold the last frame of the movie.
    #
    for i in range(0, 100):
        hold(blobs_base % 19, output_base, index)
        index += 1

    #
    # Encode the movie.
    #
    encoding.encode(output_base, movie_name, fdup=1)

    #
    # Encode the low resolution version of the movie.
    #
    for i in range(0, index):
        resize(output_base % i, low_res_output_base, 50, i)

    encoding.encode(low_res_output_base, low_res_movie_name, fdup=1)
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


    animateBlobs("localhost:../../data/varying.visit", "temp")
    createJSON("localhost:../../data/varying.visit", "temp", "output/blobs_times.json")
    createCurves("localhost:../../data/varying.visit", "temp")
    animateCurve()
    composite() # this calls the animage.py script, which is why that code is separate
    createTitle()
    finalMovie()


    print("\nFinished VisIt example script\n")
    exit()
