#
# Visualization Vignettes
#
# test_suite.py
#
# Regression and performance driver for the ParaView and VisIt vignettes.
#
# WHAT CHANGED AND WHY
#
#   The suite can now fail. check_failure() used to read only
#   text_comparison_results.json, so image comparison ran, wrote its verdict
#   to disk, and was then ignored by the one function that sets the exit
#   code. A vignette could render a black frame and CI stayed green. Image
#   results, numeric results, and the subprocess exit code are all gates now.
#
#   Blessing is explicit. Baselines used to be created automatically from the
#   current output immediately before comparing against them, so a first run
#   always passed and a deleted baseline silently re-blessed itself. Baseline
#   creation now happens only under --bless; a missing baseline is a failure.
#
#   Numeric CSV extracts are a gate. A vignette declares a CSV with
#   ctx.add_numeric_extract(); the harness compares it against the blessed
#   copy cell by cell with verify.compare_csv and a per-file tolerance. That
#   is how ex12 in both suites regression-tests numbers rather than pixels.
#
#   Rank count is a parameter. --ranks/--nodes flow through to run_tests.py
#   and from there to mpirun/srun for ParaView and to OpenComputeEngine for
#   VisIt.
#
#   The performance history is opt-out. performance_metrics_<machine>.json is
#   committed to git, so an experimental or debugging run used to leave a
#   permanent mark on a record other people read. --no-metrics (alias
#   --ephemeral) runs every test and every comparison exactly as usual but
#   appends nothing, and Testing/manage_metrics.py prunes records that are
#   already there.
#
#   Every record now carries a run_id shared by all vignettes in one
#   invocation, so a single suite run can be identified -- and removed -- as
#   a unit. Older records have no run_id and are untouched by its addition.
#
# BACKWARDS COMPATIBILITY
#
#   Every result filename, status spelling, and JSON layout the old harness
#   produced is preserved. Existing known_good_value.txt baselines are still
#   compared exactly as before. Numeric comparison of the structured results
#   JSON is additive: a vignette without one is not penalised for it.
#
# Author: James Kress, <james@jameskress.com>
#
import argparse
import datetime
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid

import pandas as pd

import verify
from metrics import child_rusage_snapshot, detect_significant_changes, gather_metrics
from plot_metrics import generate_individual_graphs
from run_tests import RUN_RESULT_FILENAME, read_run_result


# Result artifacts written inside each vignette's Testing/ directory.
IMAGE_RESULTS_FILENAME = "image_comparison_results.json"
TEXT_RESULTS_FILENAME = "text_comparison_results.json"
NUMERIC_RESULTS_FILENAME = "results_comparison.json"
CSV_RESULTS_FILENAME = "csv_comparison_results.json"


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------
def build_run_command(test_dir, args):
    """Assemble the run_tests.py invocation for one vignette."""
    run_tests_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "run_tests.py"
    )

    python_exec = shutil.which("python") or shutil.which("python3") or sys.executable
    cmd = [
        python_exec,
        run_tests_path,
        test_dir,
        "--tool",
        args.test_type,
        "--ranks",
        str(args.ranks),
        "--nodes",
        str(args.nodes),
        "--launcher",
        args.launcher,
        "--machine",
        args.machine,
        "--partition",
        args.partition,
        "--walltime",
        args.walltime,
        "--timeout",
        str(args.timeout),
    ]
    if args.threads:
        cmd += ["--threads", str(args.threads)]
    if args.account:
        cmd += ["--account", args.account]
    if args.data_dir:
        cmd += ["--data-dir", args.data_dir]
    if args.image_width:
        cmd += ["--image-width", str(args.image_width)]
    if args.image_height:
        cmd += ["--image-height", str(args.image_height)]
    if args.timesteps:
        cmd += ["--timesteps", str(args.timesteps)]
    if not args.offscreen:
        cmd.append("--no-offscreen")
    if not args.write_metrics:
        cmd.append("--no-metrics")
    if args.verbose:
        cmd.append("--verbose")
    for extra in args.vignette_arg:
        cmd += ["--vignette-arg", extra]
    return cmd, run_tests_path


def run_local_test(test_dir, args):
    """Run one vignette locally and return run_tests.py's recorded result."""
    cmd, run_tests_path = build_run_command(test_dir, args)

    if not os.path.exists(run_tests_path):
        print("run_tests.py not found at {0}".format(run_tests_path))
        return {
            "succeeded": False,
            "returncode": 127,
            "error": "run_tests.py missing",
            "timed_out": False,
        }

    completed = subprocess.run(cmd)

    testing_dir = os.path.join(test_dir, "Testing")
    payload = read_run_result(testing_dir)
    if payload is None:
        # run_tests.py always writes this file; its absence means the launch
        # itself failed in a way that must not be silently swallowed.
        payload = {
            "succeeded": completed.returncode == 0,
            "returncode": completed.returncode,
            "timed_out": False,
            "error": "run_tests.py wrote no {0}".format(RUN_RESULT_FILENAME),
        }
    return payload


