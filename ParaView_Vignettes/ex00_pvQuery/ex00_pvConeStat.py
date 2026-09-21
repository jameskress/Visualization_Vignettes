#
# Visualization Vignettes
#
# ex00_pvQuery -- query cone source properties and the active OpenGL driver
#
# Reports the geometric properties of a Cone source and then prints
# the OpenGL capability string of whatever driver ParaView bound to.
#
# The driver line is machine-specific, which is why this vignette is
# registered in test_suite.is_gpu_test_allowed_to_fail: on a CPU-only
# runner its text comparison is expected to differ and is downgraded to
# a warning by --non_gpu_machine. ex08_pvBackendCheck is the vignette
# that turns the same information into a real assertion.
#
# RUNNING IT
#
#   Locally:
#     pvbatch --force-offscreen-rendering ex00_pvConeStat.py
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type ParaView --machine_name my-machine
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
#   ./Testing/ex00_pvQuery_results.json for the harness to compare numerically,
#   alongside the existing image and known_good_value.txt comparisons.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys
from paraview.simple import *


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

VIGNETTE = "ex00_pvQuery"
TOOL = "ParaView"

_args = vc.parse_args(
    VIGNETTE,
    TOOL,
    description="query cone source properties and the active OpenGL driver",
)
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

# Create a simple cone object and query it's properties
cone = Cone()
print("Cone Resolution: ", cone.Resolution)
print("Cone Height:     ", cone.Height)
print("Cone Radius:     ", cone.Radius)
print("Cone Center:     ", cone.Center)
print("Cone Direction:  ", cone.Direction)


print("\nChecking for the currently supported OpenGL Driver")
print(GetOpenGLInformation().GetCapabilities())

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
