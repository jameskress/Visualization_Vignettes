#
# Visualization Vignettes
#
# ex12_visitExtractRegression -- queries, exports, and a regression test that
#                                survives a VisIt upgrade
#
# WHY THIS VIGNETTE EXISTS
#
#   The VisIt counterpart to ex12_pvExtractRegression, over the same dataset
#   and the same scalar, asserting the same quantities.
#
#   Every other vignette in this suite ultimately asserts on pixels. Pixel
#   comparison is fragile in a way that has nothing to do with correctness: a
#   driver update, a font change, a new default in the shader, and the diff
#   goes red while the science is untouched. Meanwhile a genuine numerical
#   regression that happens not to move many pixels slips straight through.
#
#   This vignette inverts that. It emits three kinds of artifact side by
#   side:
#
#     data extracts   VTK geometry of the contour, written by VisIt's
#                     ExportDatabase utility (the ExportDB machinery behind
#                     File > Export database in the GUI)
#     numerical CSV   per-timestep query results, compared numerically with a
#                     tolerance by Testing/verify.py
#     rendered frames kept for eyeballing and for the existing image path
#
#   The CSV is the assertion. It is declared to the harness with
#   ctx.add_numeric_extract(), which is what routes it into
#   verify.compare_csv rather than into an image diff. A contour's zone count
#   and surface area are properties of the data and the algorithm, not of the
#   renderer, so they are the right thing to pin.
#
# THE QUERIES, AND WHY use_actual_data MATTERS
#
#   One plot carries the Isosurface operator, and every measurement comes
#   from it. VisIt's use_actual_data flag is what separates the two sides:
#
#     use_actual_data=0   the original database, before operators: the input
#                         mesh's node and zone counts, the field range, and
#                         the volume-weighted integrals
#     use_actual_data=1   the data as it exists after the operator: the
#                         contour's node and zone counts and its surface area
#
#   The volume-weighted mean is Weighted Variable Sum divided by Volume, both
#   taken on the original data. It is a far more sensitive regression signal
#   than min/max, because it moves when any zone changes rather than only
#   when the extremes do. Both terms are carried in the CSV so a surprising
#   mean can be diagnosed without re-running anything.
#
# WHAT IT ASSERTS
#
#   Every export wrote its file; the CSV carries every required column and
#   one row per timestep; every contour is non-empty; every integrated area
#   is finite and positive; and the volume-weighted mean is finite. The
#   values themselves are recorded as metrics and in the CSV, so the harness
#   compares them with a tolerance rather than demanding bit-identical
#   floats.
#
# DATA
#
#   data/varying_data/varying*.vtk, point scalar "temp". Shipped with the
#   repository.
#
# RUNNING IT
#
#   visit -cli -nowin -s ex12_visitExtractRegression.py
#   visit -cli -nowin -s ex12_visitExtractRegression.py --steps 5
#
# Author: James Kress, <james@jameskress.com>
#
import csv
import math
import os
import sys


def _bootstrap_common():
    """Put Testing/ on sys.path so vignette_common can be imported."""
    here = None
    try:
        here = os.path.abspath(os.path.dirname(__file__))
    except NameError:  # pragma: no cover - VisIt CLI without __file__
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


VIGNETTE = "ex12_visitExtractRegression"
TOOL = "VisIt"

NUMERIC_CSV = "{0}_measurements.csv".format(VIGNETTE)

# Columns the numeric CSV must always carry. Checked explicitly, so a
# silently dropped column is a failure rather than a quietly shorter file.
# The first ten match ex12_pvExtractRegression exactly, so the two suites'
# CSVs can be compared against each other as well as against their own
# baselines; the last two are VisIt's raw integral terms, kept for diagnosis.
REQUIRED_COLUMNS = (
    "timestep",
    "cycle",
    "time",
    "input_points",
    "input_cells",
    "contour_points",
    "contour_cells",
    "contour_area",
    "scalar_min",
    "scalar_max",
    "scalar_mean",
    "weighted_sum",
    "volume",
)