def submit_cluster_test(test_dir, cluster_script):
    """Submit the vignette to Slurm.

    Returns the job id when sbatch accepted it. Submission is asynchronous:
    the comparison stages are skipped for submitted jobs, because comparing
    output that the job has not written yet produces a meaningless verdict.
    Collect results afterwards with --generate-metrics.
    """
    cluster_script_path = os.path.join(test_dir, cluster_script)
    if not os.path.exists(cluster_script_path):
        print("No {0} found in {1}".format(cluster_script, test_dir))
        return None

    completed = subprocess.run(
        ["sbatch", cluster_script_path],
        cwd=test_dir,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print("sbatch failed for {0}: {1}".format(cluster_script_path, completed.stderr))
        return None

    print(completed.stdout.strip())
    match = re.search(r"(\d+)", completed.stdout)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------
# A vignette directory is exNN_<name>. Matching on a bare "ex" prefix also
# swept up unrelated directories -- ParaView_Vignettes/extracts/ among them --
# and tried to run them as tests.
VIGNETTE_DIR_RE = re.compile(r"^ex(\d+)_")


def is_vignette_dir(name, parent):
    """True when `name` is a vignette directory rather than a stray folder."""
    return bool(VIGNETTE_DIR_RE.match(name)) and os.path.isdir(
        os.path.join(parent, name)
    )


def extract_example_number(dir_name):
    """Numeric part of a vignette directory name, for correct ordering."""
    match = VIGNETTE_DIR_RE.match(dir_name)
    if match:
        return int(match.group(1))
    return float("inf")


def vignette_script_name(test_dir):
    """Base name of the vignette script, used to locate its results JSON."""
    dir_name = os.path.basename(os.path.normpath(test_dir))
    preferred = os.path.join(test_dir, dir_name + ".py")
    if os.path.isfile(preferred):
        return dir_name

    candidates = [
        name[:-3]
        for name in sorted(os.listdir(test_dir))
        if name.endswith(".py")
        and not name.endswith(("_make_state.py", "_validate.py", "_common.py"))
        and not name.startswith(("make_", "run_", "conftest"))
    ]
    return candidates[0] if candidates else dir_name


# ---------------------------------------------------------------------------
# Performance logging
# ---------------------------------------------------------------------------
def new_run_id():
    """An identifier shared by every record one suite invocation writes.

    Timestamp first so the ids sort chronologically, with a short random
    suffix so two runs started in the same second on different nodes -- which
    is exactly what a scaling sweep does -- cannot collide.
    """
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    return "{0}-{1}".format(stamp, uuid.uuid4().hex[:6])


def log_performance(
    test_name,
    metrics,
    output_dir,
    args_machine_name,
    paraview_version=None,
    visit_version=None,
    run_id=None,
):
    """Append this run's metrics to the machine-specific history file.

    Callers suppress this entirely under --no-metrics; it is never called
    with a flag that makes it a no-op, because a function that silently does
    nothing is harder to reason about than one that is not called.
    """
    machine_info = platform.uname()

    machine_details = {
        "system": machine_info.system,
        "node": machine_info.node,
        "release": machine_info.release,
        "version": machine_info.version,
        "machine": machine_info.machine,
        "processor": machine_info.processor,
        "paraview_version": paraview_version,
        "visit_version": visit_version,
    }

    metrics = dict(metrics)
    metrics["machine_info"] = machine_details
    if run_id:
        metrics["run_id"] = run_id

    timestamp = datetime.datetime.now().isoformat()

    testing_dir = os.path.join(output_dir, "Testing")
    os.makedirs(testing_dir, exist_ok=True)

    machine_name = args_machine_name if args_machine_name else platform.uname().node
    log_file = os.path.join(
        testing_dir, "performance_metrics_{0}.json".format(machine_name)
    )

    data = {}
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as handle:
                data = json.load(handle)
        except ValueError:
            print(
                "Warning: {0} is not valid JSON; starting a new history.".format(
                    log_file
                )
            )
            data = {}

    data[timestamp] = metrics

    # Write through a temporary file and rename. The original seeked to 0 and
    # rewrote in place without truncating, which corrupts the document the
    # first time the new content is shorter than the old.
    #
    # The trailing newline matches the 112 history files already committed.
    # Without it every append rewrites the last line as "\ No newline at end
    # of file" and the diff is noise on top of the one added record.
    temp_file = log_file + ".tmp"
    with open(temp_file, "w") as handle:
        json.dump(data, handle, indent=4)
        handle.write("\n")
    os.replace(temp_file, log_file)


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------
def create_baseline_images(output_dir, max_images=5):
    """Copy rendered images into the baseline directory.

    Called only under --bless. During a normal run a missing baseline is a
    failure, because a baseline created from the run it is about to be
    compared against is not a test.
    """
    output_images_dir = os.path.join(output_dir, "output")
    baseline_dir = os.path.join(output_dir, "Testing", "Baseline")
    os.makedirs(baseline_dir, exist_ok=True)

    if not os.path.exists(output_images_dir):
        print(
            "No output images found in {0}. Skipping baseline creation.".format(
                output_images_dir
            )
        )
        return []

    selected_images = verify.list_output_images(output_images_dir, max_images=max_images)
    for image in selected_images:
        shutil.copy(
            os.path.join(output_images_dir, image), os.path.join(baseline_dir, image)
        )
        print("  blessed image: {0}".format(image))
    return selected_images


def bless_numeric_baseline(test_dir):
    """Copy the structured results JSON into the baseline directory."""
    script_name = vignette_script_name(test_dir)
    results_name = "{0}_results.json".format(script_name)
    produced = os.path.join(test_dir, "Testing", results_name)
    if not os.path.exists(produced):
        return None

    baseline_dir = os.path.join(test_dir, "Testing", "Baseline")
    os.makedirs(baseline_dir, exist_ok=True)
    destination = os.path.join(baseline_dir, results_name)
    shutil.copy(produced, destination)
    print("  blessed metrics: {0}".format(results_name))
    return destination


def bless_csv_baselines(test_dir):
    """Copy every declared numeric CSV extract into the baseline directory."""
    declared = declared_numeric_extracts(test_dir)
    if not declared:
        return []

    output_dir = os.path.join(test_dir, "output")
    baseline_dir = os.path.join(test_dir, "Testing", "Baseline")
    os.makedirs(baseline_dir, exist_ok=True)

    blessed = []
    for item in declared:
        filename = item["file"]
        produced = os.path.join(output_dir, filename)
        if not os.path.exists(produced):
            print(
                "  cannot bless {0}: the vignette declared it but did not "
                "write it".format(filename)
            )
            continue
        shutil.copy(produced, os.path.join(baseline_dir, filename))
        print("  blessed numeric extract: {0}".format(filename))
        blessed.append(filename)
    return blessed


def bless_test(test_dir, args):
    """Record baselines for one vignette from the run that just happened."""
    print("Blessing baselines for {0}".format(os.path.basename(test_dir)))
    create_baseline_images(test_dir, max_images=args.max_baseline_images)
    bless_numeric_baseline(test_dir)
    bless_csv_baselines(test_dir)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def resize_to_match(baseline_image, output_image):
    """Deprecated shim retained so external callers do not break.

    The suite no longer resizes before diffing: a resolution change is a
    regression to report, most often an offscreen job that silently fell back
    to software rendering. Kept as an identity function with a warning.
    """
    print(
        "Warning: resize_to_match() is deprecated and no longer used. "
        "Resolution mismatches are reported as failures instead."
    )
    return output_image


def compare_images(baseline_dir, output_dir, selected_images=None, tolerance=None):
    """Compare rendered images against baselines at native resolution.

    `selected_images` is accepted for backwards compatibility; when supplied
    it restricts the comparison to those filenames. When omitted, every
    baselined image is compared, which is the stronger check because it
    catches a vignette that has stopped producing an image entirely.
    """
    if tolerance is None:
        tolerance = verify.DEFAULT_IMAGE_TOLERANCE

    output_images_dir = os.path.join(output_dir, "output")

    if selected_images:
        results = []
        for image in selected_images:
            results.append(
                verify.compare_single_image(
                    os.path.join(baseline_dir, image),
                    os.path.join(output_images_dir, image),
                    tolerance=tolerance,
                )
            )
        return results

    return verify.compare_image_sets(baseline_dir, output_images_dir, tolerance=tolerance)


def compare_text_files(output_log, known_good_value_path, ignore_patterns=None):
    """Legacy text comparison, preserved verbatim. See verify.compare_text_files."""
    return verify.compare_text_files(output_log, known_good_value_path, ignore_patterns)


def declared_numeric_extracts(test_dir):
    """The CSV extracts a vignette declared in its last results JSON.

    Read from the produced results rather than inferred from the output
    directory, because write_timing_csv() also writes a CSV there and a
    wall-clock file compared against a baseline is a test that fails whenever
    the machine is busy. Only what the vignette explicitly declared is
    compared.
    """
    script_name = vignette_script_name(test_dir)
    results_path = os.path.join(
        test_dir, "Testing", "{0}_results.json".format(script_name)
    )
    if not os.path.exists(results_path):
        return []

    try:
        with open(results_path, "r") as handle:
            document = json.load(handle)
    except (ValueError, OSError):
        return []

    declared = document.get("numeric_extracts") or []
    return [item for item in declared if isinstance(item, dict) and item.get("file")]


def compare_csv_extracts(test_dir, args):
    """Compare every declared CSV extract against its blessed baseline.

    Returns a list of verify.compare_csv results, or an empty list for a
    vignette that declares none -- which is every vignette except ex12 in
    each suite, and which is not a failure.
    """
    declared = declared_numeric_extracts(test_dir)
    if not declared:
        return []

    output_dir = os.path.join(test_dir, "output")
    baseline_dir = os.path.join(test_dir, "Testing", "Baseline")

    results = []
    for item in declared:
        filename = item["file"]
        result = verify.compare_csv(
            os.path.join(baseline_dir, filename),
            os.path.join(output_dir, filename),
            key_columns=item.get("key_columns"),
            ignore_columns=item.get("ignore_columns"),
            rtol=float(item.get("rtol", args.rtol)),
            atol=float(item.get("atol", args.atol)),
        )
        result["file"] = filename
        results.append(result)
        print(
            "\tCSV {0}: {1}{2}".format(
                filename,
                result.get("status"),
                " ({0} mismatch(es))".format(len(result.get("mismatches", [])))
                if result.get("mismatches")
                else "",
            )
        )
    return results


def compare_numeric_results(test_dir, args):
    """Compare the structured results JSON against its baseline."""
    script_name = vignette_script_name(test_dir)
    results_name = "{0}_results.json".format(script_name)

    produced = os.path.join(test_dir, "Testing", results_name)
    baseline = os.path.join(test_dir, "Testing", "Baseline", results_name)

    if not os.path.exists(produced) and not os.path.exists(baseline):
        # This vignette does not emit structured results. Nothing to compare,
        # and nothing to complain about -- older vignettes are unaffected.
        return None

    return verify.compare_results_json(
        baseline, produced, rtol=args.rtol, atol=args.atol
    )


def is_gpu_test_allowed_to_fail(test_dir):
    """Tests that legitimately fail without a GPU."""
    gpu_required_tests = ["ex00_pvQuery", "ex08_pvBackendCheck", "ex08_visitBackendCheck"]

    parent_dir = os.path.basename(os.path.dirname(test_dir))
    if VIGNETTE_DIR_RE.match(parent_dir):
        return parent_dir in gpu_required_tests
    return False


# ---------------------------------------------------------------------------
# Failure gate
# ---------------------------------------------------------------------------
def check_failure(test_dir, non_gpu_machine):
    """Decide whether a vignette failed.

    `test_dir` is the vignette's Testing/ directory. Five independent gates,
    any one of which fails the test:

      1. the subprocess exit code recorded by run_tests.py
      2. image comparison verdicts
      3. numeric comparison of the structured results
      4. numeric comparison of declared CSV extracts
      5. the legacy text comparison

    The original checked only (5).
    """
    reasons = []

    # -- 1. subprocess exit code ----------------------------------------
    run_result = read_run_result(test_dir)
    if run_result is not None and not run_result.get("succeeded", False):
        detail = "exit code {0}".format(run_result.get("returncode"))
        if run_result.get("timed_out"):
            detail += " (timed out)"
        if run_result.get("error"):
            detail += " ({0})".format(run_result["error"])
        reasons.append("vignette process failed: {0}".format(detail))

    # -- 2. image comparison ---------------------------------------------
    image_file = os.path.join(test_dir, IMAGE_RESULTS_FILENAME)
    if os.path.exists(image_file):
        try:
            with open(image_file, "r") as handle:
                image_results = json.load(handle)
        except ValueError:
            reasons.append("{0} is not valid JSON".format(IMAGE_RESULTS_FILENAME))
            image_results = []

        for result in image_results:
            if verify.is_image_failure(result.get("status", "")):
                reasons.append(
                    "image {0}: {1}{2}".format(
                        result.get("image", "<unknown>"),
                        result.get("status"),
                        " -- " + result["detail"] if result.get("detail") else "",
                    )
                )

    # -- 3. numeric comparison -------------------------------------------
    numeric_file = os.path.join(test_dir, NUMERIC_RESULTS_FILENAME)
    if os.path.exists(numeric_file):
        try:
            with open(numeric_file, "r") as handle:
                numeric = json.load(handle)
        except ValueError:
            numeric = {"status": "ERROR", "detail": "invalid JSON"}

        status = numeric.get("status")
        if status in ("FAIL", "ERROR", "MISSING OUTPUT", "NO BASELINE"):
            for item in numeric.get("assertion_failures", []):
                reasons.append(
                    "assertion failed: {0} {1}".format(item["name"], item["detail"])
                )
            for item in numeric.get("mismatches", []):
                reasons.append(
                    "metric {0}: expected {1}, got {2}".format(
                        item["metric"], item["expected"], item["actual"]
                    )
                )
            for key in numeric.get("missing_metrics", []):
                reasons.append("metric no longer reported: {0}".format(key))
            if not reasons or status in ("ERROR", "MISSING OUTPUT", "NO BASELINE"):
                reasons.append(
                    "numeric results {0}: {1}".format(
                        status, numeric.get("detail", "")
                    )
                )

    # -- 4. declared CSV extracts ----------------------------------------
    csv_file = os.path.join(test_dir, CSV_RESULTS_FILENAME)
    if os.path.exists(csv_file):
        try:
            with open(csv_file, "r") as handle:
                csv_results = json.load(handle)
        except ValueError:
            reasons.append("{0} is not valid JSON".format(CSV_RESULTS_FILENAME))
            csv_results = []

        for result in csv_results:
            status = result.get("status")
            name = result.get("file", "<unknown>")
            if status in ("MISSING OUTPUT", "NO BASELINE", "ERROR"):
                reasons.append("csv {0}: {1}".format(name, status))
                continue
            if result.get("row_count_delta"):
                reasons.append(
                    "csv {0}: row count changed by {1}".format(
                        name, result["row_count_delta"]
                    )
                )
            for mismatch in result.get("mismatches", []):
                reasons.append(
                    "csv {0} row {1} column {2}: {3}".format(
                        name,
                        mismatch.get("row"),
                        mismatch.get("column"),
                        mismatch.get(
                            "detail",
                            "expected {0}, got {1}".format(
                                mismatch.get("expected"), mismatch.get("actual")
                            ),
                        ),
                    )
                )

    # -- 5. legacy text comparison ---------------------------------------
    text_comparison_file = os.path.join(test_dir, TEXT_RESULTS_FILENAME)
    if os.path.exists(text_comparison_file):
        try:
            with open(text_comparison_file, "r") as handle:
                text_comparison_results = json.load(handle)
        except ValueError:
            text_comparison_results = []

        for result in text_comparison_results:
            if result.get("logs_match") is False:
                reasons.append("output.log does not match known_good_value.txt")

    if not reasons:
        return False

    if is_gpu_test_allowed_to_fail(test_dir) and non_gpu_machine:
        print("\tNon-GPU test failure allowed for {0}:".format(test_dir))
        for reason in reasons:
            print("\t\t- {0}".format(reason))
        return False

    print("\tTest failure in {0}:".format(test_dir))
    for reason in reasons:
        print("\t\t- {0}".format(reason))
    return True


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def create_summary_report(
    test_directory,
    test_type,
    args_machine_name,
    args_non_gpu_machine,
    check_performance=True,
):
    """Aggregate every vignette's verdict into one report.

    `check_performance` is False under --no-metrics. The performance gate
    compares the two most recent records in the history file, and under
    --no-metrics this run wrote none -- so the gate would compare two earlier
    runs and attribute their difference to this one. Reporting nothing is
    correct; reporting a stale verdict is not.
    """
    summary_report = {
        "test_results": {},
        "any_tests_failed": False,
        "failed_image_comparisons": [],
        "failed_text_comparisons": [],
        "failed_numeric_comparisons": [],
        "failed_csv_comparisons": [],
        "failed_runs": [],
        "significant_performance_changes": [],
    }

    machine_name = args_machine_name if args_machine_name else platform.uname().node
    print("\nCreating test summary report for: {0}".format(machine_name))

    subdirectories = sorted(
        [d for d in os.listdir(test_directory) if is_vignette_dir(d, test_directory)],
        key=extract_example_number,
    )

    for subdir in subdirectories:
        subdir_path = os.path.join(test_directory, subdir)
        testing_dir = os.path.join(subdir_path, "Testing")

        if not os.path.exists(testing_dir):
            continue

        test_status = {
            "test_name": subdir,
            "run_succeeded": True,
            "image_comparison_passed": True,
            "text_comparison_passed": True,
            "numeric_comparison_passed": True,
            "csv_comparison_passed": True,
            "performance_stable": True,
        }

        gpu_exempt = is_gpu_test_allowed_to_fail(testing_dir) and args_non_gpu_machine

        # -- subprocess exit code -----------------------------------------
        run_result = read_run_result(testing_dir)
        if run_result is not None and not run_result.get("succeeded", False):
            if gpu_exempt:
                print(
                    "\t\tRun failure detected but was expected on a non-GPU "
                    "machine: \n\t\t\t{0}".format(subdir)
                )
            else:
                test_status["run_succeeded"] = False
                summary_report["failed_runs"].append(
                    {subdir: {"returncode": run_result.get("returncode")}}
                )
                summary_report["any_tests_failed"] = True

        # -- image comparison ---------------------------------------------
        comparison_file = os.path.join(testing_dir, IMAGE_RESULTS_FILENAME)
        if os.path.exists(comparison_file):
            try:
                with open(comparison_file, "r") as handle:
                    comparison_results = json.load(handle)
            except ValueError:
                comparison_results = []

            for result in comparison_results:
                if verify.is_image_failure(result.get("status", "")):
                    if gpu_exempt:
                        continue
                    test_status["image_comparison_passed"] = False
                    summary_report["failed_image_comparisons"].append({subdir: result})
                    summary_report["any_tests_failed"] = True

        # -- numeric comparison -------------------------------------------
        numeric_file = os.path.join(testing_dir, NUMERIC_RESULTS_FILENAME)
        if os.path.exists(numeric_file):
            try:
                with open(numeric_file, "r") as handle:
                    numeric = json.load(handle)
            except ValueError:
                numeric = {"status": "ERROR"}

            if numeric.get("status") not in ("PASS", None):
                if not gpu_exempt:
                    test_status["numeric_comparison_passed"] = False
                    summary_report["failed_numeric_comparisons"].append(
                        {subdir: numeric}
                    )
                    summary_report["any_tests_failed"] = True

        # -- declared CSV extracts ----------------------------------------
        csv_file = os.path.join(testing_dir, CSV_RESULTS_FILENAME)
        if os.path.exists(csv_file):
            try:
                with open(csv_file, "r") as handle:
                    csv_results = json.load(handle)
            except ValueError:
                csv_results = [{"status": "ERROR", "file": CSV_RESULTS_FILENAME}]

            for result in csv_results:
                bad = (
                    result.get("status") not in ("PASS", None)
                    or result.get("mismatches")
                    or result.get("row_count_delta")
                )
                if bad and not gpu_exempt:
                    test_status["csv_comparison_passed"] = False
                    summary_report["failed_csv_comparisons"].append({subdir: result})
                    summary_report["any_tests_failed"] = True

        # -- legacy text comparison ---------------------------------------
        text_comparison_file = os.path.join(testing_dir, TEXT_RESULTS_FILENAME)
        if os.path.exists(text_comparison_file):
            print("\n\n\tOutput comparison file found: {0}".format(text_comparison_file))
            try:
                with open(text_comparison_file, "r") as handle:
                    text_comparison_results = json.load(handle)
            except ValueError:
                text_comparison_results = []

            for result in text_comparison_results:
                if result.get("logs_match") is False:
                    if gpu_exempt:
                        test_status["text_comparison_passed"] = True
                        print(
                            "\t\tTest failure detected but was expected, not "
                            "triggering error: \n\t\t\t{0}".format(subdir)
                        )
                    else:
                        test_status["text_comparison_passed"] = False
                        summary_report["failed_text_comparisons"].append(subdir)
                        print(
                            "\t\tTest failure detected, which was unexpected: "
                            "\n\t\t\t{0}".format(subdir)
                        )
                        summary_report["any_tests_failed"] = True
            print("\t\tFinished output comparison logs.")

        # -- performance --------------------------------------------------
        performance_file = os.path.join(
            testing_dir, "performance_metrics_{0}.json".format(machine_name)
        )
        if not check_performance:
            print(
                "\n\t--no-metrics: this run appended no history, so the "
                "performance gate is skipped rather than comparing two "
                "earlier runs."
            )
        elif os.path.exists(performance_file):
            print("\tPerformance file found: {0}".format(performance_file))
            try:
                with open(performance_file, "r") as handle:
                    performance_data = json.load(handle)
            except ValueError:
                performance_data = {}

            if performance_data:
                formatted_data = [
                    dict({"timestamp": timestamp}, **metrics)
                    for timestamp, metrics in performance_data.items()
                ]
                df = pd.DataFrame(formatted_data).sort_values("timestamp")
                significant_changes = detect_significant_changes(df)

                if significant_changes:
                    test_status["performance_stable"] = significant_changes
                    summary_report["significant_performance_changes"].append(
                        {subdir: significant_changes}
                    )
                    summary_report["any_tests_failed"] = True
        else:
            print("\n\tPerformance file not found: {0}".format(performance_file))

        summary_report["test_results"][subdir] = test_status

    report_name = test_type + "_" + machine_name + "_summary_report.json"
    summary_report_path = os.path.join(os.path.dirname(__file__), report_name)
    with open(summary_report_path, "w") as handle:
        json.dump(summary_report, handle, indent=4)

    print("\nSummary report saved at: {0}".format(summary_report_path))
    return summary_report


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def clean_test_files(test_directory):
    """Remove generated files from a Testing directory."""
    files_to_clean = [
        IMAGE_RESULTS_FILENAME,
        TEXT_RESULTS_FILENAME,
        NUMERIC_RESULTS_FILENAME,
        CSV_RESULTS_FILENAME,
        RUN_RESULT_FILENAME,
        "output.log",
        "error.log",
        "*_results.json",
        "execution_time_*.png",
        "cpu_usage_*.png",
        "memory_usage_*.png",
        "*_summary_report.json",
        "visitlog.py",
    ]

    for filename in files_to_clean:
        for file_path in glob.glob(os.path.join(test_directory, filename)):
            # Never delete anything under Baseline/ -- blessed baselines are
            # inputs to the test, not products of it.
            if "Baseline" in os.path.normpath(file_path).split(os.sep):
                continue
            if os.path.isfile(file_path):
                os.remove(file_path)
                print("Removed: {0}".format(file_path))


def clean_tests(test_directory, example_dirs, args):
    """Clean every vignette's Testing directory, plus the suite directory."""
    for test_dir in example_dirs:
        print("Cleaning {0}...".format(test_dir))
        testing_dir = os.path.join(test_directory, test_dir, "Testing")
        clean_test_files(testing_dir)
        print("Clean-up of {0} complete.\n".format(testing_dir))

    main_testing_dir = os.path.dirname(os.path.abspath(__file__))
    clean_test_files(main_testing_dir)
    print("Clean-up of {0} complete.".format(main_testing_dir))


# ---------------------------------------------------------------------------
# Per-test driver
# ---------------------------------------------------------------------------
def run_test(test_dir, dir_name, args):
    """Run, compare, and record one vignette."""
    print("\n\nRunning {0}".format(test_dir))

    testing_dir = os.path.join(test_dir, "Testing")
    os.makedirs(testing_dir, exist_ok=True)

    if args.submit:
        print("Submitting {0} to cluster.".format(dir_name))
        # Submission scripts are named by the exNN prefix, not the full
        # directory name: ex07_ibex_runScript.sbat, not
        # ex07_pvScaling_ibex_runScript.sbat. The original built the latter
        # and so never found a script to submit.
        prefix_match = VIGNETTE_DIR_RE.match(dir_name)
        prefix = "ex{0}".format(prefix_match.group(1)) if prefix_match else dir_name
        script = "{0}_{1}_runScript.sbat".format(
            prefix, "shaheen" if args.machine == "shaheen" else "ibex"
        )
        job_id = submit_cluster_test(test_dir, script)
        if job_id:
            print(
                "Submitted job {0}. Comparison is skipped for submitted jobs; "
                "re-run with --generate-metrics once the job completes.".format(job_id)
            )
        return

    if not args.generate_metrics:
        print("Running {0} locally.".format(dir_name))
        rusage_before = child_rusage_snapshot()
        start_time = time.time()
        run_result = run_local_test(test_dir, args)
        end_time = time.time()

        metrics = gather_metrics(
            dir_name, start_time, end_time, run_result=run_result, before=rusage_before
        )
        if args.write_metrics:
            log_performance(
                dir_name,
                metrics,
                test_dir,
                args.machine_name,
                paraview_version=args.paraview_version,
                visit_version=args.visit_version,
                run_id=getattr(args, "run_id", None),
            )
        else:
            print(
                "  --no-metrics: ran in {0:.2f}s, {1:.1f} MB peak; nothing "
                "appended to the committed history.".format(
                    metrics.get("execution_time", 0.0),
                    metrics.get("memory_usage_mb", 0.0),
                )
            )

        if not run_result.get("succeeded", False):
            print(
                "  vignette exited {0}; comparisons will still run so the "
                "report shows what was produced.".format(run_result.get("returncode"))
            )

    # -- blessing --------------------------------------------------------
    if args.bless:
        bless_test(test_dir, args)

    # -- image comparison -------------------------------------------------
    baseline_dir = os.path.join(testing_dir, "Baseline")
    comparison_results = compare_images(
        baseline_dir, test_dir, tolerance=args.image_tolerance
    )
    with open(os.path.join(testing_dir, IMAGE_RESULTS_FILENAME), "w") as handle:
        json.dump(comparison_results, handle, indent=4)

    # -- numeric comparison ------------------------------------------------
    numeric = compare_numeric_results(test_dir, args)
    if numeric is not None:
        with open(os.path.join(testing_dir, NUMERIC_RESULTS_FILENAME), "w") as handle:
            json.dump(numeric, handle, indent=4)

    # -- declared CSV extracts ---------------------------------------------
    csv_results = compare_csv_extracts(test_dir, args)
    if csv_results:
        with open(os.path.join(testing_dir, CSV_RESULTS_FILENAME), "w") as handle:
            json.dump(csv_results, handle, indent=4)

    # -- legacy text comparison -------------------------------------------
    output_log_path = os.path.join(testing_dir, "output.log")
    if os.path.exists(output_log_path):
        known_good_value_file = os.path.join(baseline_dir, "known_good_value.txt")
        if os.path.exists(known_good_value_file):
            text_comparison_result = compare_text_files(
                output_log_path, known_good_value_file
            )
            with open(os.path.join(testing_dir, TEXT_RESULTS_FILENAME), "w") as handle:
                json.dump([{"logs_match": text_comparison_result}], handle, indent=4)
        else:
            print("Known good value file not found: {0}".format(known_good_value_file))
    else:
        print("Cannot find output.log file @ path: {0}".format(output_log_path))

    print("Generating metrics and graphs for {0}.".format(dir_name))
    generate_individual_graphs(test_dir, dir_name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        description="Run or submit the Visualization Vignettes test suite.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("root_directory", type=str, help="Root dir of repo.")
    parser.add_argument("--test_type", required=True, type=str, help="VisIt/ParaView")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit tests to cluster instead of running locally.",
    )
    parser.add_argument(
        "--generate-metrics",
        action="store_true",
        help="Generate metrics and graphs without running tests.",
    )
    parser.add_argument(
        "--clean", action="store_true", help="Clean up generated test files"
    )
    parser.add_argument(
        "--test_number",
        type=int,
        nargs="+",
        help="Specify one or more test numbers to run (e.g. 0 for ex00).",
    )
    parser.add_argument(
        "--machine_name",
        type=str,
        help="Machine name used in performance metric filenames. Keep this "
        "stable across runs or the history never accumulates and the "
        "performance gate can never fire.",
    )
    parser.add_argument(
        "--paraview_version", type=str, default=None, help="ParaView version."
    )
    parser.add_argument("--visit_version", type=str, default=None, help="VisIt version.")
    parser.add_argument(
        "--non_gpu_machine",
        action="store_true",
        default=False,
        help="Tests are running on a non-GPU machine.",
    )

    history_group = parser.add_argument_group("performance history")
    history_group.add_argument(
        "--no-metrics",
        "--ephemeral",
        dest="write_metrics",
        action="store_false",
        default=True,
        help="Run and compare exactly as usual, but append nothing to the "
        "committed performance_metrics_<machine>.json history. Use it for "
        "experimental, debugging, or throwaway runs. The performance "
        "regression gate is skipped too, because this run contributes no "
        "record for it to compare against. Prune records that are already "
        "committed with Testing/manage_metrics.py.",
    )
    history_group.add_argument(
        "--run-id",
        dest="run_id",
        default=None,
        help="Tag every record this invocation writes with this identifier. "
        "Defaults to a generated timestamp-plus-suffix id. Pass one "
        "explicitly to group several invocations -- ParaView and VisIt, say "
        "-- into a single logical run for manage_metrics.py --remove-run.",
    )

    bless_group = parser.add_argument_group("baselines")
    bless_group.add_argument(
        "--bless",
        action="store_true",
        help="Record the current output as the baseline. Without this a "
        "missing baseline is a FAILURE -- baselines are never created "
        "automatically during a normal run.",
    )
    bless_group.add_argument(
        "--max-baseline-images",
        type=int,
        default=5,
        help="Maximum images to record per vignette when blessing.",
    )
    bless_group.add_argument(
        "--image-tolerance",
        type=float,
        default=verify.DEFAULT_IMAGE_TOLERANCE,
        help="Fraction of total pixels allowed to differ before an image "
        "comparison fails.",
    )
    bless_group.add_argument(
        "--rtol",
        type=float,
        default=verify.DEFAULT_RTOL,
        help="Relative tolerance for numeric metric comparison.",
    )
    bless_group.add_argument(
        "--atol",
        type=float,
        default=verify.DEFAULT_ATOL,
        help="Absolute tolerance for numeric metric comparison.",
    )

    exec_group = parser.add_argument_group("execution")
    exec_group.add_argument("--ranks", type=int, default=1, help="MPI ranks per test.")
    exec_group.add_argument("--nodes", type=int, default=1, help="Nodes per test.")
    exec_group.add_argument(
        "--threads", type=int, default=None, help="Threads per rank."
    )
    exec_group.add_argument(
        "--launcher",
        choices=("auto", "mpirun", "srun", "none"),
        default="auto",
        help="How to launch pvbatch.",
    )
    exec_group.add_argument(
        "--machine",
        choices=("local", "ibex", "shaheen"),
        default="local",
        help="Execution site, forwarded to each vignette.",
    )
    exec_group.add_argument("--partition", default="batch", help="Scheduler partition.")
    exec_group.add_argument("--account", default=None, help="Scheduler account.")
    exec_group.add_argument(
        "--walltime", default="00:20:00", help="Walltime for a VisIt compute engine."
    )
    exec_group.add_argument(
        "--timeout", type=int, default=3600, help="Per-vignette timeout in seconds."
    )
    exec_group.add_argument(
        "--offscreen",
        dest="offscreen",
        action="store_true",
        default=True,
        help="Force offscreen rendering for pvbatch.",
    )
    exec_group.add_argument(
        "--no-offscreen",
        dest="offscreen",
        action="store_false",
        help="Do not force offscreen rendering (needed by the Xvfb vignettes).",
    )
    exec_group.add_argument("--data-dir", default=None, help="Static dataset directory.")
    exec_group.add_argument("--image-width", type=int, default=None, help="Image width.")
    exec_group.add_argument(
        "--image-height", type=int, default=None, help="Image height."
    )
    exec_group.add_argument(
        "--timesteps", type=int, default=None, help="Timesteps to process."
    )
    exec_group.add_argument(
        "--verbose", action="store_true", help="Verbose vignette logging."
    )
    exec_group.add_argument(
        "--vignette-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Extra argument forwarded verbatim to each vignette. Repeatable.",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    test_directory = os.path.join(
        args.root_directory, args.test_type + "_Vignettes"
    )
    if not os.path.isdir(test_directory):
        print("Error: {0} does not exist.".format(test_directory))
        return 2

    example_dirs = [
        d for d in os.listdir(test_directory) if is_vignette_dir(d, test_directory)
    ]
    example_dirs.sort(key=extract_example_number)

    if args.clean:
        clean_tests(test_directory, example_dirs, args)
        return 0

    if args.bless:
        print(
            "\n*** --bless: recording baselines from this run. Review the "
            "output images before committing them. ***\n"
        )

    if args.write_metrics:
        if not args.run_id:
            args.run_id = new_run_id()
        print("Performance history run_id: {0}".format(args.run_id))
    else:
        args.run_id = None
        print(
            "\n*** --no-metrics: this run appends nothing to the committed "
            "performance history. ***\n"
        )

    test_failed = False
    selected = example_dirs

    if args.test_number is not None:
        selected = []
        for test_number in args.test_number:
            if test_number < len(example_dirs):
                selected.append(example_dirs[test_number])
            else:
                print(
                    "Error: Test number {0} is out of range. Available tests: "
                    "0-{1}".format(test_number, len(example_dirs) - 1)
                )
                test_failed = True

    for dir_name in selected:
        test_dir = os.path.join(test_directory, dir_name)
        run_test(test_dir, dir_name, args)
        if args.submit:
            continue
        if check_failure(os.path.join(test_dir, "Testing"), args.non_gpu_machine):
            test_failed = True

    create_summary_report(
        test_directory,
        args.test_type,
        args.machine_name,
        args.non_gpu_machine,
        check_performance=args.write_metrics,
    )

    if args.submit:
        print("\nJobs submitted. Collect results with --generate-metrics.")
        return 0

    if args.bless:
        print("\nBaselines recorded. Re-run without --bless to verify them.")

    if test_failed:
        print("\n\n**********")
        print(
            "***** Unexpected test failure detected: consider the test_suite "
            "as NOT passed. ***** "
        )
        print("**********")
        return 13

    return 0


if __name__ == "__main__":
    sys.exit(main())
