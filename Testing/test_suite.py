import os
import subprocess
import argparse
import re
import time
import json
import glob
import shutil
import datetime
import platform
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image, ImageChops
from metrics import *
from plot_metrics import (
    generate_individual_graphs,
    generate_combination_execution_time_plot,
)


def run_local_test(test_dir):
    """
    Run the local test using the centralized run_tests.py.
    """
    run_tests_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "run_tests.py"
    )

    if os.path.exists(run_tests_path):
        subprocess.run(["python", run_tests_path, test_dir])
    else:
        print(f"run_tests.py not found at {run_tests_path}")


def submit_cluster_test(test_dir, cluster_script):
    """
    Submit the test to a cluster using batch submission.
    """
    cluster_script_path = os.path.join(test_dir, cluster_script)
    if os.path.exists(cluster_script_path):
        subprocess.run(["sbatch", cluster_script_path])
    else:
        print(f"No {cluster_script} found in {test_dir}")


def extract_example_number(dir_name):
    """
    Extracts the numerical part from the directory name (e.g., ex00 -> 00).
    Returns an integer for correct numerical sorting.
    """
    match = re.match(r"ex(\d+)", dir_name)
    if match:
        return int(match.group(1))
    return float("inf")


def log_performance(
    test_name,
    metrics,
    output_dir,
    args_machine_name,
    paraview_version=None,
    visit_version=None,
):
    """
    Log performance metrics for the executed test.
    """
    # Get machine info
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

    metrics["machine_info"] = machine_details

    # Get the current timestamp
    timestamp = datetime.datetime.now().isoformat()

    # Define system-specific Testing directory path
    testing_dir = os.path.join(output_dir, "Testing")
    os.makedirs(testing_dir, exist_ok=True)

    # Create a system-specific metrics log file
    # Get the machine name from args, if provided, otherwise from the platform
    machine_name = args_machine_name if args_machine_name else platform.uname().node
    log_file = os.path.join(testing_dir, f"performance_metrics_{machine_name}.json")

    # Log to a JSON file with date-time index
    if os.path.exists(log_file):
        with open(log_file, "r+") as file:
            data = json.load(file)
            # Append the new entry with the timestamp as the key
            data[timestamp] = metrics
            file.seek(0)  # Go to the beginning of the file
            json.dump(data, file, indent=4)
    else:
        with open(log_file, "w") as file:
            # Create a new dictionary with the timestamp as the key
            json.dump({timestamp: metrics}, file, indent=4)


def create_baseline_images(output_dir, max_images=5):
    """
    Create baseline images from the 'output' directory if they do not exist.
    """
    output_images_dir = os.path.join(output_dir, "output")
    baseline_dir = os.path.join(output_dir, "Testing", "Baseline")
    os.makedirs(baseline_dir, exist_ok=True)

    if not os.path.exists(output_images_dir):
        print(
            f"No output images found in {output_images_dir}. Skipping baseline creation."
        )
        return

    # List all images in the output directory
    image_files = sorted(
        [
            f
            for f in os.listdir(output_images_dir)
            if f.endswith((".png", ".jpg", ".jpeg"))
        ]
    )

    # Select only up to max_images
    selected_images = image_files[:max_images]

    for image in selected_images:
        src_image_path = os.path.join(output_images_dir, image)
        dest_image_path = os.path.join(baseline_dir, image)
        if not os.path.exists(dest_image_path):
            shutil.copy(src_image_path, dest_image_path)

    return selected_images