# Columns whose values are identities rather than measurements. Matched on,
# not compared. See ctx.add_numeric_extract() below.
CSV_KEY_COLUMNS = ("timestep",)

# Tolerances for the CSV comparison. Looser than the results-JSON defaults on
# purpose: these are integrals over a mesh, and their last couple of digits
# legitimately move with rank count, with the order zones are summed in, and
# with the compiler's floating-point contraction. A tolerance that fails on
# that is a tolerance people learn to ignore.
CSV_RTOL = 1e-6
CSV_ATOL = 1e-9


def add_arguments(parser):
    parser.add_argument(
        "--isovalue",
        type=float,
        default=3.0,
        help="Contour value on the scalar being extracted.",
    )
    parser.add_argument(
        "--scalar",
        default=vc.SHARED_SCALAR,
        help="Point scalar to contour and measure.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3,
        help="How many timesteps to extract and measure.",
    )
    parser.add_argument(
        "--export-format",
        default="VTK",
        help="Database type passed to ExportDatabase, e.g. VTK or Silo.",
    )


def write_visit_index(ctx, series):
    """Write a .visit index with absolute paths.

    The shipped data/varying.visit lists paths relative to the repository
    root, so opening it only works from one particular working directory.
    Writing our own index removes that dependency entirely.
    """
    index_path = os.path.join(ctx.output_dir, "{0}_series.visit".format(VIGNETTE))
    with open(index_path, "w") as handle:
        handle.write("!NBLOCKS 1\n")
        for path in series:
            handle.write(path + "\n")
    ctx.log("wrote database index: {0}".format(index_path))
    return index_path


def query_value(name, **kwargs):
    """Run a VisIt query and return its numeric output.

    GetQueryOutputValue() returns a float for scalar queries and a tuple for
    multi-valued ones such as MinMax.
    """
    Query(name, **kwargs)
    return GetQueryOutputValue()


def optional_query(ctx, name, **kwargs):
    """Run a query that some builds or datasets may not support.

    Returns None instead of raising, and says which query went missing. Used
    only for the two integral terms; every query the assertions depend on is
    run through query_value() so that a failure is a failure.
    """
    try:
        return float(query_value(name, **kwargs))
    except Exception as exc:  # noqa: BLE001 - the point is to keep going
        ctx.warn("query '{0}' unavailable: {1}".format(name, exc))
        return None


def database_times(ctx, database, n_states):
    """The simulation time of every state, from the database's own metadata.

    WHY NOT Query("Time"), WHICH IS WHAT THIS USED TO DO

    Both are wrong in the same way on the same builds, but the metadata says
    so out loud. On VisIt 3.4.2 a .visit virtual database over legacy VTK
    files reports **every state as t=0 and cycle 0**; on 3.4.1, over the same
    twenty files, it reports 0..19 for both. Reduced to fifteen lines and
    reproduced on demand:

        md = GetMetaData(index_path)
        3.4.1 -> md.times  = (0.0, 1.0, 2.0, ... 19.0)
        3.4.2 -> md.times  = (0.0, 0.0, 0.0, ...  0.0)

    Query("Time") returns the same zeros on 3.4.2, so the old code recorded
    them without complaint and the blessed CSV carried a "time" column that
    was a column of zeros.

    Taking the whole array up front makes the defect visible: `n` states with
    one distinct time between them is a fact about the reader, and run()
    asserts on it. Falling back to the state index, as this used to do, would
    have hidden it behind numbers that look right.

    GetWindowInformation().timeSliderCurrentStates is deliberately not used:
    that is the state INDEX, so it would fill "time" with a copy of
    "timestep" and always look plausible.
    """
    try:
        metadata = GetMetaData(database)
        times = [float(value) for value in (vc.visit_attr(metadata, "times") or [])]
    except Exception as exc:  # noqa: BLE001 - reported, then degraded
        ctx.warn("database metadata unavailable: {0}".format(exc))
        times = []

    if len(times) < n_states:
        ctx.warn(
            "database reports {0} time value(s) for {1} state(s); the "
            "missing ones are recorded as the state index".format(len(times), n_states)
        )
        times = times + [float(i) for i in range(len(times), n_states)]

    return times


