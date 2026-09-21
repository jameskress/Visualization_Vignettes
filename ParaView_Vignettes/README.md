# ParaView_Vignettes

This repository serves two primary purposes for High Performance Computing (HPC) visualization:
1.  **The Vignettes:** A collection of self-contained examples demonstrating how to run ParaView scripts in batch mode on HPC resources.
2.  **Interactive Guide:** Documentation on configuring local ParaView clients to connect to remote KAUST HPC clusters (Ibex and Shaheen III).

<br>

## Table of Contents

* [**Part 1: Running the Vignettes**](#part-1-running-the-vignettes) (Batch Processing)
    * [Generic / Local Setup](#generic--local-setup)
    * [KAUST Ibex Setup](#kaust-ibex-setup)
    * [KAUST Shaheen III Setup](#kaust-shaheen-iii-setup)
* [**Part 2: Interactive ParaView**](#part-2-interactive-paraview) (Client-Server Mode)
    * [Client Installation & Prerequisites](#client-installation--prerequisites)
    * [Connection Setup](#connection-setup)
    * [KAUST Connection Guide (GUI Options)](#kaust-connection-guide-gui-options)
* [**Part 3: HPC Resource Strategy**](#part-3-hpc-resource-strategy) (Performance Cheat Sheet)
* [**Appendix**](#appendix) (Example Details & Reference)

<br>

---

# Part 1: Running the Vignettes

Use this section if you want to run the provided example scripts (`ex01`, `ex02`, etc.) on a cluster. These examples are designed to run in **Batch Mode** (non-interactively).

### Generic / Local Setup
*Use this for your local machine or non-KAUST clusters.*

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/jameskress/Visualization_Vignettes.git](https://github.com/jameskress/Visualization_Vignettes.git)
    cd Visualization_Vignettes/ParaView_Vignettes
    ```
2.  **Environment Setup:**
    ```bash
    # Load ParaView module (system dependent)
    module load paraview
    # Or source the provided environment script
    source ../MODULES.sh
    ```
3.  **Run an Example:**
    Copy the template script inside an example folder (e.g., `ex01/ex01_template_runScript.sbat`), customize it for your scheduler, and submit it.

### KAUST Ibex Setup

1.  **Connect:** `ssh <user>@glogin.ibex.kaust.edu.sa`
2.  **Clone:**
    ```bash
    cd /ibex/scratch/<username>/
    git clone [https://github.com/jameskress/Visualization_Vignettes.git](https://github.com/jameskress/Visualization_Vignettes.git)
    cd Visualization_Vignettes/ParaView_Vignettes
    ```
3.  **Run:**
    ```bash
    module load paraview
    sbatch ex01/ex01_ibex_runScript.sbat
    ```

### KAUST Shaheen III Setup

1.  **Connect:** `ssh <user>@shaheen.hpc.kaust.edu.sa`
2.  **Clone:**
    ```bash
    cd /scratch/<username>/
    git clone [https://github.com/jameskress/Visualization_Vignettes.git](https://github.com/jameskress/Visualization_Vignettes.git)
    cd Visualization_Vignettes/ParaView_Vignettes
    ```
3.  **Configure & Run:**
    ```bash
    # You MUST edit the script to add your Project Account (e.g., k01)
    vim ex01/ex01_shaheen_runScript.sbat
    # Change: #SBATCH --account=k##

    sbatch ex01/ex01_shaheen_runScript.sbat
    ```

> **IMPORTANT: GPU Access & The "Video" Group**
> If you intend to use the `ppn` partition (GPU nodes) on Shaheen III for hardware-accelerated rendering, you must be a member of the **`video`** Unix group.
> * **How to check:** Run the command `groups` in your terminal. If you see `video`, you have access.
> * **How to apply:** Send an email to **help@hpc.kaust.edu.sa** requesting addition to the `video` group for visualization purposes.

<br>

---

# Part 2: Interactive ParaView

Use this section if you want to use the ParaView GUI on your laptop to visualize data stored on the supercomputer (Client-Server mode).

### Client Installation & Prerequisites

Before connecting, you must prepare your local machine (laptop/desktop).

1.  **Install ParaView:**
    * Download the client from [ParaView.org](https://www.paraview.org/download/).
    * **Crucial:** Your local client version **MUST** match the version on the HPC system (check `module avail paraview` on the cluster).

2.  **OS-Specific Requirements:**
    * **macOS Users:** You **MUST** install [XQuartz (X11)](https://www.xquartz.org/). ParaView requires X11 to display the authentication window and handle the connection tunnel.
    * **Windows Users:** You need a terminal client to handle authentication.
        * **CRITICAL PITFALL:** The standard Windows Command Prompt or PowerShell often **fails** to correctly handle the **reverse connection tunnel** required by ParaView (due to issues with the native OpenSSH implementation).
        * **SOLUTION:** You **MUST** install and use [PuTTY](https://www.putty.org/) to ensure the connection works reliably.
    * **Linux:** No additional software is typically required.

### Connection Setup

1.  **Get Server Configs (`.pvsc`):**
    * **Ibex:** Download [ibex_server.pvsc](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ibex/default_servers.pvsc)
    * **Shaheen:** Download [shaheen_server.pvsc](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ksl/default_servers.pvsc)
2.  **Load Configs:**
    * Open ParaView → `File` → `Connect...`
    * Click `Load Servers` → Select the downloaded `.pvsc` file.
3.  **Connect:**
    * Select the server (e.g., `shaheen`) from the list and click `Connect`.

### KAUST Connection Guide (GUI Options)

When you click **Connect**, a dialog will appear asking for job settings. Use this guide to choose the right options.

#### **For Shaheen III**

| Option | Setting | Description |
| :--- | :--- | :--- |
| **Queue Name** | `workq` | **Recommended.** Standard exclusive access node. Uses CPU rendering (Mesa). |
| | `shared` | Good for small jobs or quick checks. |
| | `ppn` | **GPU Node.** Use only for heavy volume rendering. **Requires `video` group (see Part 1).** |
| **Tasks Per Node** | `192` | For `workq`. Uses all CPU cores for processing. |
| | `128` | For `ppn` (GPU nodes have fewer CPU cores). |
| | `16` | For `shared`. |

#### **For Ibex**

| Option | Setting | Description |
| :--- | :--- | :--- |
| **Node Group** | `cpu` | **Recommended.** Uses software rendering (Mesa). Good for 95% of tasks. |
| | `gpu` | Uses hardware rendering. Only for massive geometry or volume rendering. |
| **Tasks/Rank** | `1` to `4` | **Keep this low.** Setting this high splits the RAM too many times and causes crashes. |

<br>

---

# Part 3: HPC Resource Strategy

Use this cheat sheet to determine the resources you need for your job (Interactive or Batch).

### 1. Rendering Backend: Mesa vs. EGL
* **Mesa (Software Rendering):**
    * **Use for:** Isosurfaces, Slices, Clips, and general analysis.
    * **Why:** It is faster and more stable for geometry-heavy workflows on modern CPUs.
    * **Target:** Shaheen `workq` or Ibex `cpu`.
* **EGL (Hardware/GPU Rendering):**
    * **Use for:** Volume Rendering (Fog/Clouds/Fire) or massive triangle counts (>50M).
    * **Target:** Shaheen `ppn` or Ibex `gpu`.
    * **Note:** Shaheen `ppn` requires `video` group membership.

#### How the backend is actually selected

Loading the right module is only half of it. ParaView 6.0 stopped inferring a
render window from the build alone, and the site's own interactive launcher
-- `run_pvserver.sbat`, the script `pv_launcher.sh` submits for a
reverse-connected GUI session -- picks one explicitly from the module name:

```bash
if [[ "$MODNAME" == *"mesa"* ]]; then
    export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
elif [[ "$MODNAME" == *"egl"* ]]; then
    export VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow
fi
```

`ParaView_Vignettes/MODULES.sh` now makes the same decision from the same
evidence, so a batch vignette and an interactive session rendering through
the same libraries also render through the same backend. It exports two
things:

| Variable | Meaning |
| :--- | :--- |
| `VV_PARAVIEW_MODULE` | The module that was loaded, e.g. `paraview/5.13.1-gnu-egl`. |
| `VTK_DEFAULT_OPENGL_WINDOW` | The render window class ParaView should instantiate. |

An existing `VTK_DEFAULT_OPENGL_WINDOW` in the environment is left alone --
someone who exported it by hand is saying something the script cannot infer.
`Testing/run_tests.py` makes the same decision when it launches `pvbatch`
outside a batch script, reading `$VV_PARAVIEW_MODULE` and falling back to
`$LOADEDMODULES`.

Without the hint an `-egl` module can fall back to `llvmpipe` and still
produce correct-looking images at roughly a hundredth of the speed, with
nothing in the output to say so. `ex08_pvBackendCheck` exists to catch
exactly that, and its `.sbat` scripts derive `--expect-backend` from
`VV_MODULE_VARIANT` so flipping the variant cannot leave a contradictory
expectation behind. ex08 also fails when the environment and the expectation
ask for opposite things -- a Mesa module with `--expect-backend egl` is a
configuration bug that no amount of rendering will reveal, because both
halves succeed on their own terms.

### 2. Shaheen Configuration Strategy
*Metric: Tasks = CPU Threads*

| Data Size | Queue | Nodes | Tasks Setting |
| :--- | :--- | :--- | :--- |
| **< 16 GB** | `shared` | 1 | 16 |
| **16 GB - 350 GB** | `workq` | 1 | 192 |
| **> 350 GB** | `workq` | 2+ | 192 |

### 3. Ibex Configuration Strategy
*Metric: Tasks = MPI Ranks*

| Goal | Queue | Tasks Setting | Note |
| :--- | :--- | :--- | :--- |
| **Standard Vis** | `batch` | 4 | Balanced CPU/RAM usage. |
| **High RAM** | `batch` | 1 | Gives 100% of node RAM to a single process. |

<br>

---

# Appendix

### Repository Structure
```
ex##_name/
├── ex##_name.py                  # The vignette
├── ex##_ibex_runScript.sbat      # Ibex submission script
├── ex##_shaheen_runScript.sbat   # Shaheen III submission script
├── ex##_make_state.py            # Fixture generator, where one is needed
├── output/                       # Rendered images, extracts, timing CSVs
└── Testing/
    ├── Baseline/                 # Blessed images + known_good_value.txt
    ├── ex##_name_results.json    # Structured results from the last run
    └── performance_metrics_*.json
```

### Three ParaView behaviours that will otherwise cost you an afternoon

**1. `pvbatch` segfaults on `sys.exit()`.** Whenever a render window has been
created and no usable X display exists, which is every offscreen batch run and
every Slurm compute node, ParaView 6.1 crashes during Python finalization:
the script has already finished and written its results, and the process still
exits 1 with "Segmentation fault". Every rendering vignette here ends with
`vc.exit_vignette()`, which flushes and calls `os._exit()` rather than
unwinding the interpreter. The same script exits 0 under `xvfb-run`, which is
how the cause was pinned down.

**2. `Show()` auto-rescales a lookup table** to the representation's own data
range the first time it colours by an array. Setting a preset and rescaling
*before* the `Show`/`ColorBy` therefore has the rescale silently undone, and
the frame is drawn with a lookup table nobody configured. This cost a 26.5%
whole-frame difference twice, in two unrelated changes. Fetch the transfer
function and rescale it **after** every `Show` and `ColorBy`.

**3. Preset names moved, and the three versions in use fail differently.**
`Viridis (matplotlib)` became `Viridis` in 6.1, not 6.0. Given a name it does
not have, 6.1 raises, 5.13 returns `False`, and **6.0.1 does neither**: it
returns something truthy and leaves the transfer function alone. Use
`vc.apply_color_preset()`, which verifies that the transfer function actually
changed rather than trusting the return value.

### Before the first run on a machine

```bash
export PARAVIEW_PATH=/path/to/paraview/bin      # or module load
python3 ../Testing/prepare_machine.py --check   # non-zero if not ready
python3 ../Testing/prepare_machine.py           # build what is missing
```

`data/topologies/` and `ex11_state.pvsm` are generated per machine and locked
to a ParaView major.minor. A mismatch does not announce itself: an AMR
hierarchy written by 6.1.0 opens under 6.0.1 and quietly reads 216 points
where 842 were written. `test_suite.py` refuses to start on a stale fixture
for that reason. For a machine with no network, see
`Testing/OFFLINE_SETUP.md`.

### The shared command-line interface

Every vignette accepts the same flags, so the harness can drive any of them
the same way and you can run any of them by hand the same way. Run any
vignette with `--help` for the full list.

| Flag | Purpose |
| :--- | :--- |
| `--machine {local,ibex,shaheen}` | Execution site. `local` never contacts a scheduler. |
| `--ranks N` / `--nodes N` | How wide to run. |
| `--partition` / `--account` / `--walltime` | Scheduler settings. |
| `--image-width` / `--image-height` | Output resolution. |
| `--data-dir` | Where the static datasets live (also `$VV_DATA_DIR`). |
| `--timesteps N` | Cap how many timesteps to process. |
| `--verbose` | Per-step progress logging. |

Each vignette writes `Testing/<name>_results.json` carrying its metrics,
per-phase timings and assertions, and exits non-zero when an assertion
fails. The submission scripts keep every tunable in one `RUN CONFIGURATION`
block at the top.

> **ex07 onwards need one preparation step.** `ex09` reads the topology
> datasets generated by `data/make_topology_datasets.py`, and `ex11` needs a
> state file generated by its own `ex11_make_state.py`. Both are one-time
> steps; see those vignettes' headers.

### Example Details

**Classic vignettes** -- how to do a thing.

1.  **ex00_pvQuery**: Loading data and querying mesh statistics/metadata.
2.  **ex01_pvScreenshot**: Basic rendering pipeline and saving images.
3.  **ex02_pvAnimation**: Camera path animation.
4.  **ex03_pvIsosurfaceAnimation**: Animating filter parameters (Isovalues).
5.  **ex04_pvStreamlineAnimation**: Flow visualization and particle tracing.
6.  **ex05_pvMultiTimeStepFile**: Handling time-series datasets.
7.  **ex06_pvLargeData**: Optimization for massive datasets (ghost cells, parallel rendering).

**Verification vignettes** -- how to know a thing still works. These assert
on what they produce and fail the suite when it changes.

8.  **ex07_pvScaling**: Isosurface extraction across rank counts, with I/O,
    filter and render time measured separately into a scaling CSV. Asserts
    that geometry is rank-invariant.
9.  **ex08_pvBackendCheck**: Reads the live `GL_VENDOR`/`GL_RENDERER` through
    `GetOpenGLInformation()` and fails when a job that asked for a GPU is
    quietly running on `llvmpipe`. Also fails on a resolution mismatch, the
    other half of the same symptom.
10. **ex09_pvMeshTopologies**: One contour pipeline over four topologies --
    unstructured tetrahedra, overlapping AMR, polydata, and a *deliberately
    ragged* multiblock whose blocks are unequal in every axis.
11. **ex10_pvColormapFidelity**: One field through four transfer functions --
    built-in preset, custom XML map, log-scaled, and categorical -- each with
    an explicitly formatted colour legend.
12. **ex11_pvStateVerification**: Loads a saved `.pvsm` headlessly under
    Xvfb, steps the animation, renders, and disconnects cleanly. Catches a
    state file that no longer loads after a ParaView upgrade.
13. **ex12_pvExtractRegression**: `CreateExtractor`/`SaveExtracts` emitting
    data, image and *numerical* extracts side by side, so the regression
    assertion is a number with a tolerance rather than a pixel diff. The CSV
    is declared with `ctx.add_numeric_extract()`, which routes it into
    `verify.compare_csv`.

Every one of these has a VisIt counterpart of the same number in
`VisIt_Vignettes/`. The suites are 1:1 across `ex00` through `ex12`, which
is also what makes `--test_number N` select `exNN` in either suite.

### Batch scripts and the site launchers

The `.sbat` scripts in each vignette directory run the vignette itself,
inside the allocation `sbatch` gives them. They are not a replacement for the
site's interactive launcher and do not overlap with it:

| Path | What it starts | Where the script runs |
| :--- | :--- | :--- |
| `pv_launcher.sh` → `run_pvserver.sbat` | `pvserver`, reverse-connecting to a desktop ParaView client | On the compute nodes; you drive it from the GUI |
| `ex##_<site>_runScript.sbat` | `pvbatch` running one vignette to completion | On the compute nodes, headless |

Two launch details are copied from `run_pvserver.sbat` because they are the
site's proven settings, not preferences:

* **`--map-by ppr:<ranks-per-node>:node`** on the Open MPI path. Without it
  Open MPI packs every rank onto the first node of a multi-node allocation,
  and a scaling study measures one node however many it asked for.
* **`--disable-xdisplay-test`** alongside `--force-offscreen-rendering`. On a
  compute node with no X server the display probe costs a timeout before
  ParaView gives up and renders offscreen anyway.

`ex11` is the one exception to the offscreen flags: it verifies the
on-display path a GUI user takes, so it runs under `xvfb-run` and forces
nothing.

### `pvbatch` vs. `pvpython`
* **`pvpython`**: Serial. Runs on one core. Use for testing on login nodes.
* **`pvbatch`**: Parallel. Runs with MPI. **Always use this for these examples.**
