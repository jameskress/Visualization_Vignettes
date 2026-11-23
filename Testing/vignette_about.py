"""What each vignette does, in words, for the dashboard and the site pages.

ABOUT: number -> (short title, one sentence). The sentence is the same for
ParaView and VisIt; it appears on the landing page, under each vignette
page's title and in the gallery.

PIPELINE: (tool, number) -> the four parts of that tool's script, in order:
what it reads, what it does, what it writes and what the regression suite
checks. ParaView and VisIt versions of one number do the same exercise, but
not always on the same data, so each gets its own entry.

Keep these in step with the scripts: a claim here that the code does not
make is worse than no description. Terms a reader may not know are defined
where they first appear (isosurface, rank, extract, baseline).
"""

ABOUT = {
    0: (
        "Query",
        "Prints facts about a dataset instead of drawing it; the printout is "
        "compared line by line with a saved copy.",
    ),
    1: (
        "Screenshot",
        "The smallest rendering pipeline: load or make one dataset, " "save one image.",
    ),
    2: (
        "Camera animation",
        "A camera flies around a scene for 100 frames, and the frames become a movie.",
    ),
    3: (
        "Isosurface animation",
        "An isosurface (the surface where a field equals one value) swept from "
        "2.0 to 5.4 over 35 frames.",
    ),
    4: (
        "Streamlines",
        "343 streamlines traced through a vector field, growing over 125 frames.",
    ),
    5: (
        "Time series",
        "One image per step of a 20-step time series, each labelled with its "
        "cycle and time.",
    ),
    6: (
        "Large data",
        "A 5.7 GB cyclone simulation drawn as slices, terrain, volume rendering "
        "and wind, in parallel.",
    ),
    7: (
        "Scaling",
        "Extracts and measures one isosurface at any number of ranks; the "
        "measurements must not change with the rank count.",
    ),
    8: ("Backend check", "Fails when a job that asked for a GPU renders in software."),
    9: (
        "Mesh topologies",
        "The same contour over four kinds of mesh; the point, cell and contour "
        "counts of each are checked.",
    ),
    10: (
        "Colormap fidelity",
        "One field through four colour maps (built in, custom, logarithmic, "
        "categorical), each with its legend.",
    ),
    11: (
        "State verification",
        "A saved session reloaded without a GUI and stepped through three time steps.",
    ),
    12: (
        "Extract regression",
        "Writes three kinds of output per time step (contour geometry, an image "
        "and a row of measurements) and checks each one against its baseline.",
    ),
}

# The four parts, in the order they are shown.
PARTS = (
    ("reads", "Reads"),
    ("does", "Does"),
    ("writes", "Writes"),
    ("checked", "Checked"),
)

_NOISE = "The file data/noise.silo (a 50 × 50 × 50 grid; the field hardyglobal)"
_VARYING = "The 20-step varying series (a 50 × 50 × 50 grid; the field temp)"
_FRAMES = "the first five frames are compared with baseline images"

