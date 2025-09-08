# In-Transit Analysis Reader

This project provides a flexible and extensible **in-transit reader** for simulation data using **ADIOS2** streams. It leverages **Fides** for data model abstraction and **Ascent** for in-situ visualization and analysis.

---

## Key Features

- **In-Transit Processing**: Connects to a running simulation's ADIOS2 data stream (e.g., using the SST engine) for live analysis.
- **Extensible Backend**: `analysis_backends.h` is designed to be easily extended with other analysis libraries like ParaView Catalyst.
- **Fides Integration**: Uses Fides to interpret the incoming data stream according to a user-provided JSON schema, abstracting away the raw data layout.
- **Ascent for Visualization**: Seamlessly passes the data to Ascent for complex visualization and analysis tasks defined by Ascent action files.
- **MxN Parallelism**: Designed to run in an MxN configuration where M simulation ranks write data and N analysis ranks read and process it. Fides handles the parallel data redistribution.

## Running the In-Transit Analysis Reader

The `analysis-reader` can be run in two primary modes:

1. **Standalone** — for post-hoc analysis on saved files.
2. **Coupled** — for live, in-transit analysis of a running simulation.

This advanced workflow allows you to **visualize and analyze data without writing it to disk**.

---

## Command-Line Arguments

The reader's behavior is controlled by several command-line arguments:

| Flag (Short/Long)         | Description                                                           |
| ------------------------- | --------------------------------------------------------------------- |
| `-f`, `--file`            | **Required.** The name of the ADIOS2 file or stream (e.g., `gs.bp`).  |
| `-s`, `--settings`        | **Required.** Path to the simulation's JSON settings file.            |
| `-c`, `--mpi-split-color` | Color for `MPI_Comm_split` in MPMD mode. Crucial for in-transit runs. |
| `-e`, `--engine`          | Override the ADIOS2 engine (e.g., `SST`, `BP4`, `BP5`).               |
| `-b`, `--block-mode`      | Data handling: `preserve` (default) or `repartition`.                 |
| `-w`, `--sst-wait-mode`   | SST wait mode: `block` (default) or `timeout`.                        |
| `-t`, `--sst-timeout`     | Timeout in seconds when `sst-wait-mode` is `timeout`.                 |
| `-V`, `--adios-verbose`   | Set ADIOS2 engine verbose level (`0-5`).                              |
| `-d`, `--debug-verify`    | Enable Conduit blueprint verification for debugging.                  |
| `--timers`                | Enable performance timers and generate per-rank CSV files.            |
| `-h`, `--help`            | Print the help message.                                               |

---

## Mode 1: Standalone (Post-Hoc)

In this mode, the reader analyzes a `.bp` file that has already been written to disk.

**Example:**

```bash
# Example: Run the analysis reader on 4 cores to process a saved file
mpirun -n 4 ./analysis-reader \
    --file gs-adios.bp \
    --settings ../configs/miniapp-settings/settings-adios-memselect.json
```

## Mode 2: Coupled (In-Transit / MPMD)

This is the **true in-transit mode**, where the simulation and analysis codes run simultaneously.  
It is achieved using an **MPMD (Multiple Program, Multiple Data)** MPI launch.

The simulation and analysis processes are assigned different _colors_ to partition them into separate communicators, allowing them to run as independent groups within a single MPI job.

💡 **Key Concept**:

- The simulation runs with `color=0` (implied).
- The analysis reader is launched with `color=1` (or any other non-zero integer).
- The reader uses the `--mpi-split-color` flag to identify itself, which triggers an internal `MPI_Comm_split` call to establish its own analysis-only communicator.

### Example: 16 simulation ranks write to an SST stream, and 4 analysis ranks read from it

⚠️ Notes:

- Make sure the simulation settings file specifies the **SST engine** for ADIOS2.
- Link necessary files (e.g., `ascent_actions.yaml`, & `adios2.xml`) into the run directory.

```bash
mpirun -n 16 ../kvvm-gray-scott --settings=settings-sim-sst.json \
    : -n 4 ./analysis-reader --file=gs.bp \
        --settings=settings-sim-sst.json \
        --engine=SST \
        --mpi-split-color=1
```

This is what the `adios2.xml` should look like for `MPMD` mode:

