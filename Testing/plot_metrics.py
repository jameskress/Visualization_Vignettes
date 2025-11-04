import os
import matplotlib.pyplot as plt
import pandas as pd
import json
import itertools
import numpy as np


# Define a list of marker shapes to cycle through
marker_shapes = ["o", "s", "^", "D", "P", "X", "*", "v", "<", ">"]


def generate_marker_map(unique_versions):
    """
    Dynamically assign marker shapes to unique versions.
    """
    marker_cycle = itertools.cycle(marker_shapes)  # Cycle through marker shapes
    return {version: next(marker_cycle) for version in unique_versions}


def get_marker_shape(row, marker_map):
    """Get the marker shape for a given version using the marker_map."""
    visit_version = row.get("machine_info", {}).get("visit_version", None)
    paraview_version = row.get("machine_info", {}).get("paraview_version", None)

    version = visit_version if visit_version != None else paraview_version
    return marker_map.get(version, "x"), version  # Use 'x' if the version isn't found


def generate_individual_graphs(test_directory, current_sub_test):
    """
    Generate individual performance metric graphs over time for each sub-test in the test_directory,
    comparing performance across multiple machines.
    """
    testing_dir = os.path.join(test_directory, "Testing")
    print(f"\tGathering metrics and creating plots in {testing_dir}")

    # Check if the Testing directory exists for the sub-test
    if not os.path.exists(testing_dir):
        print(f"Testing directory not found for {testing_dir}")
        return  # Skip if the Testing directory doesn't exist

    # Find all performance metrics JSON files in the Testing directory
    performance_files = [
        f
        for f in os.listdir(testing_dir)
        if f.startswith("performance_metrics_") and f.endswith(".json")
    ]

    if not performance_files:
        print(f"No performance data found for {testing_dir}.")
        return  # Skip if no performance data is available

    # Dictionary to store performance data for each machine
    all_data = {}
    all_versions = set()  # To track unique versions

    # Load performance metrics from each JSON file
    for file_name in performance_files:
        machine_name = file_name.split("_")[-1].replace(
            ".json", ""
        )  # Extract machine name
        file_path = os.path.join(testing_dir, file_name)

        with open(file_path, "r") as file:
            performance_data = json.load(file)

        if performance_data:
            # Use the JSON keys (which represent the timestamp) as the DataFrame index
            df = pd.DataFrame.from_dict(
                performance_data, orient="index"
            )  # Create DataFrame from dictionary
            df.index = pd.to_datetime(
                df.index
            )  # Convert index (which is timestamp) to datetime
            df = df.sort_index()  # Ensure the DataFrame is sorted by time

            all_data[machine_name] = df  # Store the DataFrame with the machine name

        # Collect all unique versions (either VisIt or ParaView) for dynamic marker assignment
        for row in df.to_dict(orient="records"):
            visit_version = row.get("machine_info", {}).get("visit_version", None)
            paraview_version = row.get("machine_info", {}).get("paraview_version", None)
            version = visit_version if visit_version != None else paraview_version
            # print(version)
            all_versions.add(version)

    if not all_data:
        print(f"No valid performance data found in {testing_dir}.")
        return  # Skip if no valid performance data is available

    # Generate a marker map based on unique versions found
    # print(all_versions)
    marker_map = generate_marker_map(all_versions)

    # Sort machine names alphabetically for consistent ordering
    sorted_machines = sorted(all_data.keys())

    # Ensure the output directory exists before saving the plots
    os.makedirs(testing_dir, exist_ok=True)
    
    # --- NEW LOGIC: CREATE CATEGORICAL AXIS ---
    
    # 1. Collect all unique dates from ALL machines
    all_timestamps = set()
    for df in all_data.values():
        all_timestamps.update(df.index)

    # 2. Sort them to create a master list of x-axis ticks
    sorted_unique_dates = sorted(list(all_timestamps))

    # 3. Create a map from the date to its integer index (0, 1, 2, ...)
    date_to_index_map = {date: i for i, date in enumerate(sorted_unique_dates)}
    
    # 4. Create the labels for the x-axis
    # You can change the format string
    x_tick_labels = [date.strftime('%Y-%m-%d %H:%M') for date in sorted_unique_dates]
    
    # --- END NEW LOGIC ---

    # Create subplots for execution_time, memory_usage_mb, and cpu_usage_percent comparisons across machines
    metrics = {
        "execution_time": "Execution Time (s)",
        "memory_usage_mb": "Memory Usage (MB)",
        "cpu_usage_percent": "CPU Usage (%)",
    }

    # Generate a colormap with distinct colors
    colors = plt.cm.turbo(
        np.linspace(0, 1, len(sorted_machines))
    )  # Adjust colormap as needed

    for metric, ylabel in metrics.items():
        plt.figure(figsize=(22, 10))
        added_labels = set()  # Set to track added labels
        version_shapes = {}  # Dictionary to track shapes for each version

        for i, machine_name in enumerate(sorted_machines):
            df = all_data[machine_name]
            if metric in df.columns:
                
                # --- PLOTTING LOGIC CHANGED ---
                # Get the integer x-values for this machine's dates
                x_values = [date_to_index_map[date] for date in df.index]

                # Plot the line for this machine
                plt.plot(
                    x_values,
                    df[metric],
                    linestyle="-",
                    linewidth=2,
                    color=colors[i],
                    alpha=0.5,
                )
                
                # Plot the markers
                for j in range(len(df)):
                    row_data = df.iloc[j]
                    timestamp = df.index[j]
                    value = row_data[metric]
                    
                    # Get the x-axis position from our map
                    x_val = date_to_index_map[timestamp]

                    marker_shape, returned_version = get_marker_shape(
                        row_data, marker_map
                    )

                    plt.plot(
                        x_val,  # Use the integer index
                        value,
                        marker=marker_shape,
                        color=colors[i],
                        markersize=8,
                        linestyle='None'
                    )

                    version_shapes[returned_version] = marker_shape
                # --- END PLOTTING LOGIC CHANGE ---

            # only add the label once
            if machine_name not in added_labels:
                plt.plot(
                    [],
                    [],
                    linestyle="-",
                    linewidth=4,
                    color=colors[i],
                    label=machine_name,
                )  # Add to legend
                added_labels.add(machine_name)  # Mark this label as added

        plt.title(f"{ylabel} Over Time - {current_sub_test}", fontsize=18)
        
        # --- X-AXIS LABELS CHANGED ---
        plt.xlabel("Test Run Date (Not to scale)", fontsize=14)
        plt.ylabel(ylabel, fontsize=14)
        
        # Set the x-ticks to our integer indices and the labels to our date strings
        plt.xticks(
            ticks=np.arange(len(x_tick_labels)), 
            labels=x_tick_labels, 
            rotation=45, 
            ha="right", 
            fontsize=12
        )
        
        # --- END X-AXIS CHANGE ---

        # Add the main legend for machines
        main_legend = plt.legend(
            title="Machines",
            loc="upper left",
            bbox_to_anchor=(1, 1),
            frameon=False,
            fontsize=14,
        )
        main_legend.get_title().set_fontsize(14)  # Set legend title font size

        # Create the second legend for marker shapes corresponding to versions
        handles = [
            plt.Line2D(
                [0], [0], marker=marker, linestyle="None", color="black", markersize=10
            )
            for marker in version_shapes.values()
        ]
        version_labels = list(version_shapes.keys())  # Use only version names
        version_legend = plt.legend(
            handles,
            version_labels,
            title="Versions",
            loc="upper left",
            bbox_to_anchor=(1, 0.5),
            frameon=False,
            fontsize=14,
        )
        version_legend.get_title().set_fontsize(
            14
        )  # Set version legend title font size

        # Add both legends to the plot
        plt.gca().add_artist(
            main_legend
        )  # Ensure main legend is added back to the plot
        plt.gca().add_artist(version_legend)  # Add the version legend to the plot

        # Adjust layout to ensure both legends are visible
        plt.tight_layout(rect=[0, 0, 0.85, 1])  # Leave space on the right for legends

        # Save the plot with the metric name in the filename
        plt.savefig(os.path.join(testing_dir, f"{metric}_comparison.png"))
        plt.close()

    print(f"\tDone with `generate_individual_graphs`")