def database_cycles(ctx, database, n_states):
    """The simulation cycle of every state, from the database's metadata.

    Same source and same caveat as database_times(): over the legacy series
    these come back all-zero on 3.4.2 and 0,1,2.. on 3.4.1, because the legacy
    files carry no cycle either. Over the XML series both read the real
    values, and they agree with what ParaView reads out of the same files'
    FieldData.
    """
    try:
        metadata = GetMetaData(database)
        cycles = [int(value) for value in (vc.visit_attr(metadata, "cycles") or [])]
    except Exception as exc:  # noqa: BLE001 - reported, then degraded
        ctx.warn("database cycles unavailable: {0}".format(exc))
        cycles = []
    if len(cycles) < n_states:
        cycles = cycles + [None] * (n_states - len(cycles))
    return cycles


def resolve_export_function(ctx):
    """Return VisIt's export-database callable.

    The utility is ExportDatabase() in every VisIt this repository targets.
    ExportDB is looked for as well because the name appears in older
    documentation and in some site wrappers, and resolving it here means a
    build that only carries the older spelling reports nothing worse than a
    log line.
    """
    namespace = globals()
    for name in ("ExportDatabase", "ExportDB"):
        function = namespace.get(name)
        if callable(function):
            ctx.log("export utility: {0}()".format(name))
            return function, name
    raise vc.VignetteError(
        "Neither ExportDatabase() nor ExportDB() is available in this VisIt "
        "build. Exporting is what this vignette is for, so there is nothing "
        "useful to fall back to."
    )


def export_attributes(ctx, basename):
    """ExportDBAttributes for one timestep's contour geometry."""
    atts = ExportDBAttributes()
    atts.db_type = ctx.args.export_format
    atts.filename = basename
    atts.dirname = ctx.output_dir
    atts.variables = (ctx.args.scalar,)
    return atts


def configure_annotations():
    annotation = AnnotationAttributes()
    annotation.userInfoFlag = 0
    annotation.databaseInfoFlag = 0
    annotation.legendInfoFlag = 0
    annotation.axes3D.visible = 0
    annotation.axes3D.triadFlag = 0
    annotation.axes3D.bboxFlag = 0
    annotation.backgroundMode = annotation.Solid
    annotation.backgroundColor = (23, 26, 31, 255)
    annotation.foregroundColor = (240, 242, 247, 255)
    SetAnnotationAttributes(annotation)


def save_attributes(ctx, filename):
    save_atts = SaveWindowAttributes()
    save_atts.family = 0
    save_atts.format = save_atts.PNG
    save_atts.width = ctx.args.image_width
    save_atts.height = ctx.args.image_height
    save_atts.resConstraint = save_atts.NoConstraint
    save_atts.outputToCurrentDirectory = 0
    save_atts.outputDirectory = ctx.output_dir
    save_atts.fileName = filename
    return save_atts


def collect_volume_integrals(ctx, scalar, step_count):
    """Volume and Weighted Variable Sum per timestep, measured before the
    contour pipeline exists.

    WHY A SEPARATE PASS

    The volume-weighted mean is Weighted Variable Sum over Volume, both on
    the ORIGINAL mesh. Neither can be taken from the plot that carries the
    Isosurface operator:

      * use_actual_data=0 selects which data a query reads, but the query is
        still validated against the plot's output topology. An isosurfaced
        plot is a surface, so VisIt answers "Volume query requires 3D surface
        plot data" and returns 0.0 with either value of the flag. The
        vignette divided by that and asserted on the resulting NaN.
      * Adding a second, hidden plot does not work either: VisIt does not
        execute a hidden plot's pipeline, so both integrals come back 0.0.
        Measured, after trying it.

    So the integrals are collected here, on their own plot, which is then
    deleted. Nothing about the rendered frames changes, and the contour
    pipeline downstream is built on a clean slate.
    """
    integrals = {}

    AddPlot("Pseudocolor", scalar, 1, 0)
    atts = PseudocolorAttributes()
    atts.legendFlag = 0
    SetPlotOptions(atts)

    try:
        for state in range(step_count):
            SetTimeSliderState(state)
            DrawPlots()
            weighted_sum = optional_query(
                ctx, "Weighted Variable Sum", use_actual_data=0
            )
            volume = optional_query(ctx, "Volume", use_actual_data=0)
            integrals[state] = (weighted_sum, volume)
            ctx.debug(
                "state {0}: weighted_sum={1} volume={2}".format(
                    state, weighted_sum, volume
                )
            )
    finally:
        DeleteAllPlots()

    return integrals


