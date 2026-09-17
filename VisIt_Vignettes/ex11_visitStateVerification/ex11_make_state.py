#
# Visualization Vignettes
#
# ex11_make_state.py -- generate the VisIt session file ex11 restores
#
# WHY THIS IS A SEPARATE SCRIPT
#
#   A VisIt .session records plot types, operator attributes, the view, and
#   the database it was built against. Restoring one into a different VisIt
#   version can drop an attribute or fail on a renamed operator -- which is
#   exactly what ex11_visitStateVerification is built to catch. Generating
#   the session on every run would make that test tautological, so the
#   session is a committed artifact regenerated deliberately:
#
#     visit -cli -nowin -s ex11_make_state.py
#
#   run_tests.py excludes filenames ending in _make_state.py from vignette
#   discovery, so this will not be mistaken for the vignette itself.
#
# WHAT THE SESSION CONTAINS
#
#   A Pseudocolor plot of "temp" over the shipped varying*.vtk time series
#   with an Isosurface operator, annotations trimmed for reproducible images,
#   and a fixed view. Deliberately modest: the point is to exercise session
#   round-tripping, not to be a showcase.
#
#   The session is written with SaveSession(), which records the absolute
#   path of the database. ex11_visitStateVerification re-points that path at
#   the local data directory when it restores, so a moved checkout still
#   works.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys


SESSION_FILENAME = "ex11_visit.session"
INDEX_FILENAME = "ex11_series.visit"
SCALAR = "temp"
ISOVALUE = 3.0


def log(message):
    print("[ex11_make_state] {0}".format(message))
    sys.stdout.flush()


def script_dir():
    try:
        return os.path.abspath(os.path.dirname(__file__))
    except NameError:
        return os.path.abspath(os.path.dirname(sys.argv[0]))


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


def write_index(here, files):
    """Write a .visit index with absolute paths beside the session."""
    index_path = os.path.join(here, INDEX_FILENAME)
    with open(index_path, "w") as handle:
        handle.write("!NBLOCKS 1\n")
        for path in files:
            handle.write(path + "\n")
    log("wrote {0}".format(index_path))
    return index_path


def main():
    here = script_dir()
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    data_dir = os.environ.get("VV_DATA_DIR", os.path.join(repo_root, "data"))

    files = series_files(os.path.abspath(data_dir))
    log("time series: {0} file(s)".format(len(files)))

    index_path = write_index(here, files)

    if not OpenDatabase(index_path, 0):
        raise RuntimeError("OpenDatabase failed for {0}".format(index_path))

    AddPlot("Pseudocolor", SCALAR, 1, 0)
    pc_atts = PseudocolorAttributes()
    pc_atts.colorTableName = "hot_desaturated"
    SetPlotOptions(pc_atts)

    AddOperator("Isosurface")
    iso_atts = IsosurfaceAttributes()
    iso_atts.contourMethod = iso_atts.Value
    iso_atts.contourValue = (ISOVALUE,)
    iso_atts.variable = SCALAR
    SetOperatorOptions(iso_atts)

    annotation = AnnotationAttributes()
    annotation.userInfoFlag = 0
    annotation.databaseInfoFlag = 0
    annotation.legendInfoFlag = 1
    SetAnnotationAttributes(annotation)

    DrawPlots()
    ResetView()

    session_path = os.path.join(here, SESSION_FILENAME)
    SaveSession(session_path)
    log("wrote {0}".format(session_path))
    log(
        "Commit both files. Regenerate only when deliberately moving to a new "
        "VisIt version."
    )

    DeleteAllPlots()
    CloseDatabase(index_path)
    exit(0)


if __name__ == "__main__":
    main()
