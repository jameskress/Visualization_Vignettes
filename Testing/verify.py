#
# Visualization Vignettes
#
# verify.py
#
# Comparison routines shared by the test harness.
#
# Extracted from test_suite.py so that image comparison, structured numeric
# comparison, and the legacy text comparison all live in one place and can be
# unit-checked without importing the whole suite.
#
# THREE THINGS CHANGED RELATIVE TO THE ORIGINAL INLINE ROUTINES
#
#   1. A resolution mismatch is a FAILURE, not something to paper over.
#      The original resize_to_match() rescaled the output to the baseline's
#      dimensions before diffing, which hid exactly the regression that
#      matters most on a cluster: an offscreen job that requested EGL,
#      silently fell back to software, and rendered at a different size.
#
#   2. Diffs run at native resolution and the threshold is a FRACTION of
#      total pixels, not a flat count. A flat 1000-pixel budget means 24% of
#      a 64x64 thumbnail and 0.012% of a 4K frame.
#
#   3. Numeric comparison of structured results is available alongside the
#      text comparison rather than instead of it. Baselines that only have
#      known_good_value.txt keep working untouched.
#
# Author: James Kress, <james@jameskress.com>
#
import csv
import json
import os
import re

try:
    import numpy as _np
except ImportError:  # pragma: no cover - exercised only on hosts without numpy
    _np = None

try:
    from PIL import Image, ImageChops
except ImportError:  # pragma: no cover
    Image = None
    ImageChops = None


# Image comparison verdicts. SAME / ACCEPTABLE / DIFFERENT / NO BASELINE keep
# the spellings the original harness wrote into image_comparison_results.json
# so existing tooling and archived result files stay readable.
STATUS_SAME = "SAME"
STATUS_ACCEPTABLE = "ACCEPTABLE"
STATUS_DIFFERENT = "DIFFERENT"
STATUS_NO_BASELINE = "NO BASELINE"
STATUS_SIZE_MISMATCH = "SIZE MISMATCH"
STATUS_MISSING_OUTPUT = "MISSING OUTPUT"
STATUS_ERROR = "ERROR"

# Any verdict in this set fails the test.
IMAGE_FAILURE_STATUSES = frozenset(
    (
        STATUS_DIFFERENT,
        STATUS_NO_BASELINE,
        STATUS_SIZE_MISMATCH,
        STATUS_MISSING_OUTPUT,
        STATUS_ERROR,
    )
)

# Fraction of total pixels allowed to differ before a comparison fails.
# 0.001 is one pixel in a thousand: enough to absorb driver-level dithering
# and font hinting, far too little to absorb a geometry or colormap change.
DEFAULT_IMAGE_TOLERANCE = 0.001

# Per-channel sum below which a pixel counts as unchanged. Matches the
# original harness, which ignored pixels whose summed RGB delta was <= 1.
CHANNEL_NOISE_FLOOR = 1

DEFAULT_RTOL = 1e-6
DEFAULT_ATOL = 1e-9

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


def is_image_failure(status):
    """True when an image verdict should fail the test."""
    return status in IMAGE_FAILURE_STATUSES


# ---------------------------------------------------------------------------
# Image comparison
# ---------------------------------------------------------------------------
def _count_differing_pixels(baseline_image, output_image):
    """Number of pixels whose summed RGB delta exceeds the noise floor.

    Uses numpy when available -- the pure-Python path walks every pixel, which
    is 4.2 million interpreted iterations for a single 2048x2048 screenshot.
    """
    diff = ImageChops.difference(baseline_image, output_image)

    if _np is not None:
        array = _np.asarray(diff, dtype=_np.int32)
        if array.ndim == 3:
            per_pixel = array.sum(axis=2)
        else:
            per_pixel = array
        return int((per_pixel > CHANNEL_NOISE_FLOOR).sum())

    return sum(1 for pixel in diff.getdata() if sum(pixel) > CHANNEL_NOISE_FLOOR)


