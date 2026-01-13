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

### Connection Setup

1.  **Install ParaView Locally:**
    * Download from [ParaView.org](https://www.paraview.org/download/).
    * **Crucial:** Your local version MUST match the HPC version (check `module avail paraview` on the cluster).
2.  **Get Server Configs (`.pvsc`):**
    * **Ibex:** Download [ibex_server.pvsc](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ibex/default_servers.pvsc)
    * **Shaheen:** Download [shaheen_server.pvsc](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ksl/default_servers.pvsc)
3.  **Load Configs:**
    * Open ParaView → `File` → `Connect...` → `Load Servers` → Select the `.pvsc` file.

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
├── ex##_name.py                  # Main ParaView Python script
├── ex##_template_runScript.sbat  # Template batch script
├── README.md                     # Specific documentation
└── helper_scripts/               # Utilities
```

### Example Details
1.  **ex00_pvQuery**: Loading data and querying mesh statistics/metadata.
2.  **ex01_pvScreenshot**: Basic rendering pipeline and saving images.
3.  **ex02_pvAnimation**: Camera path animation.
4.  **ex03_pvIsosurfaceAnimation**: Animating filter parameters (Isovalues).
5.  **ex04_pvStreamlineAnimation**: Flow visualization and particle tracing.
6.  **ex05_pvMultiTimeStepFile**: Handling time-series datasets.
7.  **ex06_pvLargeData**: Optimization for massive datasets (ghost cells, parallel rendering).

### `pvbatch` vs. `pvpython`
* **`pvpython`**: Serial. Runs on one core. Use for testing on login nodes.
* **`pvbatch`**: Parallel. Runs with MPI. **Always use this for these examples.**