def compare_images(baseline_dir, output_dir, selected_images):
    """
    Compare images in the 'output' directory against baseline images.
    """
    output_images_dir = os.path.join(output_dir, "output")
    comparison_results = []

    if not os.path.exists(output_images_dir):
        print(f"No output images found in {output_images_dir}. Skipping comparison.")
        return comparison_results

    for image in selected_images:
        if image.endswith((".png", ".jpg", ".jpeg")):
            baseline_image_path = os.path.join(baseline_dir, image)
            output_image_path = os.path.join(output_images_dir, image)

            if os.path.exists(baseline_image_path):
                baseline_image = Image.open(baseline_image_path)
                output_image = Image.open(output_image_path)

                # Compare images
                diff = ImageChops.difference(baseline_image, output_image)

                # Count the number of differing pixels
                diff_pixels = sum(1 for x in diff.getdata() if sum(x) > 1)

                threshold_pixels = 1000
                if diff_pixels > threshold_pixels:  # Images are different
                    comparison_results.append(
                        {
                            "image": image,
                            "diff_pixels": diff_pixels,
                            "status": "DIFFERENT",
                        }
                    )
                elif diff_pixels > 0:  # different but within tolerance
                    comparison_results.append(
                        {
                            "image": image,
                            "diff_pixels": diff_pixels,
                            "status": "ACCEPTABLE",
                        }
                    )
                else:
                    comparison_results.append(
                        {
                            "image": image,
                            "diff_pixels": diff_pixels,
                            "status": "SAME",
                        }
                    )
            else:
                comparison_results.append(
                    {
                        "image": image,
                        "status": "NO BASELINE",
                    }
                )

    return comparison_results


def compare_text_files(output_log, known_good_value_path, ignore_patterns=None):
    """
    Compare the output.log text with a known good value, ignoring non-consequential differences like paths.
    """
    if ignore_patterns is None:
        ignore_patterns = [
            r"/[^ ]+/",  # Ignore file paths
            r"[a-zA-Z]:\\[^ ]+",  # Ignore Windows paths
            r"\d{2,4}[-/]\d{2}[-/]\d{2,4}",  # Ignore dates in different formats (YYYY-MM-DD, DD/MM/YYYY)
            r"\d+:\d+:\d+",  # Ignore timestamps
        ]

    def clean_content(content):
        """Remove inconsequential differences based on ignore_patterns."""
        for pattern in ignore_patterns:
            content = re.sub(pattern, "", content)
        return content.strip()

    # Read and clean output log content
    with open(output_log, "r") as log_file:
        log_content = log_file.readlines()

    log_content = [clean_content(line) for line in log_content if clean_content(line)]

    # Read and clean known good value content
    with open(known_good_value_path, "r") as known_good_file:
        known_good_content = known_good_file.readlines()

    known_good_content = [
        clean_content(line) for line in known_good_content if clean_content(line)
    ]

    # Compare cleaned log content with cleaned known good content
    for known_line in known_good_content:
        if known_line not in log_content:
            return False  # If any known good line is missing from the output log

    return True  # All lines match