def compare_single_image(baseline_path, output_path, tolerance=DEFAULT_IMAGE_TOLERANCE):
    """Compare one rendered image against its baseline at native resolution.

    Returns a result dict. Never raises: an unreadable image is reported as
    ERROR so one bad file cannot abort a whole suite run.
    """
    result = {
        "image": os.path.basename(output_path),
        "tolerance_fraction": tolerance,
    }

    if Image is None:
        result["status"] = STATUS_ERROR
        result["detail"] = "Pillow is not installed; cannot compare images."
        return result

    if not os.path.exists(output_path):
        result["status"] = STATUS_MISSING_OUTPUT
        result["detail"] = "Vignette did not produce {0}".format(output_path)
        return result

    if not os.path.exists(baseline_path):
        result["status"] = STATUS_NO_BASELINE
        result["detail"] = (
            "No baseline at {0}. Re-run the suite with --bless to record one.".format(
                baseline_path
            )
        )
        return result

    try:
        baseline_image = Image.open(baseline_path).convert("RGB")
        output_image = Image.open(output_path).convert("RGB")
    except Exception as exc:  # pragma: no cover - corrupt file path
        result["status"] = STATUS_ERROR
        result["detail"] = "Could not open image: {0}".format(exc)
        return result

    result["baseline_size"] = list(baseline_image.size)
    result["output_size"] = list(output_image.size)

    # A resolution change is a regression in its own right. Rendering at an
    # unexpected size almost always means the render window was not created
    # the way the script asked -- a software fallback, a missing offscreen
    # context, or a headless server clamping the window.
    if baseline_image.size != output_image.size:
        result["status"] = STATUS_SIZE_MISMATCH
        result["detail"] = (
            "Resolution changed: baseline {0}x{1}, output {2}x{3}. "
            "This usually means the render backend differs from the one the "
            "baseline was captured with.".format(
                baseline_image.size[0],
                baseline_image.size[1],
                output_image.size[0],
                output_image.size[1],
            )
        )
        return result

    total_pixels = baseline_image.size[0] * baseline_image.size[1]
    try:
        differing = _count_differing_pixels(baseline_image, output_image)
    except Exception as exc:  # pragma: no cover
        result["status"] = STATUS_ERROR
        result["detail"] = "Diff failed: {0}".format(exc)
        return result

    fraction = (float(differing) / total_pixels) if total_pixels else 0.0
    result["diff_pixels"] = differing
    result["total_pixels"] = total_pixels
    result["diff_fraction"] = round(fraction, 9)

    if differing == 0:
        result["status"] = STATUS_SAME
    elif fraction > tolerance:
        result["status"] = STATUS_DIFFERENT
        result["detail"] = (
            "{0} of {1} pixels differ ({2:.4%}), tolerance {3:.4%}".format(
                differing, total_pixels, fraction, tolerance
            )
        )
    else:
        result["status"] = STATUS_ACCEPTABLE
        result["detail"] = "{0} pixels differ ({1:.4%}), within tolerance".format(
            differing, fraction
        )

    return result


def list_baseline_images(baseline_dir):
    """Image filenames recorded as baselines, sorted for stable ordering."""
    if not os.path.isdir(baseline_dir):
        return []
    return sorted(
        name
        for name in os.listdir(baseline_dir)
        if name.lower().endswith(IMAGE_SUFFIXES)
    )


def list_output_images(output_dir, max_images=None):
    """Image filenames the vignette produced, sorted for stable ordering."""
    if not os.path.isdir(output_dir):
        return []
    names = sorted(
        name
        for name in os.listdir(output_dir)
        if name.lower().endswith(IMAGE_SUFFIXES)
    )
    if max_images:
        names = names[:max_images]
    return names


def compare_image_sets(
    baseline_dir, output_dir, tolerance=DEFAULT_IMAGE_TOLERANCE, max_images=None
):
    """Compare every baselined image against the corresponding output.

    Driven by the BASELINE list, not the output list. Comparing only what the
    run happened to produce means a vignette that silently stops emitting an
    image passes; driving from the baseline turns that into MISSING OUTPUT.
    """
    baseline_names = list_baseline_images(baseline_dir)
    if max_images:
        baseline_names = baseline_names[:max_images]

    results = []
    for name in baseline_names:
        results.append(
            compare_single_image(
                os.path.join(baseline_dir, name),
                os.path.join(output_dir, name),
                tolerance=tolerance,
            )
        )

    # Report images the run produced that no baseline covers. Informational
    # only -- a new image is not a regression, but it should be visible so
    # somebody remembers to bless it.
    baselined = set(baseline_names)
    for name in list_output_images(output_dir, max_images=max_images):
        if name not in baselined:
            results.append(
                {
                    "image": name,
                    "status": STATUS_NO_BASELINE,
                    "detail": "Produced by the run but not baselined. "
                    "Re-run with --bless to record it.",
                    "tolerance_fraction": tolerance,
                }
            )
    return results


