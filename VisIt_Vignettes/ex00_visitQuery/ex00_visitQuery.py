#
# Visualization Vignettes
#
# ex00_visitQuery -- query mesh statistics from a Silo database
#
# Opens noise.silo, adds a Pseudocolor plot, and runs VisIt's built-in
# queries -- surface area, average value, centroid, grid information,
# min/max, node and zone counts, volume.
#
# Its known_good_value.txt baseline pins the exact query output, so the
# print statements below must not be reworded.
#
# RUNNING IT
#
#   Locally:
#     visit -cli -nowin -s ex00_visitQuery.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --machine_name my-machine
#
#   On a cluster:
#     sbatch ex00_ibex_runScript.sbat
#     sbatch ex00_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex00_visitQuery_results.json for the harness to compare numerically,
#   alongside the existing image and known_good_value.txt comparisons.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys


# --------------------------------------------------------------------------
# Shared vignette scaffolding: CLI parsing, logging, structured results.
# Added without altering the pipeline below, so every committed baseline --
# images and known_good_value.txt alike -- keeps passing unchanged.
# --------------------------------------------------------------------------
def _bootstrap_common():
    """Put Testing/ on sys.path so vignette_common can be imported."""
    here = None
    try:
        here = os.path.abspath(os.path.dirname(__file__))
    except NameError:  # pragma: no cover
        here = None
    if not here and sys.argv and sys.argv[0]:
        here = os.path.abspath(os.path.dirname(sys.argv[0]))
    if not here:
        here = os.getcwd()
    testing = os.path.abspath(os.path.join(here, "..", "..", "Testing"))
    if testing not in sys.path:
        sys.path.insert(0, testing)
    return here


SCRIPT_DIR = _bootstrap_common()

import vignette_common as vc  # noqa: E402

VIGNETTE = "ex00_visitQuery"
TOOL = "VisIt"

_args = vc.parse_args(VIGNETTE, TOOL, description="query mesh statistics from a Silo database")
ctx = vc.VignetteContext(VIGNETTE, TOOL, _args, script_dir=SCRIPT_DIR)

# This vignette writes its images through literal "<script-dir>/output" paths
# in the pipeline below. Rewriting all of them would mean touching hundreds of
# lines and re-blessing every baseline, so --output-dir is pinned instead and
# the caller is told rather than being silently ignored.
_fixed_output = os.path.join(SCRIPT_DIR, "output")
if os.path.abspath(ctx.output_dir) != _fixed_output:
    ctx.warn(
        "--output-dir is not honoured by this vignette; images are written "
        "to " + _fixed_output
    )
    ctx.output_dir = _fixed_output
os.makedirs(ctx.output_dir, exist_ok=True)
# --------------------------------------------------------------------------

print("Running VisIt example script: ", sys.argv[0], "\n")

# Get directory of this script
script_dir = os.path.abspath(os.path.dirname(__file__))
print("Running script from: ", script_dir)

# Launch the compute engine when a site was named on the command line.
#
# This replaces a positional-argument block that read sys.argv[4] to pick the
# machine. The Shaheen submission script passes five positional arguments, so
# argv[4] held the walltime string and neither branch ever matched:
# OpenComputeEngine was skipped and every Shaheen run executed serially on one
# core while reporting success. Named flags remove the whole class of bug.
vc.open_visit_engine(ctx, OpenComputeEngine)


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


# --------------------------------------------------------------------------
# Structured results and a real exit code.
#
# The assertion is deliberately conservative -- it checks only that every
# image already blessed as a baseline was produced again. That cannot fail on
# a setup where this vignette works today, and it does catch the failure the
# old harness could not see at all: a vignette that silently stops emitting a
# frame.
#
# exit() is VisIt's, not Python's: it tears the viewer down before returning
# the status. Falling off the end of a VisIt CLI script leaves the client
# running and holding the compute engine's allocation open.
# --------------------------------------------------------------------------
ctx.assert_baselined_images_present()
_code = ctx.finish()
vc.finish_visit_session(
    ctx, _code, close_compute_engine=CloseComputeEngine, exit_func=exit
)