PIPELINE = {
    ("ParaView", 0): {
        "reads": "Nothing: it makes a cone.",
        "does": "Prints the cone's resolution, height, radius, centre and "
        "direction, then the OpenGL driver ParaView is using.",
        "writes": "Text only, no image.",
        "checked": "The printout is compared line by line with a saved copy, "
        "which names an NVIDIA driver, so a run with --non_gpu_machine "
        "reports a failure only as a warning.",
    },
    ("VisIt", 0): {
        "reads": _NOISE + ".",
        "does": "Runs VisIt's queries on the mesh: surface area, average value, "
        "centroid, grid size, minimum and maximum, node and zone counts, volume.",
        "writes": "Text only, no image.",
        "checked": "The printout is compared line by line with a saved copy "
        "(for example 125 000 nodes, volume 8000, average 3.27436).",
    },
    ("ParaView", 1): {
        "reads": "Nothing: it makes a cone.",
        "does": "Shows it with default colouring and annotations off.",
        "writes": "One 2048 × 2048 PNG.",
        "checked": "The image is compared with its baseline.",
    },
    ("VisIt", 1): {
        "reads": _NOISE + ".",
        "does": "A pseudocolour plot of hardyglobal with the hot_desaturated "
        "colour table.",
        "writes": "One 2048 × 2048 PNG.",
        "checked": "The image is compared with its baseline; some machines keep "
        "their own baseline.",
    },
    ("ParaView", 2): {
        "reads": "Nothing: it makes a sphere and an ellipse.",
        "does": "A 100-frame animation: the camera follows a closed orbit while "
        "the sphere's opacity is animated.",
        "writes": "100 PNGs (4054 × 2536); an MP4 movie on a workstation.",
        "checked": "The run must finish; " + _FRAMES + ".",
    },
    ("VisIt", 2): {
        "reads": _NOISE + ".",
        "does": "Seven camera positions joined by a smooth spline into 100 frames.",
        "writes": "100 PNGs (2048 × 1784) and an MP4 movie.",
        "checked": "The run must finish; " + _FRAMES + ".",
    },
    ("ParaView", 3): {
        "reads": _NOISE + ", through ParaView's VisIt Silo reader (skipped on a "
        "build without it).",
        "does": "Contours hardyglobal at 35 values, 2.0 to 5.4 in steps of 0.1, "
        "one frame each.",
        "writes": "35 PNGs (4054 × 2536); an MP4 movie on a workstation.",
        "checked": "The run must finish; " + _FRAMES + ".",
    },
    ("VisIt", 3): {
        "reads": _NOISE + ".",
        "does": "The isosurface operator at the same 35 values, 2.0 to 5.4.",
        "writes": "35 PNGs (2048 × 1784) and an MP4 movie.",
        "checked": "The run must finish; " + _FRAMES + ".",
    },
    ("ParaView", 4): {
        "reads": _NOISE + " and its vector field grad.",
        "does": "Seeds a 7 × 7 × 7 grid of 343 points and traces "
        "streamlines forward through grad, drawn as tubes over three slices of "
        "hardyglobal; each frame lets the lines run one more step. Rendered "
        "with OSPRay ray tracing.",
        "writes": "125 PNGs (4054 × 2536); an MP4 movie on a workstation.",
        "checked": "The run must finish; " + _FRAMES + ", allowing 0.5% of "
        "pixels to differ (GPU line drawing varies slightly).",
    },
    ("VisIt", 4): {
        "reads": _NOISE + " and its vector field grad.",
        "does": "An integral-curve plot seeded from a 7 × 7 × 7 box, "
        "drawn as tubes with cone heads over three slices; each frame shows "
        "the curves up to a later integration time.",
        "writes": "125 PNGs (2048 × 1784) and an MP4 movie.",
        "checked": "The run must finish; " + _FRAMES + ".",
    },
    ("ParaView", 5): {
        "reads": _VARYING + ", as a .pvd file.",
        "does": "Colours the surface by temp and labels each step with its "
        "cycle and time; an image extractor writes one image per time step.",
        "writes": "20 JPEGs (2082 × 924); an MP4 movie on a workstation.",
        "checked": "The run must finish; " + _FRAMES + ".",
    },
    ("VisIt", 5): {
        "reads": _VARYING + ", as a .visit file.",
        "does": "A pseudocolour plot of temp, labelled with cycle and time; at "
        "each of the 20 steps it saves an image and runs the ex00 queries plus "
        "sample statistics.",
        "writes": "20 PNGs (2048 × 1532), the query printout and an MP4 movie.",
        "checked": "The first five frames against baseline images, and every "
        "step's query results against a saved copy.",
    },
    ("ParaView", 6): {
        "reads": "A WRF simulation of Cyclone Chapala (2015) and a rainfall "
        "file, 5.7 GB together; skipped where the data is not installed.",
        "does": "Slices coloured by water vapour; terrain raised by height; "
        "rain and ice volume-rendered; surface wind as line-integral "
        "convolution (a streaky texture that follows the flow) with arrows; "
        "rainfall on top. Rendered in parallel with OSPRay (the batch "
        "scripts use 8 ranks).",
        "writes": "One 2850 × 1750 PNG.",
        "checked": "The image against its baseline, allowing 5% of pixels to "
        "differ because the wind texture varies from run to run.",
    },
    ("VisIt", 6): {
        "reads": "The same cyclone and rainfall data, by restoring a saved "
        "VisIt session onto it.",
        "does": "Six pseudocolour plots: water vapour on three slices, terrain, "
        "wind streamlines, ice, rain and rainfall.",
        "writes": "One 2850 × 1750 image.",
        "checked": "The image against its baseline, only when run on the "
        "baseline's 8 ranks: the overlapping see-through plots blend "
        "differently at other rank counts.",
    },
    ("ParaView", 7): {
        "reads": _VARYING + ", as legacy .vtk files.",
        "does": "At each step, contours temp at 3.0 and integrates the contour "
        "to get its area; reading, contouring, integrating and rendering are "
        "timed separately. A rank is one MPI process; this runs at any count.",
        "writes": "One PNG of the last isosurface and a row of timings.",
        "checked": "The last step's numbers must match the baseline at every "
        "rank count: 20 steps read, 125 000 points, 5386 contour cells, "
        "contour area 303.84, temp range 1.93 to 26.10. The timings are "
        "recorded, not compared.",
    },
    ("VisIt", 7): {
        "reads": "The same series, through a .visit index written at run time; "
        "the ranks come from VisIt's parallel compute engine.",
        "does": "An isosurface at 3.0; VisIt reads and contours in one step, so "
        "it times opening, the pipeline and rendering.",
        "writes": "One PNG and a row of timings.",
        "checked": "Zone count, temp range and surface area must match the "
        "baseline (the same 5386 cells and 303.84 as ParaView) at every rank "
        "count.",
    },
    ("ParaView", 8): {
        "reads": "Nothing: it makes a sphere.",
        "does": "Asks the OpenGL driver who it is (vendor, renderer, version) "
        "and calls it software (llvmpipe, swrast and similar) or hardware "
        "(NVIDIA, AMD, Intel); then renders a small probe image.",
        "writes": "One probe PNG; the driver strings go into the record's notes.",
        "checked": "A job that asked for a GPU (EGL) must get hardware, one "
        "that asked for OSMesa must get software, and the probe must be the "
        "requested size.",
    },
    ("VisIt", 8): {
        "reads": "One step of the varying series.",
        "does": "VisIt does not report its OpenGL driver, so it checks where "
        "and how it rendered instead: it forces rendering on the compute "
        "engine and counts the engine's processes and nodes.",
        "writes": "One probe PNG.",
        "checked": "The engine must have rendered an image of the requested "
        "size and, when asked, run in parallel on the requested ranks and nodes.",
    },
    ("ParaView", 9): {
        "reads": "Four generated meshes of the same wave field: a tetrahedral "
        "mesh, an adaptive-refinement (AMR) mesh, a polygonal surface, and a "
        "grid split into three blocks of unequal width.",
        "does": "Contours each one (the surface as white isolines over its "
        "colours), removes AMR ghost cells (the overlap between refinement "
        "levels) and merges the blocks first.",
        "writes": "Four PNGs, one per mesh, and a table of counts.",
        "checked": "Per mesh: input points and cells, contour cells and value "
        "range against the baseline, and the blocks must really be unequal.",
    },
    ("VisIt", 9): {
        "reads": "The same tetrahedral, surface and three-block meshes, and a "
        "uniform grid in place of AMR.",
        "does": "A pseudocolour plot with the isosurface operator, querying "
        "node and zone counts before and after it.",
        "writes": "Four PNGs and a table of counts.",
        "checked": "The same five numbers per mesh against the baseline. The "
        "three-block mesh has more nodes than in ParaView because VisIt keeps "
        "each block's copy of a shared face.",
    },
    ("ParaView", 10): {
        "reads": "One step of the varying series (temp, 1.78 to 27.40).",
        "does": "Draws temp four ways: a built-in map (Cool to Warm Extended), "
        "a custom map loaded from an XML file, the custom map on a log scale, "
        "and five labelled categories (coolest to warmest). The legend's font, "
        "position and number format are fixed.",
        "writes": "Four PNGs and a table of the settings applied.",
        "checked": "Per map: the range, log scale on or off, categories on or "
        "off and the legend shown; the images against their baselines.",
    },
    ("VisIt", 10): {
        "reads": "The same step and field.",
        "does": "The same four: hot_desaturated, a custom table read from a "
        ".ct file, log scaling, and a five-colour discrete table over temp "
        "binned into five categories.",
        "writes": "Four PNGs and a table of the settings applied.",
        "checked": "Per map: the colour table in use, the range, log scaling "
        "and the legend; the images against their baselines.",
    },
    ("ParaView", 11): {
        "reads": "A saved ParaView state file (.pvsm): the varying series "
        "contoured at 3.0.",
        "does": "Loads the state without the GUI, points it at this machine's "
        "data, steps through three time steps and disconnects.",
        "writes": "Three PNGs, one per step.",
        "checked": "The state holds two sources, one 1024 × 1024 view and "
        "20 time steps; all three steps render, time advances, and the "
        "session closes cleanly.",
    },
    ("VisIt", 11): {
        "reads": "A saved VisIt session: the varying series with an isosurface "
        "at 3.0.",
        "does": "Restores the session without the GUI and moves the time "
        "slider through three states.",
        "writes": "Three PNGs, one per state.",
        "checked": "One plot and 20 time states in the session, all three "
        "states rendered, and the reported state changes each time.",
    },
    ("ParaView", 12): {
        "reads": _VARYING + ", as a .pvd file.",
        "does": "At each of three time steps, contours temp at 3.0 and "
        "integrates the contour (its area) and the grid (the mean of temp). "
        "An extract is a file written as the pipeline runs: here the contour "
        "geometry, an image, and a row of measurements.",
        "writes": "Per step one .vtp contour and one PNG, plus one CSV with a "
        "row per step: time step, cycle, time, input points and cells, contour "
        "points and cells, contour area, and the minimum, maximum and mean of "
        "temp.",
        "checked": "Every CSV cell against the baseline table (relative "
        "tolerance 10⁻⁶), the images against theirs, one file of "
        "each kind per step, and positive areas.",
    },
    ("VisIt", 12): {
        "reads": _VARYING + ", as a .visit file.",
        "does": "At each of three states: an isosurface at 3.0, exported as a "
        "VTK file; an image; and queries for the counts, area and range. A "
        "second plot without the operator sums temp over the volume for the "
        "mean.",
        "writes": "Per step one exported contour and one PNG, plus one CSV "
        "with the same columns as ParaView and the weighted sum and volume.",
        "checked": "Every CSV cell against the baseline table (relative "
        "tolerance 10⁻⁶), the images, one file of each kind per "
        "step, and a distinct time for every state. Clear output/ first: "
        "older exported files are counted too.",
    },
}
