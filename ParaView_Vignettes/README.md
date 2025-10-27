# ParaView_Vignettes

This guide is for the [ParaView_Vignettes Repository](https://github.com/jameskress/Visualization_Vignettes/tree/master/ParaView_Vignettes), which provides a collection of examples (vignettes) demonstrating how to use ParaView on high-performance computing resources. It covers running the examples and configuring ParaView for interactive use in HPC environments.

<br>

## What is ParaView?

ParaView is an open-source, multi-platform data analysis and visualization application. It allows users to quickly build visualizations to analyze their data using qualitative and quantitative techniques. Developed to handle extremely large datasets, ParaView excels at using distributed memory computing resources, making it ideal for use on HPC systems.

The examples in this repository demonstrate how to leverage ParaView for large-scale distributed visualizations, which can be run interactively through a GUI or non-interactively via batch scripts.

## Getting Started

This repository provides both generic instructions that work on any HPC system and detailed instructions for specific HPC installations:

- [Generic HPC Setup](#generic-hpc-setup): Instructions for setting up ParaView on any HPC system
- [KAUST HPC Systems](#kaust-hpc-systems): Specific instructions for KAUST's Ibex and Shaheen III clusters
- [Example Details](#example-details): Information about the included visualization examples
- [Advanced Topics](#advanced-topics): ParaView-specific configuration and usage guidance

<br>

## Table of Contents
- [Getting Started](#getting-started)
  - [Generic Setup Instructions](#generic-setup-instructions)
  - [Known HPC Systems](#known-hpc-systems)
    - [KAUST Ibex Cluster](#kaust-ibex-cluster)
    - [KAUST Shaheen III](#kaust-shaheen-iii)
- [Using ParaView in HPC Environments](#using-paraview-in-hpc-environments)
  - [Interactive Use (Client/Server Mode)](#1-interactive-use-clientserver-mode)
  - [Batch Processing Mode](#2-batch-processing-mode)
- [Repository Reference](#repository-reference)
- [Example Details](#example-details)
- [Appendix: `pvbatch` vs. `pvpython`](#appendix-pvbatch-vs-pvpython)


<br>

## Getting Started: Running the Examples

This guide will walk you through running the ParaView examples. We provide both generic instructions for any HPC system and specific instructions for known HPC installations.

### Generic Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone https://github.com/jameskress/Visualization_Vignettes.git
   cd Visualization_Vignettes/ParaView_Vignettes
   ```

2. **Environment Setup**
   ```bash
   # Load ParaView module (name may vary by system)
   module load paraview
   # Or source the provided environment script
   source ../MODULES.sh
   ```

### Known HPC Systems

#### KAUST Ibex Cluster

1. **Connect and Clone:**
   ```bash
   ssh <username>@glogin.ibex.kaust.edu.sa
   cd /ibex/scratch/<username>/
   git clone https://github.com/jameskress/Visualization_Vignettes.git
   cd Visualization_Vignettes/ParaView_Vignettes
   ```

2. **Load Modules:**
   ```bash
   module load paraview
   ```

3. **Run Example:**
   ```bash
   sbatch ex01/ex01_ibex_runScript.sbat
   ```

#### KAUST Shaheen III

1. **Connect and Clone:**
   ```bash
   ssh <username>@shaheen.hpc.kaust.edu.sa
   cd /scratch/<username>/
   git clone https://github.com/jameskress/Visualization_Vignettes.git
   cd Visualization_Vignettes/ParaView_Vignettes
   ```

2. **Configure and Run:**
   ```bash
   # Edit the run script to include your project account
   vim ex01/ex01_shaheen_runScript.sbat
   # Change --account=<##> to your account, e.g., --account=k01
   
   # Submit the job
   sbatch ex01/ex01_shaheen_runScript.sbat
   ```

### 2. Set Up ParaView Environment

Before running the examples, you'll need ParaView available in your environment:

1. **Local Installation**: 
   - Download from [ParaView's website](https://www.paraview.org/download/)
   - Add ParaView's bin directory to your PATH

2. **HPC Environment**:
   - Most HPC systems provide ParaView as a module
   - Use provided `MODULES.sh` or load manually:
     ```bash
     module load paraview    # Adjust module name as needed
     ```

### 3. Configure and Run Examples

Each example includes a template batch script that can be customized for your system:

1. **Copy the Template**:
   ```bash
   cp ex01/ex01_template_runScript.sbat ex01/my_runScript.sbat
   ```

2. **Customize the Script**:
   - Set your job scheduler (Slurm, PBS, LSF, etc.)
   - Configure resource requirements
   - Adjust module loading commands
   - Set project/account information

3. **Submit the Job**:
   ```bash
   # For Slurm
   sbatch ex01/my_runScript.sbat
   
   # For PBS
   qsub ex01/my_runScript.pbs
   
   # For LSF
   bsub < ex01/my_runScript.lsf
   ```

### 4. Check the Output

The output logs and any generated images will appear in the example's directory.
* Log files will be named like `ex01.ibex.<job_id>.out` or `ex01.shaheen_<job_id>.out`.
* You can view generated images on the command line using `display *.png`.

<br>

## Using ParaView in HPC Environments

ParaView offers two primary modes of operation, each suited for different visualization needs. The following sections provide both generic setup instructions and specific configurations for known HPC systems.

### 1. Interactive Use (Client/Server Mode)

Client/Server mode lets you interactively visualize data that lives on remote HPC resources while using a local GUI.

#### Generic Setup Instructions

1. **Install ParaView Locally:**
   - Download from [ParaView website](https://www.paraview.org/download/)
   - **Version Matching:** Your local client version MUST match the server version
   - **Prerequisites:**
     - Linux/Windows: No additional requirements
     - macOS: Install [XQuartz (X11)](https://www.xquartz.org/)

2. **Configure Server Connection:**
   - Create a server configuration (`.pvsc`) file
   - Example template (`hpc_server.pvsc`):
     ```xml
     <Servers>
       <Server name="HPC Cluster" resource="csrc://localhost">
         <CommandStartup>
           <Options>
             <Option name="PV_SERVER_PORT" label="Server Port" skip="true">11111</Option>
             <Option name="SCHEDULER" label="Job Scheduler" skip="true">SLURM</Option>
           </Options>
         </CommandStartup>
       </Server>
     </Servers>
     ```

#### Known HPC Systems

##### KAUST Ibex
1. **Download Server Configuration:**
   - Save [ibex_server.pvsc](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ibex/default_servers.pvsc)
   - Version check: `module avail paraview` on Ibex

2. **Import Configuration:**
   - Open ParaView → `File` → `Connect...`
   - Click `Load Servers`, select the `.pvsc` file
   - Select "ibex" server and connect

##### KAUST Shaheen III
1. **Download Server Configuration:**
   - Save [shaheen_server.pvsc](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ksl/default_servers.pvsc)
   - Version check: `module avail paraview` on Shaheen

2. **GPU-Enabled Visualization:**
   - **Hardware:** NVIDIA L40 GPU, 192 cores, ~768GB RAM
   - **Requirements:** 
     - `video` group membership (contact help@hpc.kaust.edu.sa)
     - Use `ppn` partition
   - **Settings:**
     - Tasks per node: 192
     - GPU nodes: 1-2 max
     - Project account required

#### **Connecting to an HPC System**

After the one-time setup, follow these steps each time you want to start an interactive session.

1.  In ParaView, go to `File -> Connect...`.
2.  Select the server you want to connect to (e.g., `shaheen` or `ibex`) and click `Connect`.
3.  An options dialog will appear. Configure your job settings.
4.  After clicking `OK`, a terminal window (`xterm` or command prompt) will pop up. Enter your HPC password and DUO authentication code when prompted.
5.  Once your job starts, you will have control of the ParaView GUI again. You can now open files located on the remote HPC system and visualize them.

#### **Using GPU-Accelerated Rendering**

For best rendering performance with large datasets, ParaView can utilize GPU acceleration when available.

##### Generic GPU Setup
1. **Requirements:**
   - HPC nodes with GPU support
   - ParaView built with GPU capabilities
   - Required modules loaded

2. **Configuration:**
   - Request GPU-enabled queue/partition
   - Configure rendering backend in job script
   - Verify GPU is detected in ParaView

##### Shaheen III GPU Configuration
For GPU-accelerated rendering on Shaheen III:

1. **Hardware Resources:**
   - L40 GPU
   - 192 CPU cores
   - ~768 GB RAM

2. **Access Requirements:** 
   - Must be in `video` Linux group
     - Contact help@hpc.kaust.edu.sa for access
   - Use `ppn` partition exclusively

3. **Job Settings:**
   - Tasks per node: 192 (recommended)
   - Maximum nodes: 1-2
   - Project account required

4. **Verification:**
   - Check `Help -> About` in ParaView
   - OpenGL Renderer should show GPU device

### 2. Batch Processing Mode

This mode is ideal for automated workflows, parameter sweeps, or generating animations without manual intervention. You write a Python script that ParaView executes on the cluster via a batch job.

* **How it Works:** You submit a job to the scheduler (Slurm) which runs `pvbatch` with your Python script (`.py`) as input.
* **Examples:** All the examples in this repository (`ex00` to `ex06`) are designed to be run in batch mode. See the "Getting Started" section above for instructions.

#### Creating a Python Script with Tracing
The easiest way to generate a Python script for batch processing is to perform the actions once in the interactive GUI and have ParaView automatically generate the code.

1.  Start an interactive session.
2.  In the GUI, go to `Tools -> Start Trace`. Keep the default settings and click `OK`.
3.  Perform all your visualization steps: open files, apply filters, change colors, set camera angles, etc.
4.  Once finished, go to `Tools -> Stop Trace`.
5.  ParaView will display the generated Python script. Save this script (`.py`) to be used with `pvbatch`.

<br>

## Repository Reference

### Repository Structure

Each example is organized as a self-contained module:

```
ex##_name/
├── ex##_name.py                  # Main ParaView Python script
├── ex##_template_runScript.sbat  # Template batch script for HPC systems
├── README.md                     # Example documentation
└── helper_scripts/               # Additional utilities
    └── createParaViewMovie.sh    # Convert image sequences to MP4
```

Key Components:
- **Python Script**: Core visualization logic using ParaView's Python API
- **Template Script**: Customizable job script for different HPC environments
- **Documentation**: Step-by-step guide and expected outputs
- **Helper Scripts**: Utilities for post-processing and analysis

### Example Details

The examples progress from basic operations to complex visualization workflows:

1. `ex00_pvQuery`: Data Loading and Analysis
   - Load and examine dataset structure
   - Query mesh statistics and variables
   - Access metadata and attributes
   - Basic data inspection techniques

2. `ex01_pvScreenshot`: Basic Visualization
   - Set up visualization pipeline
   - Configure display properties
   - Generate high-quality screenshots
   - Basic camera positioning

3. `ex02_pvAnimation`: Camera Animation
   - Create camera paths
   - Control animation timing
   - Generate image sequences
   - Configure frame rates and quality

4. `ex03_pvIsosurfaceAnimation`: Advanced Visualization
   - Create and animate isosurfaces
   - Work with multiple visualization objects
   - Control opacity and coloring
   - Animate filter parameters

5. `ex04_pvStreamlineAnimation`: Flow Visualization
   - Generate streamlines from vector fields
   - Configure integration parameters
   - Animate particle tracing
   - Optimize seed placement

6. `ex05_pvMultiTimeStepFile`: Time-Series Analysis
   - Load time-varying datasets
   - Configure temporal interpolation
   - Process multiple timesteps
   - Generate time-based animations

7. `ex06_pvLargeData`: Production Visualization
   - Handle large-scale datasets
   - Optimize memory usage
   - Configure parallel processing
   - Complex multi-filter pipelines

<br>

## Appendix: `pvbatch` vs. `pvpython`

ParaView provides two Python interpreters. The key difference is how they are designed to run:

-   **`pvpython`**: A **serial** application. It's like the standard ParaView client but with a Python interpreter instead of a GUI. It can connect to a remote `pvserver` but runs itself on a single node. Best for interactive scripting on a login node.
-   **`pvbatch`**: A **parallel** MPI application. It is its own server and is designed to be launched with `srun` or `mpirun` across multiple nodes. This is the correct tool for large-scale, parallel batch processing.

**The examples in this repository all use `pvbatch` for scalable performance.**

For more details, see the official [ParaView Documentation](https://docs.paraview.org/en/latest/index.html).