def create_summary_report(test_directory, test_type, args_machine_name):
    """
    Create a summary report indicating:
    1. Tests with image/text comparison failures.
    2. Tests with significant performance changes between runs.
    Save the report in the same directory as test_suite.py.
    """
    summary_report = {
        "test_results": {},
        "any_tests_failed": False,
        "failed_image_comparisons": [],
        "failed_text_comparisons": [],
        "significant_performance_changes": [],
    }

    # Get the machine name from args, if provided, otherwise from the platform
    machine_name = args_machine_name if args_machine_name else platform.uname().node
    print(f"\nCreating test summary report for: {machine_name}")

    subdirectories = sorted(
        [
            d
            for d in os.listdir(test_directory)
            if d.startswith("ex") and os.path.isdir(os.path.join(test_directory, d))
        ]
    )

    for subdir in subdirectories:
        subdir_path = os.path.join(test_directory, subdir)
        testing_dir = os.path.join(subdir_path, "Testing")

        if not os.path.exists(testing_dir):
            continue

        test_status = {
            "test_name": subdir,
            "image_comparison_passed": True,
            "text_comparison_passed": True,
            "performance_stable": True,
        }

        # Check image comparison results
        comparison_file = os.path.join(testing_dir, "image_comparison_results.json")
        if os.path.exists(comparison_file):
            with open(comparison_file, "r") as f:
                comparison_results = json.load(f)
            for result in comparison_results:
                if result["status"] == "DIFFERENT":
                    test_status["image_comparison_passed"] = False
                    summary_report["failed_image_comparisons"].append({subdir: result})
                    summary_report["any_tests_failed"] = True

        # Check text comparison results
        text_comparison_file = os.path.join(testing_dir, "text_comparison_results.json")
        if os.path.exists(text_comparison_file):
            with open(text_comparison_file, "r") as f:
                text_comparison_results = json.load(f)
            for result in text_comparison_results:
                if result["logs_match"] == False:
                    test_status["text_comparison_passed"] = False
                    summary_report["failed_text_comparisons"].append(subdir)
                    summary_report["any_tests_failed"] = True

        # Check performance changes
        performance_file = os.path.join(
            testing_dir, f"performance_metrics_{machine_name}.json"
        )
        if os.path.exists(performance_file):
            print(f"\n\tPerformance file found: {performance_file}")
            with open(performance_file, "r") as f:
                performance_data = json.load(f)

            # Create a list of dictionaries with 'timestamp' extracted from keys
            formatted_data = [
                {"timestamp": timestamp, **metrics}
                for timestamp, metrics in performance_data.items()
            ]

            # Debugging: Print the formatted data to inspect
            # print("Formatted Performance Data:", formatted_data)
            df = pd.DataFrame(formatted_data).sort_values("timestamp")
            significant_changes = detect_significant_changes(df)

            if significant_changes:
                test_status["performance_stable"] = significant_changes
                summary_report["significant_performance_changes"].append(
                    {subdir: significant_changes}
                )
                summary_report["any_tests_failed"] = True
        else:
            print(f"\n\tPerformance file not found: {performance_file}")

        # Add the test status to the summary report
        summary_report["test_results"][subdir] = test_status

    # Save summary report in the main Testing directory (same as test_suite.py)
    report_name = test_type + "_" + machine_name + "_summary_report.json"
    summary_report_path = os.path.join(os.path.dirname(__file__), report_name)
    with open(summary_report_path, "w") as f:
        json.dump(summary_report, f, indent=4)

    print(f"\nSummary report saved at: {summary_report_path}")


# function to cleanup all temporary files in a given directory
def clean_test_files(test_directory):
    """Remove all generated files in the test directory."""
    # Define the files/directories to clean
    files_to_clean = [
        "image_comparison_results.json",
        "text_comparison_results.json",
        "output.log",
        "error.log",
        "execution_time_*.png",
        "cpu_usage_*.png",
        "memory_usage_*.png",
        "*_summary_report.json",
        "visitlog.py",
        # Add any other files or directories that should be cleaned up
    ]

    for filename in files_to_clean:
        # Use glob to find files matching the filename
        for file_path in glob.glob(os.path.join(test_directory, filename)):
            if os.path.exists(file_path):
                os.remove(file_path)  # Remove individual files
                print(f"Removed: {file_path}")


