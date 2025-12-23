# ParaView_Vignettes

This guide is for the [ParaView_Vignettes Repository](https://github.com/jameskress/Visualization_Vignettes/tree/master/ParaView_Vignettes).

**What is this repo?**
This repository provides a collection of self-contained examples ("vignettes") that demonstrate how to use ParaView on high-performance computing resources. Unlike standard tutorials, these examples are designed specifically for distributed memory environments (MPI) and cover the transition from interactive GUI work to automated batch processing.

**What is ParaView?**
ParaView is an open-source, multi-platform data analysis and visualization application. It allows users to quickly build visualizations using qualitative and quantitative techniques. Developed to handle extremely large datasets, ParaView excels at using distributed memory computing resources, making it ideal for HPC systems like Shaheen III and Ibex.

---

## Table of Contents

1. [Getting Started (Run the Examples)](#1-getting-started)
2. [Performance Cheat Sheet](#2-performance-cheat-sheet)
3. [Interactive Configuration Guide (GUI)](#3-interactive-configuration-guide-gui)
4. [The Vignettes (Example Details)](#4-the-vignettes-example-details)
5. [Appendix: Batch Mode & pvbatch](#appendix-batch-mode--pvbatch)

---

## 1. Getting Started

These instructions will get you running the provided examples immediately.

### Generic HPC Setup
1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/jameskress/Visualization_Vignettes.git](https://github.com/jameskress/Visualization_Vignettes.git)
    cd Visualization_Vignettes/ParaView_Vignettes
    ```
2.  **Environment Setup:**
    ```bash
    module load paraview  # or source ../MODULES.sh
    ```
3.  **Run an Example:**
    Copy the template script from an example folder (e.g., `ex01`), edit the account/scheduler settings, and submit.

### KAUST Specific Setup

#### Shaheen III
1.  **Connect:** `ssh <user>@shaheen.hpc.kaust.edu.sa` -> `cd /scratch/<user>/`
2.  **Clone:** Follow Generic steps above.
3.  **Run:**
    ```bash
    # Edit script to add your project account (e.g., --account=k01)
    vim ex01/ex01_shaheen_runScript.sbat
    sbatch ex01/ex01_shaheen_runScript.sbat
    ```

#### Ibex Cluster
1.  **Connect:** `ssh <user>@glogin.ibex.kaust.edu.sa` -> `cd /ibex/scratch/<user>/`
2.  **Clone:** Follow Generic steps above.
3.  **Run:**
    ```bash
    sbatch ex01/ex01_ibex_runScript.sbat
    ```

---

## 2. Performance Cheat Sheet

Use this guide to determine how many nodes and tasks you need based on your data size and rendering needs.

### **Hardware & Rendering Basics**

* **Mesa (Software Rendering) - PREFERRED:**
    * **Best for:** **95% of use cases.** Standard isosurfaces, slices, clips, and general data analysis.
    * **System Config:** Shaheen `workq`/`shared` or Ibex `cpu`.
* **EGL (Hardware Rendering):**
    * **Best for:** Strictly for Volume Rendering (fog/clouds) or massive geometry (>50 million triangles).
    * **System Config:** Shaheen `ppn` (requires `video` group) or Ibex `gpu`.

### **System Specifications**

* **Shaheen III:**
    * **CPU:** 192 Cores per node (AMD Genoa). *Note: `ppn` nodes have 128 Cores.*
    * **RAM:** 384 GB per node.
    * **GPU:** NVIDIA L40 (Available only on `ppn` partition).
    * **Filesystem Critical Note:** On compute nodes, `/project` is **Read-Only**. You MUST write all output data to `/scratch`.
* **Ibex:**
    * **CPU:** Varies (Intel/AMD).
    * **RAM:** Varies significantly (384 GB up to 3 TB on large-mem nodes).
    * **GPU:** V100, A100, RTX 2080Ti, etc.

### **Shaheen III Configuration Strategy**
*Shaheen scripts use threading. "Tasks" here refers to CPU threads per MPI process.*

| Scenario | Queue | Nodes | Tasks/GPU (Threads) | Actionable Advice |
| :--- | :--- | :--- | :--- | :--- |
| **Small Data**<br>(< 16 GB) | `shared` | 1 | **16** | Fast queue times. Uses a slice of a node. |
| **Standard Vis**<br>(16 GB - 350 GB) | `workq` | 1 | **192** | **Recommended.** Data fits in one node's RAM (384GB). Set threads to 192 to use all physical cores. |
| **Large Data**<br>(> 350 GB) | `workq` | 2+ | **192** | Data exceeds single-node RAM. Increase Node count to distribute memory load. |
| **GPU Rendering** | `ppn` | 1 | **128** | **Avoid unless necessary.** Use only for heavy volume rendering. Requires `video` group. |

### **Ibex Configuration Strategy**
*Ibex scripts use MPI. "Tasks" here refers to distinct MPI processes.*

| Scenario | Queue | Nodes | Tasks/GPU (MPI Ranks) | Actionable Advice |
| :--- | :--- | :--- | :--- | :--- |
| **Standard Analysis** | `batch` | 1 | **4** | Balanced approach (4 processes, ~12 threads each). |
| **High RAM Needs**<br>(> 100 GB per process) | `batch` | 1+ | **1** | **Crucial:** By setting tasks to 1, a single ParaView process gets access to 100% of the node's RAM (e.g., 384GB). Setting tasks to 40 would split that RAM 40 ways. |
| **Hardware Rendering** | `batch` | 1 | **1** | Maps 1 ParaView process to 1 GPU. Ideal for V100/A100 nodes. |
| **Multi-GPU Node** | `batch` | 1 | **4** | Only use if the specific node has 4 GPUs (e.g., `gpu:v100`). |

---

## 3. Interactive Configuration Guide (GUI)

When using `File -> Connect` to launch a remote server, use these descriptions to understand the specific GUI options for KAUST systems.

### **Shaheen III Options**
* **Queue Name:**
    * `workq`: **Primary choice.** Exclusive access. Use this for almost all visualization tasks.
    * `shared`: Shared access. Good for small jobs.
    * `ppn`: GPU nodes. **Limited Availability.** Select this ONLY if you strictly need GPU acceleration (EGL).
* **Tasks Per Node/GPU:**
    * This controls **Threading** (OpenMP).
    * **Recommendation:**
        * If `workq`: Set to **192**.
        * If `ppn`: Set to **128**.
        * If `shared`: Set to **8** or **16**.

### **Ibex Options**
* **Node Group:**
    * `cpu`: Uses Mesa (Software) rendering. Select this for most standard analysis jobs.
    * `gpu:v100/a100`: Uses EGL (Hardware) rendering. Select this only if rendering performance is the bottleneck.
* **GPUs / Tasks Per Node:**
    * This controls **MPI Ranks**.
    * **Recommendation:** Keep this number low (1 to 4). Increasing this does *not* always speed up data analysis and often leads to "Out of Memory" errors because the RAM is split into smaller chunks.

---

## 4. The Vignettes (Example Details)

The core of this repository is the examples. Each folder (`ex##`) is a self-contained module containing a Python script and a template SLURM script.

### **ex00_pvQuery: Data Loading & Inspection**
* **Goal:** Learn how to probe data without rendering images.
* **Concepts:** Loading data, querying mesh statistics (points/cells), accessing data arrays, and printing metadata to stdout.

### **ex01_pvScreenshot: Basic Rendering**
* **Goal:** The "Hello World" of visualization.
* **Concepts:** Setting up a render view, changing background colors, simple camera positioning, and saving a `.png` file.

### **ex02_pvAnimation: Camera Movements**
* **Goal:** Create a video by moving the camera around a static object.
* **Concepts:** Orbiting, camera paths, setting resolution/framerates, and saving animation frames.

### **ex03_pvIsosurfaceAnimation: Animating Filters**
* **Goal:** Animate the data processing itself, not just the camera.
* **Concepts:** Using the `Contour` filter and automating changes to the "Isovalue" over time to show internal data structures.

### **ex04_pvStreamlineAnimation: Flow Visualization**
* **Goal:** Visualize vector fields (velocity).
* **Concepts:** Seeding streamlines (StreamTracer), generating tubes from lines, and animating the flow.

### **ex05_pvMultiTimeStepFile: Time-Series Data**
* **Goal:** Handle data that changes over time (simulations).
* **Concepts:** Loading file series (`data_01.vtk`, `data_02.vtk`...), managing timesteps, and ensuring consistent coloring across time.

### **ex06_pvLargeData: Production/Parallel Optimization**
* **Goal:** Best practices for "Hero Runs" (massive data).
* **Concepts:** Ghost cells, balancing memory usage, parallel rendering parameters, and optimizing for the specific HPC interconnect.

---

## Appendix: Batch Mode & pvbatch

ParaView includes two Python interpreters. For this repository, **we always use `pvbatch`**.

1.  **`pvpython` (Serial):**
    * Runs on a single core.
    * Behaves like the GUI client but without a window.
    * *Use case:* Testing scripts on a login node or converting file formats.

2.  **`pvbatch` (Parallel):**
    * Runs with MPI (`mpirun` or `srun`).
    * Automatically handles data distribution across nodes.
    * *Use case:* Running visualizations on the cluster.

**How to generate scripts:**
The easiest way to write code for these examples is to use the **Python Trace** feature in the ParaView GUI (`Tools -> Start Trace`), perform your actions, and then save the resulting Python code.