#
# Visualization Vignettes
#
# ex11_make_state.py -- generate the ParaView state file ex11 loads
#
# WHY THIS IS A SEPARATE SCRIPT
#
#   A .pvsm is version-sensitive. A state written by ParaView 5.13 loaded
#   into 6.0 may work, may warn, or may silently drop a property, and that is
#   precisely the failure ex11_pvStateVerification exists to detect. Keeping
#   generation separate means the state in the repository is a deliberate,
#   dated artifact rather than something regenerated on every run -- which
#   would make the test tautological.
#
#   Regenerate it when you intentionally move to a new ParaView major
#   version, review the diff, and commit it:
#
#     pvbatch ex11_make_state.py
#
#   run_tests.py will not mistake this for the vignette: filenames ending in
#   _make_state.py are excluded from vignette discovery.
#
# WHAT THE STATE CONTAINS
#
#   A legacy VTK reader over the shipped varying*.vtk time series, a contour
#   on the "temp" scalar, a coloured surface representation with a visible
#   scalar bar, and a render view with a fixed camera. Deliberately modest:
#   the point is to exercise state round-tripping, not to be a showcase.
#
# Author: James Kress, <james@jameskress.com>
#
import argparse
import os
import sys

from paraview.simple import *  # noqa: F401,F403


STATE_FILENAME = "ex11_state.pvsm"
SCALAR = "temp"
ISOVALUE = 3.0


def log(message):
    print("[ex11_make_state] {0}".format(message))
    sys.stdout.flush()


def series_files(data_dir):
    """Absolute, sorted paths of the shipped varying*.vtk time series."""
    series_dir = os.path.join(data_dir, "varying_data")
    if not os.path.isdir(series_dir):
        raise RuntimeError(
            "Time series directory not found: {0}. Run data/fetchData.sh "
            "first.".format(series_dir)
        )
    names = sorted(f for f in os.listdir(series_dir) if f.lower().endswith(".vtk"))
    if not names:
        raise RuntimeError("No .vtk files in {0}".format(series_dir))
    return [os.path.join(series_dir, name) for name in names]


def main(argv=None):
    here = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(
        description="Generate the ParaView state file used by ex11.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("VV_DATA_DIR", os.path.join(repo_root, "data")),
        help="Directory holding the static datasets.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(here, STATE_FILENAME),
        help="Where to write the .pvsm.",
    )
    parser.add_argument("--image-width", type=int, default=1024)
    parser.add_argument("--image-height", type=int, default=1024)
    args, _unknown = parser.parse_known_args(argv)

    paraview.simple._DisableFirstRenderCameraReset()

    files = series_files(os.path.abspath(args.data_dir))
    log("time series: {0} file(s)".format(len(files)))

    reader = LegacyVTKReader(registrationName="ex11_series", FileNames=files)
    UpdatePipeline(proxy=reader)

    contour = Contour(Input=reader, registrationName="ex11_contour")
    contour.ContourBy = ["POINTS", SCALAR]
    contour.Isosurfaces = [ISOVALUE]
    contour.PointMergeMethod = "Uniform Binning"
    UpdatePipeline(proxy=contour)

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [args.image_width, args.image_height]
    view.ShowAnnotation = False
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [0.09, 0.10, 0.12]

    display = Show(contour, view)
    display.Representation = "Surface"
    ColorBy(display, ("POINTS", SCALAR))

    lut = GetColorTransferFunction(SCALAR)
    lut.ApplyPreset("Cool to Warm", True)

    array_info = reader.PointData.GetArray(SCALAR)
    if array_info is not None:
        scalar_range = array_info.GetRange(0)
        lut.RescaleTransferFunction(scalar_range[0], scalar_range[1])

    display.SetScalarBarVisibility(view, True)

    ResetCamera(view)
    Render(view)

    # A camera pinned in the state means the loaded view is reproducible;
    # leaving it to ResetCamera on load would let a changed default bounds
    # calculation quietly change every baseline image.
    log(
        "camera position: {0}".format(
            [round(value, 4) for value in view.CameraPosition]
        )
    )

    SaveState(args.output)
    log("wrote {0}".format(args.output))
    log(
        "Commit this file. Regenerate it only when deliberately moving to a "
        "new ParaView version."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