```xml
<io name="SimulationOutput">
    <engine type="SST">
        <parameter key="verbose" value="0"/>
        <!-- SST engine parameters -->
        <parameter key="RendezvousReaderCount" value="0"/>
        <parameter key="QueueLimit" value="5"/>
        <parameter key="QueueFullPolicy" value="Block"/>
        <parameter key="DataTransport" value="MPI"/>
        <!-- BP5/SST engine parameters -->
        <parameter key="OpenTimeoutSecs" value="60.0"/>
        <!-- BP5 engine parameters -->
        <parameter key="NumAggregators" value="1"/>
        <parameter key="AsyncWrite" value="false"/>
    </engine>
</io>
```

In this configuration, the simulation generates data that is streamed via the ADIOS2 SST engine directly to the analysis-reader processes, which consume it for live visualization with Ascent. No data is written to the parallel file system by the simulation code itself.

## Mode 2: Coupled (In-Transit / evpath)

This is the **true in-transit mode**, where the simulation and analysis codes run simultaneously.  
It is achieved using separate programs and MPI launches.

The simulation and analysis processes are assigned different _colors_ to partition them into separate communicators, allowing them to run as independent groups within a single MPI job.

💡 **Key Concept**:

- The simulation and analysis codes synchronize with each other using an `ADIOS2` `*.sst` file.

### Example: 16 simulation ranks write to an SST stream, and 4 analysis ranks read from it

⚠️ Notes:

- Make sure the simulation settings file specifies the **SST engine** and **evpath** for ADIOS2.
- Link necessary files (e.g., `ascent_actions.yaml`, & `adios2.xml`) into the run directory.

```bash
mpirun -n 16 ./kvvm-gray-scott --settings=settings-sim-sst.json
mpirun -n 4 ./analysis-reader --file=gs.bp \
        --settings=settings-sim-sst.json \
        --engine=SST
```

This is what the `adios2.xml` should look like for `MPMD` mode:

```xml
<io name="SimulationOutput">
    <engine type="SST">
        <parameter key="verbose" value="0"/>
        <!-- SST engine parameters -->
        <parameter key="RendezvousReaderCount" value="0"/>
        <parameter key="QueueLimit" value="5"/>
        <parameter key="QueueFullPolicy" value="Block"/>
        <parameter key="DataTransport" value="evpath"/>
        <!-- BP5/SST engine parameters -->
        <parameter key="OpenTimeoutSecs" value="60.0"/>
        <!-- BP5 engine parameters -->
        <parameter key="NumAggregators" value="1"/>
        <parameter key="AsyncWrite" value="false"/>
    </engine>
</io>
```

In this configuration, the simulation generates data that is streamed via the ADIOS2 SST engine directly to the analysis-reader processes, which consume it for live visualization with Ascent. No data is written to the parallel file system by the simulation code itself.

## ⏱️ Performance Timers and Visualization

This project includes an optional feature to collect and visualize detailed performance timers, helping you understand and analyze the simulation's performance characteristics. The same code and script are used for both the reader and writer performance timers.

### Enabling Timers

To instrument the code and collect performance data, you must enable the timers during the CMake configuration step by setting the `ENABLE_TIMERS` option to `ON` (or `1`).

```
Example of enabling timers during CMake configuration
cmake -DENABLE_TIMERS=ON ..
```

When you run a simulation that was built with timers enabled, a new directory named `reader_timers/` will be created in the run directory. This folder will be populated with `.csv` files—one for each MPI rank—containing detailed timing information for each simulation step.

### Visualizing the Timers

A Python script is provided to easily parse all the generated timer files and create a comprehensive summary plot.

#### Prerequisites

The script depends on the **pandas**, **matplotlib**, and **numpy** libraries. You can install them using pip:

```
pip install pandas matplotlib numpy
```

#### Running the Script

```
General Usage
python3 visualize-performance-metrics.py -i <directory_with_csvs> -o <output_image_name.png>

```

**_Example: Visualizing Reader Performance_**

```
python3 visualize-gray-scott-timers.py -i timers_reader/ -o reader_performance.png
```

This will process all .csv files in the timers_reader/ directory and generate an image named reader_performance.png.

The summary image contains four plots providing a comprehensive overview of the run's performance:

1. **Timers per Step**: A line plot showing the mean time for each instrumented region, with shading to indicate the minimum and maximum times across all ranks. This is useful for seeing how performance changes over time and identifying rank-to-rank variation.

2. **Timers (stacked)**: A stacked bar chart showing the composition of the total step time, averaged across all ranks. This helps identify which operations are the most expensive.

3. **System Stats per Step**: A dual-axis plot showing memory usage (RSS) and CPU time (user/system) per step.

4. **Total Step Time by Rank**: A line plot showing the total wall-clock time for each step, with a separate line for each MPI rank. This is excellent for diagnosing load imbalance issues.