# logic to execute a single unit test
def run_test(test_dir, dir_name, args):
    print(f"\nRunning {test_dir}")

    submit = args.submit
    generate_metrics_only = args.generate_metrics

    if submit:
        print(f"Submitting {dir_name} to cluster.")
        ibex_script = f"{dir_name}_ibex_runScript.sbat"
        submit_cluster_test(test_dir, ibex_script)
    elif not generate_metrics_only:
        print(f"Running {dir_name} locally.")
        start_time = time.time()
        run_local_test(test_dir)
        end_time = time.time()

        # Gather and log performance metrics
        metrics = gather_metrics(dir_name, start_time, end_time)
        log_performance(
            dir_name,
            metrics,
            test_dir,
            args.machine_name,
            paraview_version=args.paraview_version,
            visit_version=args.visit_version,
        )

    # Create baseline images
    selected_images = create_baseline_images(test_dir)

    # Compare generated images against baseline
    baseline_dir = os.path.join(test_dir, "Testing", "Baseline")
    comparison_results = compare_images(baseline_dir, test_dir, selected_images)

    # Save image comparison results
    comparison_results_file = os.path.join(
        test_dir, "Testing", "image_comparison_results.json"
    )
    with open(comparison_results_file, "w") as f:
        json.dump(comparison_results, f, indent=4)

    # Perform text comparison of output.log
    output_log_path = os.path.join(test_dir, "Testing", "output.log")
    if os.path.exists(output_log_path):
        known_good_value_file = os.path.join(
            test_dir, "Testing", "Baseline", "known_good_value.txt"
        )  # Update this path as necessary
        if os.path.exists(known_good_value_file):
            text_comparison_result = compare_text_files(
                output_log_path, known_good_value_file
            )
            text_comparison_results_output = []
            text_comparison_results_output.append(
                {"logs_match": text_comparison_result}
            )

            # Save text comparison results
            text_comparison_results_file = os.path.join(
                test_dir, "Testing", "text_comparison_results.json"
            )
            with open(text_comparison_results_file, "w") as f:
                json.dump(text_comparison_results_output, f, indent=4)
        else:
            print(f"Known good value file not found: {known_good_value_file}")
    else:
        print(f"Cannot find output.log file @ path: {output_log_path}")

    print(f"Generating metrics and graphs for {dir_name}.")
    generate_individual_graphs(test_dir, dir_name)


# function to coordinate the different cleanup needed after testing
def clean_tests(test_directory, example_dirs, args):
    for test_dir in example_dirs:
        print(f"Cleaning {test_dir}...")
        testing_dir = test_directory + "/" + test_dir + "/Testing"
        clean_test_files(testing_dir)
        print(f"Clean-up of {testing_dir} complete.\n")

    main_testing_dir = args.root_directory + "Testing"
    clean_test_files(main_testing_dir)
    print(f"Clean-up of {main_testing_dir} complete.")
    pass


def main():
    parser = argparse.ArgumentParser(description="Run or submit tests.")
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
        help="Specify the test number to run (e.g., 0 for ex00, 1 for ex01, etc.).",
    )
    parser.add_argument(
        "--machine_name",
        type=str,
        help="Optional machine name to use in performance metrics",
    )
    parser.add_argument(
        "--paraview_version",
        type=str,
        default=None,
        help="Specify the ParaView version (e.g., 5.13.1)",
    )
    parser.add_argument(
        "--visit_version",
        type=str,
        default=None,
        help="Specify the VisIt version (e.g., 3.2.0)",
    )

    args = parser.parse_args()

    test_directory = args.root_directory + args.test_type + "_Vignettes"
    example_dirs = [
        d
        for d in os.listdir(test_directory)
        if d.startswith("ex") and os.path.isdir(os.path.join(test_directory, d))
    ]
    example_dirs.sort(key=extract_example_number)

    # remove all temporary files and exit
    if args.clean:
        clean_tests(test_directory, example_dirs, args)
        return

    # a single test was specified, just run it
    if args.test_number is not None:
        # Check if the test number is within the valid range
        if args.test_number < len(example_dirs):
            test_dir = os.path.join(test_directory, example_dirs[args.test_number])
            run_test(test_dir, example_dirs[args.test_number], args)
        else:
            print(
                f"Error: Test number {args.test_number} is out of range. Available tests: 0-{len(example_dirs)-1}"
            )
    else:  # Run all tests if no specific test number is given
        for dir_name in example_dirs:
            test_dir = os.path.join(test_directory, dir_name)
            run_test(test_dir, dir_name, args)

        # Create a summary report of all tests
        create_summary_report(test_directory, args.test_type, args.machine_name)


if __name__ == "__main__":
    main()