def measure(ctx, state, time_value, integrals, cycle=None):
    """Collect the numerical measurements for one timestep.

    use_actual_data=0 asks the original database; =1 asks the data as it
    exists after the Isosurface operator. Both come from the same plot.
    """
    input_points = int(query_value("NumNodes", use_actual_data=0))
    input_cells = int(query_value("NumZones", use_actual_data=0))
    contour_points = int(query_value("NumNodes", use_actual_data=1))
    contour_cells = int(query_value("NumZones", use_actual_data=1))

    contour_area = float(query_value("3D surface area"))

    minmax = query_value("MinMax", use_actual_data=0)
    if isinstance(minmax, (list, tuple)) and len(minmax) >= 2:
        scalar_min, scalar_max = float(minmax[0]), float(minmax[1])
    else:
        scalar_min = scalar_max = float("nan")

    # Precomputed on an operator-free plot before this pipeline existed; see
    # collect_volume_integrals().
    weighted_sum, volume = integrals.get(state, (None, None))

    if weighted_sum is not None and volume:
        scalar_mean = weighted_sum / volume
    else:
        scalar_mean = float("nan")

    return {
        "timestep": state,
        "cycle": cycle,
        "time": float(time_value),
        "input_points": input_points,
        "input_cells": input_cells,
        "contour_points": contour_points,
        "contour_cells": contour_cells,
        "contour_area": contour_area,
        "scalar_min": scalar_min,
        "scalar_max": scalar_max,
        "scalar_mean": scalar_mean,
        "weighted_sum": weighted_sum if weighted_sum is not None else float("nan"),
        "volume": volume if volume is not None else float("nan"),
    }


def write_numeric_csv(ctx, rows):
    """Write the version-agnostic numerical record and declare it."""
    path = os.path.join(ctx.output_dir, NUMERIC_CSV)
    with open(path, "w") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(REQUIRED_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in REQUIRED_COLUMNS})
    ctx.log("wrote numeric extract: {0}".format(path))

    # This is the line that routes the file into verify.compare_csv instead
    # of leaving it as an unchecked artifact beside the images.
    ctx.add_numeric_extract(
        NUMERIC_CSV,
        key_columns=CSV_KEY_COLUMNS,
        rtol=CSV_RTOL,
        atol=CSV_ATOL,
    )
    return path


