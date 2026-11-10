# In-Transit Analysis Reader

This project provides a flexible and extensible **in-transit reader** for simulation data using **ADIOS2** streams. It leverages a backend system to connect with powerful in-situ visualization and analysis libraries like **Ascent** and **ParaView Catalyst**.

<br>

## Key Features

- **In-Transit Processing**: Connects to a running simulation's ADIOS2 data stream (e.g., using the SST engine) for live analysis.

- **Extensible Backend System**: The reader uses a factory pattern (`backend_factory.cpp`) that can be easily extended to support various analysis libraries.

- **Multiple Visualization Backends**: Out-of-the-box support for both Ascent and ParaView Catalyst.

- **Data Handling**: The dataset is decomposed and redistributed evenly among the analysis ranks (`repartition`): each rank reads one slab along the slowest dimension, plus the next slab's first plane so the pieces meet. A `preserve` mode (each rank keeps whole writer blocks) is not implemented; the reader stops with an error if it is requested.

- **MxN Parallelism**: Designed to run in an MxN configuration where M simulation ranks write data and N analysis ranks read and process it. The reader handles the parallel data redistribution.

<br>

## Analysis Backends

The reader supports multiple backends for analysis. The desired backend is typically specified in the settings JSON file but can be overridden with the `--output-type` flag.

### Ascent (`"output_type": "ascent"`)

The default backend, providing a rich feature set for direct visualization and analysis.

- **Data Modes**: `repartition`.

- **Configuration**: Controlled by Ascent action files (e.g., `ascent_actions.yaml`).

### ParaView Catalyst (`"output_type": "catalyst_insitu/catalyst_io"`)

Integrates with the ParaView Catalyst library, allowing you to leverage ParaView's extensive visualization capabilities and Python scripting for analysis pipelines.

- **Data Modes**: `repartition`. The shared plane between neighbouring pieces is flagged `DUPLICATEPOINT` in `vtkGhostType`, so point-based analysis does not count it twice. Pin colour ranges in Catalyst scripts: each rank sees only its own slab, so a range taken from the data differs per rank and the image changes with the rank count.

- **Configuration**: Requires a Catalyst Python script to define the analysis pipeline. The path to this script must be specified in the settings JSON file.

### ADIOS2 writer (`"output_type": "adios_writer"`)

Writes every staged step back to disk with ADIOS2, so an in transit run saves data from the staging nodes and the simulation only pays for the hand-off.

- **Data Modes**: Repartition only. Each rank writes the slab it owns; the overlap plane the reader adds is not written, so the file holds the global `u` and `v` arrays once, as the simulation's own BP5 output does.
- **Output**: `<output_file_name>.bp` from the settings file, or `staged_output.bp`.
- **Configuration**: the `AnalysisOutput` IO of `adios2.xml` in the working directory, if that file exists; otherwise BP5 with ADIOS2's defaults. At scale, one aggregator per staging node (`NumAggregators`) is a good start.
- **Timers**: `ADIOS_Write_Time` as well as the read timers and `total_step`.

All backends end the ADIOS2 step as soon as the step's data is read, before rendering or writing, so the simulation can carry on with its next steps while the reader works. The reads are deferred: both fields of a step arrive together at `EndStep()`, one round of communication with the writers instead of one per field, as ADIOS2 recommends for SST. `ADIOS_EndStep` times that transfer; `ADIOS_Read_U` and `ADIOS_Read_V` now time only the scheduling of the reads.

Stepping: a step that is not ready yet (the `timeout` wait mode, when the simulation is slower than the timeout) is waited for again; only the end of the stream ends the reader, and an ADIOS2 error (`OtherError`) stops it with an error (#42).

<br>

## Command-Line Arguments

The reader's behavior is controlled by several command-line arguments:

| Flag (Short/Long) | Description |
|---|---|
| `-f`, `--file` | **Required.** The name of the ADIOS2 file or stream (e.g., `gs.bp`). |
| `-s`, `--settings` | **Required.** Path to the simulation's JSON settings file. |
| `-o`, `--output-type` | Analysis backend: `ascent`, `catalyst_insitu`, `catalyst_io` or `adios_writer`. Overrides the value in the settings file. |
| `-c`, `--mpi-split-color` | Color for `MPI_Comm_split` in MPMD mode. Crucial for in-transit runs. |
| `-e`, `--engine` | Override the ADIOS2 engine (e.g., `SST`, `BP4`, `BP5`). |
| `-b`, `--block-mode` | Data handling: `repartition` (the default and the only mode implemented). |
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
> This launch method may be necessary if your system restricts communication between mpi jobs, even mpi jobs in the same job script. If you have problems initializing ADIOS communication this may be the issue.

**Example (16 sim ranks, 4 analysis ranks):**
```
# Make sure the simulation settings file specifies the SST engine.
mpirun -n 16 ./gray-scott --settings-file=./settings-adios-memselect.json \
    : -n 4 ./analysis-reader --file=gs-adios-memselect.bp \
        --settings=settings-ascent.json \
        --engine=SST \
        --block-mode repartition \
        --mpi-split-color=1
```

**2. Separate Launches**

The simulation and analysis codes are launched as separate jobs. They discover each other via the filesystem rendezvous file created by the ADIOS2 SST engine (e.g., `gs.bp.sst`).

**Example (16 sim ranks, 4 analysis ranks):**
```
# Launch simulation in the background
mpirun -n 16 ./gray-scott --settings-file=./settings-adios-memselect.json &

# Launch the reader to connect to the stream
mpirun -n 4 ./analysis-reader --file=gs-adios-memselect.bp \
        --settings=settings-ascent.json \
        --engine=SST \
        --block-mode repartition
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

> [!WARNING]
> **SST Engine Limitations:** The ADIOS2 SST engine does **not** support "Span" mode (zero-copy buffer management).
> Ensure that `"adios_span": false` is set in your simulation's JSON settings file when running in-transit.
> Enabling it will cause the simulation to crash with an `Engine SstWriter does not support DoPut` exception.

> [!NOTE]
> `"overwrite_last_step": true` is ignored with SST (the simulation warns and writes every scheduled output step; `metadata.json` records the setting in effect under `backend.overwrite_last_step`). Overwriting closes and reopens the engine at every step, which drops the reader's connection and leaves the reader waiting forever.

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

When the reader is built with timers enabled, it writes `reader_timers/steps/rank_NNNNN.jsonl`: one JSON object per step per rank, with the reader's timers (`total_step`, `Blueprint_Time`, `Vis_Time` or `ADIOS_Write_Time`, and the ADIOS2 read timers), memory high-water mark and CPU time. This is the same logger and record format as the simulation; see the [Performance section of the miniapp README](../README.md#performance).

The reader does not yet write `metadata.json` or `summary.json`, so `scripts/perf_report.py` does not read its directories. To look at a reader run, load the JSON lines directly, for example with pandas:

```python
import glob, json, pandas as pd
rows = [json.loads(l) for f in glob.glob("reader_timers/steps/*.jsonl") for l in open(f)]
df = pd.json_normalize(rows)          # columns t.total_step, t.Vis_Time, rss_MB, ...
print(df.groupby("step")["t.total_step"].max().describe())
```