def generate_combination_execution_time_plot(base_directory):
    """
    Generate a combined execution time plot across all tests and machines in the base directory.
    Each test and machine will have a separate series.
    """
    # Initialize a dictionary to store data for all tests and machines
    all_data = {}

    # Discover all sub-test directories automatically
    for test_name in sorted(os.listdir(base_directory)):
        test_dir = os.path.join(base_directory, test_name)

        # Only proceed if it's a directory and contains a 'Testing' subdirectory
        if os.path.isdir(test_dir) and os.path.exists(
            os.path.join(test_dir, "Testing")
        ):
            testing_dir = os.path.join(test_dir, "Testing")

            # Find all performance metrics JSON files in the Testing directory
            performance_files = [
                f
                for f in os.listdir(testing_dir)
                if f.startswith("performance_metrics_") and f.endswith(".json")
            ]

            if not performance_files:
                print(f"No performance data found for {test_name}.")
                continue

            # Load data from each JSON file
            for file_name in performance_files:
                machine_name = file_name.split("_")[-1].replace(
                    ".json", ""
                )  # Extract machine name
                file_path = os.path.join(testing_dir, file_name)

                with open(file_path, "r") as file:
                    performance_data = json.load(file)

                if performance_data:
                    # Use the JSON keys (which represent the timestamp) as the DataFrame index
                    df = pd.DataFrame.from_dict(performance_data, orient="index")
                    df.index = pd.to_datetime(df.index)  # Convert index to datetime
                    df = df.sort_index()  # Ensure the DataFrame is sorted by time

                    # Add to the data dictionary with test and machine as the key
                    all_data[(test_name, machine_name)] = df

    if not all_data:
        print("No valid performance data found.")
        return

    # Plot all execution time data in one combined plot
    plt.figure(figsize=(22, 10))

    colors = plt.cm.turbo(
        np.linspace(0, 1, len(all_data))
    )  # Distinct colors for each series

    for i, ((test_name, machine_name), df) in enumerate(all_data.items()):
        if "execution_time" in df.columns:
            plt.plot(
                df.index,
                df["execution_time"],
                label=f"{test_name} - {machine_name}",
                linestyle="-",
                linewidth=2,
                color=colors[i],
            )

    plt.title("Execution Time Across All Tests and Machines", fontsize=18)
    plt.xlabel("Date and Time", fontsize=14)
    plt.ylabel("Execution Time (s)", fontsize=14)
    plt.xticks(rotation=45, ha="right", fontsize=12)

    # Add legend outside the plot
    plt.legend(loc="upper left", bbox_to_anchor=(1, 1), frameon=False, fontsize=12)

    # Adjust layout to fit the legend
    plt.tight_layout(rect=[0, 0, 0.85, 1])

    # Save the combined plot
    output_file = os.path.join(base_directory, "combined_execution_time_plot.png")
    plt.savefig(output_file)
    plt.close()

    print(f"Combined execution time plot saved as {output_file}")