def run(ctx):
    scalar = ctx.args.scalar
    series = ctx.timestep_files()
    ctx.log("time series: {0} file(s)".format(len(series)))
    ctx.log("contouring '{0}' at {1}".format(scalar, ctx.args.isovalue))

    engine_launched = vc.open_visit_engine(ctx, OpenComputeEngine)
    # A note, not a metric. `metrics` is a correctness gate compared against
    # the baseline; how the engine was launched is a property of the run,
    # not of the result. Gating on it makes every rank change look like a
    # regression -- measured: the same suite at --ranks 8 produced
    # bit-identical images and failed here on "expected false, got true".
    # ex08_visitBackendCheck keeps it as a metric, because the backend IS
    # its subject.
    ctx.notes.append("compute_engine_launched={0}".format(bool(engine_launched)))

    export_function, export_name = resolve_export_function(ctx)
    ctx.add_metric("export_utility", export_name)

    # The generated XML series index, not one written here from the legacy
    # files. Writing an index cannot add a time to data that has none, which
    # is what the old path amounted to. See vc.time_series_index().
    index_path = ctx.time_series_index()

    with ctx.phase("open"):
        if not OpenDatabase(index_path, 0):
            raise vc.VignetteError("OpenDatabase failed for {0}".format(index_path))

    n_states = TimeSliderGetNStates()
    ctx.log("timesteps in database: {0}".format(n_states))

    requested = ctx.args.steps or n_states
    step_count = max(1, min(requested, n_states))
    ctx.log("extracting {0} of {1} timestep(s)".format(step_count, n_states))

    # -- the reader's own idea of time, asserted rather than trusted -------
    times = database_times(ctx, index_path, n_states)
    cycles = database_cycles(ctx, index_path, n_states)
    distinct = len(set(times[:n_states]))
    ctx.add_metric("database_distinct_times", distinct)
    ctx.add_metric("database_time_span", round(max(times) - min(times), 6))
    ctx.log(
        "database times: {0} distinct value(s) across {1} state(s), "
        "span {2}".format(distinct, n_states, round(max(times) - min(times), 6))
    )
    ctx.assert_true(
        "database reports a distinct time per state",
        n_states < 2 or distinct == n_states,
        "{0} distinct time value(s) across {1} states. A time series whose "
        "states all carry the same time is a reader defect, not data: VisIt "
        "3.4.2 returns t=0 and cycle=0 for every state of a .visit index "
        "over legacy VTK, where 3.4.1 returns 0..{2} over the same "
        "files.".format(distinct, n_states, n_states - 1),
    )

    # -- volume integrals, on their own plot, before anything else ---------
    with ctx.phase("integrals"):
        integrals = collect_volume_integrals(ctx, scalar, step_count)

    # -- pipeline ----------------------------------------------------------
    AddPlot("Pseudocolor", scalar, 1, 0)

    pc_atts = PseudocolorAttributes()
    pc_atts.colorTableName = "hot_desaturated"
    pc_atts.legendFlag = 0
    SetPlotOptions(pc_atts)

    AddOperator("Isosurface")
    iso_atts = IsosurfaceAttributes()
    iso_atts.contourMethod = iso_atts.Value
    iso_atts.contourValue = (ctx.args.isovalue,)
    iso_atts.variable = scalar
    SetOperatorOptions(iso_atts)

    configure_annotations()

    rows = []
    exported = []
    for state in range(step_count):
        SetTimeSliderState(state)

        with ctx.phase("pipeline", accumulate=True):
            DrawPlots()

        time_value = times[state]

        # -- data extract --------------------------------------------------
        basename = "{0}_contour_{1:06d}".format(VIGNETTE, state)
        with ctx.phase("export", accumulate=True):
            ok = export_function(export_attributes(ctx, basename))
        if not ok:
            raise vc.VignetteError(
                "{0}() refused to write {1} as {2}. Check that this VisIt "
                "build carries the {2} writer.".format(
                    export_name, basename, ctx.args.export_format
                )
            )
        exported.append(basename)

        # -- rendered frame ------------------------------------------------
        ResetView()
        image_name = "{0}_frame_{1:06d}.png".format(VIGNETTE, state)
        SetSaveWindowAttributes(save_attributes(ctx, image_name))
        with ctx.phase("render", accumulate=True):
            SaveWindow()
        ctx.image_path(image_name)

        # -- measurements --------------------------------------------------
        with ctx.phase("query", accumulate=True):
            row = measure(ctx, state, time_value, integrals, cycles[state])
        rows.append(row)

        ctx.log(
            "  step {0}: t={1} contour {2} zones, area={3:.4f}, "
            "mean={4:.6f}".format(
                state,
                time_value,
                row["contour_cells"],
                row["contour_area"],
                row["scalar_mean"],
            )
        )

    csv_path = write_numeric_csv(ctx, rows)

    # -- record what landed on disk ---------------------------------------
    produced = sorted(os.listdir(ctx.output_dir))
    data_files = [
        name
        for name in produced
        if name.startswith("{0}_contour_".format(VIGNETTE))
        and not name.lower().endswith(".png")
    ]
    frame_files = [
        name
        for name in produced
        if name.startswith("{0}_frame_".format(VIGNETTE))
        and name.lower().endswith(".png")
    ]
    for name in data_files:
        ctx.extract_path(name)

    ctx.log("data extracts : {0}".format(len(data_files)))
    ctx.log("image extracts: {0}".format(len(frame_files)))

    # -- metrics -----------------------------------------------------------
    last = rows[-1]
    ctx.add_metric("steps_extracted", len(rows))
    ctx.add_metric("data_extract_files", len(data_files))
    ctx.add_metric("image_extract_files", len(frame_files))
    ctx.add_metric("input_points", last["input_points"])
    ctx.add_metric("input_cells", last["input_cells"])
    ctx.add_metric("contour_cells", last["contour_cells"])
    ctx.add_metric("contour_area", round(last["contour_area"], 4))
    ctx.add_metric("scalar_min", round(last["scalar_min"], 6))
    ctx.add_metric("scalar_max", round(last["scalar_max"], 6))
    ctx.add_metric("scalar_mean", round(last["scalar_mean"], 6))

    # -- assertions ---------------------------------------------------------
    ctx.assert_true(
        "export wrote a file for every step",
        len(data_files) >= len(exported),
        "exported {0} basename(s), found {1} file(s) in {2}".format(
            len(exported), len(data_files), ctx.output_dir
        ),
    )
    ctx.assert_true(
        "one rendered frame per step",
        len(frame_files) >= step_count,
        "expected at least {0}, found {1}".format(step_count, len(frame_files)),
    )
    ctx.assert_true(
        "numeric CSV was written",
        os.path.exists(csv_path),
        NUMERIC_CSV,
    )

    with open(csv_path, "r") as handle:
        reader_csv = csv.DictReader(handle)
        header = reader_csv.fieldnames or []
        csv_rows = list(reader_csv)

    ctx.assert_true(
        "numeric CSV carries every required column",
        all(column in header for column in REQUIRED_COLUMNS),
        "missing: {0}".format(
            [column for column in REQUIRED_COLUMNS if column not in header]
        ),
    )
    ctx.assert_true(
        "numeric CSV has one row per extracted step",
        len(csv_rows) == step_count,
        "expected {0} row(s), found {1}".format(step_count, len(csv_rows)),
    )
    ctx.assert_true(
        "every contour is non-empty",
        all(row["contour_cells"] > 0 for row in rows),
        "zone counts: {0}".format([row["contour_cells"] for row in rows]),
    )
    ctx.assert_true(
        "every integrated area is finite and positive",
        all(
            not math.isnan(row["contour_area"]) and row["contour_area"] > 0.0
            for row in rows
        ),
        "areas: {0}".format([row["contour_area"] for row in rows]),
    )
    ctx.assert_true(
        "volume-weighted mean is finite",
        not math.isnan(last["scalar_mean"]),
        "mean={0} from weighted_sum={1} / volume={2}".format(
            last["scalar_mean"], last["weighted_sum"], last["volume"]
        ),
    )

    DeleteAllPlots()
    CloseDatabase(index_path)


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Emit data, numeric and image extracts, and regression "
        "test the numbers rather than the pixels.",
        extend=add_arguments,
    )
    ctx = vc.VignetteContext(VIGNETTE, TOOL, args, script_dir=SCRIPT_DIR)
    try:
        run(ctx)
        code = ctx.finish()
    except Exception as exc:  # noqa: BLE001 - a vignette must report, not raise
        code = ctx.abort(exc)

    vc.finish_visit_session(
        ctx, code, close_compute_engine=CloseComputeEngine, exit_func=exit
    )


if __name__ == "__main__":
    main()
