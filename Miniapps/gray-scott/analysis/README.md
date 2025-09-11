# In-Transit Analysis Reader

This project provides a flexible and extensible **in-transit reader** for simulation data using **ADIOS2** streams. It leverages a backend system to connect with powerful in-situ visualization and analysis libraries like **Ascent** and **ParaView Catalyst**.

<br>

## Key Features

- **In-Transit Processing**: Connects to a running simulation's ADIOS2 data stream (e.g., using the SST engine) for live analysis.

- **Extensible Backend System**: The reader uses a factory pattern (`backend_factory.cpp`) that can be easily extended to support various analysis libraries.

- **Multiple Visualization Backends**: Out-of-the-box support for both Ascent and ParaView Catalyst.

- **Flexible Data Handling**: Can process data in two modes:

  - `preserve`: Each analysis rank receives a subset of the original data blocks.

  - `repartition`: The entire dataset is decomposed and redistributed evenly among the analysis ranks.

- **MxN Parallelism**: Designed to run in an MxN configuration where M simulation ranks write data and N analysis ranks read and process it. The reader handles the parallel data redistribution.

<br>

## Analysis Backends

The reader supports multiple backends for analysis. The desired backend is typically specified in the settings JSON file but can be overridden with the `--output-type` flag.

### Ascent (`"output_type": "ascent"`)

The default backend, providing a rich feature set for direct visualization and analysis.

- **Data Modes**: Supports both `preserve` and `repartition` block modes.

- **Configuration**: Controlled by Ascent action files (e.g., `ascent_actions.yaml`).

### ParaView Catalyst (`"output_type": "catalyst_insitu/catalyst_io"`)

Integrates with the ParaView Catalyst library, allowing you to leverage ParaView's extensive visualization capabilities and Python scripting for analysis pipelines.

- **Data Modes**: **Only supports `repartition` block mode.** Attempting to use `preserve` mode will result in a warning, and the timestep will be skipped.

- **Configuration**: Requires a Catalyst Python script to define the analysis pipeline. The path to this script must be specified in the settings JSON file.

<br>

## Command-Line Arguments

The reader's behavior is controlled by several command-line arguments:

| Flag (Short/Long) | Description |
|---|---|
| `-f`, `--file` | **Required.** The name of the ADIOS2 file or stream (e.g., `gs.bp`). |
| `-s`, `--settings` | **Required.** Path to the simulation's JSON settings file. |
| `-o`, `--output-type` | Analysis backend to use (`ascent` or `catalyst`). Overrides the value in the settings file. |
| `-c`, `--mpi-split-color` | Color for `MPI_Comm_split` in MPMD mode. Crucial for in-transit runs. |
| `-e`, `--engine` | Override the ADIOS2 engine (e.g., `SST`, `BP4`, `BP5`). |
| `-b`, `--block-mode` | Data handling: `preserve` (default) or `repartition`. Note: Catalyst only supports `repartition`. |
| `-w`, `--sst-wait-mode` | SST wait mode: `block` (default) or `timeout`. |
| `-t`, `--sst-timeout` | Timeout in seconds when `sst-wait-mode` is `timeout`. |
| `-V`, `--adios-verbose` | Set ADIOS2 engine verbose level (`0-5`). |
| `-d`, `--debug` | Enable Conduit blueprint verification (Ascent) or extra logging (Catalyst). |
| `-h`, `--help` | Print the help message. |

<br>

## Running the Reader

### Mode 1: Standalone (Post-Hoc)

In this mode, the reader analyzes a `.bp` file that has already been written to disk. The `settings.json` file should specify the desired `output_type`.

**Example (Ascent):**
```
# Run the analysis reader on 4 cores to process a saved file with Ascent
mpirun -n 4 ./analysis-reader \
    --file gs-adios.bp \
    --settings ../configs/miniapp-settings/settings-ascent.json
```

**Example (Catalyst):**
```
# Run the analysis reader on 4 cores to process a saved file with Catalyst
# Note the required block-mode and that the settings file must point to a catalyst script.
mpirun -n 4 ./analysis-reader \
    --file gs-adios.bp \
    --settings ../configs/miniapp-settings/settings-catalyst-insitu.json \
    --block-mode repartition
```

### Mode 2: Coupled (In-Transit)

This is the **true in-transit mode**, where the simulation and analysis codes run simultaneously, streaming data without writing it to disk. This is typically done using the ADIOS2 `SST` engine.

**1. MPMD (Multiple Program, Multiple Data) Launch**

The simulation and analysis processes are launched in a single `mpirun` command and are assigned different "colors" to partition them into separate communicators.

> [!CAUTION]
> Catalyst does not work in MPMD mode due to underlying MPI conflicts, launch as two separate processes. 

**Example (16 sim ranks, 4 analysis ranks):**
```
# Make sure the simulation settings file specifies the SST engine.
mpirun -n 16 ./simulation --settings=settings-adios-span.json \
    : -n 4 ./analysis-reader --file=gs.bp \
        --settings=settings-ascent.json \
        --engine=SST \
        --mpi-split-color=1
```

**2. Separate Launches**

The simulation and analysis codes are launched as separate jobs. They discover each other via the filesystem rendezvous file created by the ADIOS2 SST engine (e.g., `gs.bp.sst`).

**Example (16 sim ranks, 4 analysis ranks):**
```
# Launch simulation in the background
mpirun -n 16 ./simulation --settings=settings-sim-sst.json &

# Launch the reader to connect to the stream
mpirun -n 4 ./analysis-reader --file=gs.bp \
        --settings=settings-sim-sst.json \
        --engine=SST
```

**ADIOS2 XML Configuration for In-Transit**

For in-transit runs, the simulation code needs an `adios2.xml` configuration file in its run directory to configure the SST engine parameters. A typical configuration for streaming looks like this:

```xml
<adios-config>
    <io name="SimulationOutput">
        <engine type="SST">
            <!-- Set verbosity to 5 for detailed ADIOS2 logs -->
            <parameter key="verbose" value="0"/>
            <!-- SST engine parameters -->
            <parameter key="RendezvousReaderCount" value="0"/>
            <parameter key="QueueLimit" value="5"/>
            <parameter key="QueueFullPolicy" value="Block"/>
            <!-- BP5/SST engine parameters -->
            <parameter key="OpenTimeoutSecs" value="60.0"/>
        </engine>
    </io>
</adios-config>
```

> [!CAUTION]
> If there is a leftover `*.sst` file in your run directory your runs may fail immediately. If your runs are failing unexpectedly, check for this file. 

<br>

## Performance Timers and Visualization

This project includes an optional feature to collect and visualize detailed performance timers.

### Enabling Timers

To enable timers, set the `ENABLE_TIMERS` CMake option to `ON`:
```
cmake -DENABLE_TIMERS=ON ..
```

When an application built with timers enabled is run, a `reader_timers/` directory will be created, containing per-rank `.csv` files with detailed timing information.

### Visualizing the Timers

A Python script is provided to parse the timer files and create a summary plot.

**Prerequisites:**
```
pip install pandas matplotlib numpy
```

**Running the Script:**
```
# General Usage
python3 visualize-performance-metrics.py -i <directory_with_csvs> -o <output_image_name.png>

# Example: Visualizing Reader Performance
python3 visualize-gray-scott-timers.py -i timers_reader/ -o reader_performance.png
```

The summary image contains four plots providing a comprehensive overview of the run's performance: Timers per Step, Timers (stacked), System Stats per Step, and Total Step Time by Rank.
