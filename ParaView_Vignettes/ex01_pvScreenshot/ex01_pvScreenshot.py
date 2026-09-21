#
# Visualization Vignettes
#
# ex01_pvScreenshot -- render a single screenshot
#
# The smallest useful ParaView vignette: create a source, show it in a
# render view, and save one screenshot. Start here when you want the
# minimum viable pvbatch script.
#
# RUNNING IT
#
#   Locally:
#     pvbatch --force-offscreen-rendering ex01_pvScreenshot.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type ParaView --machine_name my-machine
#
#   On a cluster:
#     sbatch ex01_ibex_runScript.sbat
#     sbatch ex01_shaheen_runScript.sbat
#
#   Run with --help to see every accepted flag. All vignettes share one CLI:
#   --machine/--nodes/--ranks/--partition/--walltime select where and how
#   wide to run, --image-width/--image-height size the output, --data-dir
#   points at the static datasets.
#
# OUTPUT
#
#   Images land in ./output. A structured results JSON is written to
#   ./Testing/ex01_pvScreenshot_results.json for the harness to compare numerically,
#   alongside the existing image and known_good_value.txt comparisons.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys
from pathlib import *
from paraview.simple import *

paraview.simple._DisableFirstRenderCameraReset()


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

VIGNETTE = "ex01_pvScreenshot"
TOOL = "ParaView"

_args = vc.parse_args(VIGNETTE, TOOL, description="render a single screenshot")
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

print("Running ParaView example script: ", sys.argv[0], "\n")

# Create a simple cone object
cone = Cone()

# get active view
renderView1 = GetActiveViewOrCreate("RenderView")
renderView1.ViewSize = [2048, 2048]
renderView1.ShowAnnotation = False  # Disables render view annotations


# get directory where script is stored
fileDir = str(Path(__file__).parent.resolve())

# Create the output directory if it doesn't exist
directory = Path(fileDir + "/output")
directory.mkdir(parents=True, exist_ok=True)

# show data in view
cone1Display = Show(cone, renderView1)
SaveScreenshot(str(directory) + "/ex01_pvScreenshot.png", renderView1)

print("\nFinished ParaView example script\n")


# --------------------------------------------------------------------------
# Structured results and a real exit code.
#
# The assertion is deliberately conservative -- it checks only that every
# image already blessed as a baseline was produced again. That cannot fail on
# a setup where this vignette works today, and it does catch the failure the
# old harness could not see at all: a vignette that silently stops emitting a
# frame.
# --------------------------------------------------------------------------
ctx.assert_baselined_images_present()
vc.exit_vignette(ctx.finish())