# ---------------------------------------------------------------------------
# Structured numeric comparison
# ---------------------------------------------------------------------------
def _load_json(path):
    with open(path, "r") as handle:
        return json.load(handle)


def _values_match(actual, expected, rtol, atol):
    """Tolerant equality for the value kinds a results JSON can hold."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(actual) == bool(expected)

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        delta = abs(float(actual) - float(expected))
        allowed = float(atol) + float(rtol) * abs(float(expected))
        return delta <= allowed

    if isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
            return False
        return all(
            _values_match(a, e, rtol, atol) for a, e in zip(actual, expected)
        )

    return actual == expected


def compare_results_json(
    baseline_path, output_path, rtol=DEFAULT_RTOL, atol=DEFAULT_ATOL
):
    """Compare a vignette's structured results against its baseline.

    Deliberate rules:

      * Only `metrics` is compared. `timings` is recorded but never
        regression-checked, because a wall-clock baseline fails whenever the
        machine is busy and teaches people to ignore red tests.

      * Keys present in the output but absent from the baseline are ALLOWED.
        Adding a new metric must not break an existing baseline -- that is
        what keeps this change backwards-compatible with blessed baselines.

      * Keys present in the baseline but absent from the output are a
        failure: a vignette that stops reporting a metric has regressed.

      * Per-key tolerances may be supplied in the baseline under
        `_tolerances`: {"metric_name": {"rtol": 1e-3, "atol": 0.5}}.
    """
    result = {
        "baseline": baseline_path,
        "output": output_path,
        "mismatches": [],
        "missing_metrics": [],
        "assertion_failures": [],
        "rtol": rtol,
        "atol": atol,
    }

    if not os.path.exists(output_path):
        result["status"] = "MISSING OUTPUT"
        result["detail"] = "Vignette produced no results JSON at {0}".format(
            output_path
        )
        return result

    try:
        output_doc = _load_json(output_path)
    except ValueError as exc:
        result["status"] = "ERROR"
        result["detail"] = "Results JSON is not valid JSON: {0}".format(exc)
        return result

    # The vignette's own verdict is authoritative regardless of baselines.
    result["vignette_status"] = output_doc.get("status", "unknown")
    for assertion in output_doc.get("assertions", []):
        if not assertion.get("passed", False):
            result["assertion_failures"].append(
                {
                    "name": assertion.get("name", "<unnamed>"),
                    "detail": assertion.get("detail", ""),
                }
            )

    if not os.path.exists(baseline_path):
        # No numeric baseline yet. Assertions still gate the test, so a
        # vignette without a blessed baseline is not automatically green.
        result["status"] = (
            "FAIL" if result["assertion_failures"] else "NO BASELINE"
        )
        result["detail"] = "No numeric baseline at {0}".format(baseline_path)
        return result

    try:
        baseline_doc = _load_json(baseline_path)
    except ValueError as exc:
        result["status"] = "ERROR"
        result["detail"] = "Baseline JSON is not valid JSON: {0}".format(exc)
        return result

    baseline_metrics = baseline_doc.get("metrics", {})
    output_metrics = output_doc.get("metrics", {})
    per_key = baseline_doc.get("_tolerances", {})

    for key in sorted(baseline_metrics):
        if key not in output_metrics:
            result["missing_metrics"].append(key)
            continue

        overrides = per_key.get(key, {})
        key_rtol = float(overrides.get("rtol", rtol))
        key_atol = float(overrides.get("atol", atol))

        if not _values_match(
            output_metrics[key], baseline_metrics[key], key_rtol, key_atol
        ):
            result["mismatches"].append(
                {
                    "metric": key,
                    "expected": baseline_metrics[key],
                    "actual": output_metrics[key],
                    "rtol": key_rtol,
                    "atol": key_atol,
                }
            )

    result["new_metrics"] = sorted(
        key for key in output_metrics if key not in baseline_metrics
    )

    failed = (
        result["mismatches"]
        or result["missing_metrics"]
        or result["assertion_failures"]
        or result["vignette_status"] not in ("ok", "unknown")
    )
    result["status"] = "FAIL" if failed else "PASS"
    return result


def compare_csv(
    baseline_path,
    output_path,
    key_columns=None,
    ignore_columns=None,
    rtol=1e-3,
    atol=1e-6,
):
    """Compare two CSV files row by row with numeric tolerance.

    `key_columns` names the columns that identify a row; when omitted rows are
    matched by position. `ignore_columns` skips volatile columns -- hostnames,
    wall times -- that legitimately change between runs.
    """
    result = {
        "baseline": baseline_path,
        "output": output_path,
        "mismatches": [],
        "row_count_delta": 0,
    }
    ignore = set(ignore_columns or ())

    if not os.path.exists(output_path):
        result["status"] = "MISSING OUTPUT"
        return result
    if not os.path.exists(baseline_path):
        result["status"] = "NO BASELINE"
        return result

    def read_rows(path):
        with open(path, "r") as handle:
            return list(csv.DictReader(handle))

    baseline_rows = read_rows(baseline_path)
    output_rows = read_rows(output_path)
    result["row_count_delta"] = len(output_rows) - len(baseline_rows)

    if key_columns:
        def row_key(row):
            return tuple(row.get(col, "") for col in key_columns)

        output_index = {}
        for row in output_rows:
            output_index[row_key(row)] = row
        pairs = [
            (row, output_index.get(row_key(row))) for row in baseline_rows
        ]
    else:
        pairs = [
            (baseline_rows[i], output_rows[i] if i < len(output_rows) else None)
            for i in range(len(baseline_rows))
        ]

    for index, (baseline_row, output_row) in enumerate(pairs):
        if output_row is None:
            result["mismatches"].append(
                {"row": index, "column": "*", "detail": "row missing from output"}
            )
            continue

        for column, expected in baseline_row.items():
            if column in ignore:
                continue
            actual = output_row.get(column)
            if actual is None:
                result["mismatches"].append(
                    {"row": index, "column": column, "detail": "column missing"}
                )
                continue
            if not _cells_match(actual, expected, rtol, atol):
                result["mismatches"].append(
                    {
                        "row": index,
                        "column": column,
                        "expected": expected,
                        "actual": actual,
                    }
                )

    # A changed row count is a failure in its own right, even when every row
    # that survived still matches. Extracting a different number of timesteps
    # is a deliberate change, and a deliberate change wants a re-bless rather
    # than a silent pass.
    result["status"] = (
        "FAIL" if (result["mismatches"] or result["row_count_delta"]) else "PASS"
    )
    return result


def _cells_match(actual, expected, rtol, atol):
    try:
        return _values_match(float(actual), float(expected), rtol, atol)
    except (TypeError, ValueError):
        return str(actual).strip() == str(expected).strip()


# ---------------------------------------------------------------------------
# Legacy text comparison
# ---------------------------------------------------------------------------
DEFAULT_IGNORE_PATTERNS = [
    r"/[^ ]+/",                      # file paths
    r"[a-zA-Z]:\\[^ ]+",             # Windows paths
    r"\d{2,4}[-/]\d{2}[-/]\d{2,4}",  # dates
    r"\d+:\d+:\d+",                  # timestamps
]


def compare_text_files(output_log, known_good_value_path, ignore_patterns=None):
    """Subset match of a known-good log against the run's output.

    Preserved verbatim in behaviour from the original harness so that every
    existing known_good_value.txt baseline keeps passing unchanged. It is a
    weak assertion -- order-insensitive, subset-only, and it strips anything
    path-shaped -- which is precisely why compare_results_json() exists
    alongside it for new vignettes.
    """
    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORE_PATTERNS

    def clean_content(content):
        for pattern in ignore_patterns:
            content = re.sub(pattern, "", content)
        return content.strip()

    with open(output_log, "r") as log_file:
        log_content = log_file.readlines()
    log_content = [clean_content(line) for line in log_content if clean_content(line)]

    with open(known_good_value_path, "r") as known_good_file:
        known_good_content = known_good_file.readlines()
    known_good_content = [
        clean_content(line) for line in known_good_content if clean_content(line)
    ]

    for known_line in known_good_content:
        if known_line not in log_content:
            return False
    return True
