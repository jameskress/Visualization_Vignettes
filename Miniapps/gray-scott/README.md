# KAUST Visualization Vignettes Miniapp - gray-scott

This is a 3D 7-point stencil code to simulate the following [Gray-Scott
reaction diffusion model](https://doi.org/10.1126/science.261.5118.189):

```
u_t = Du * (u_xx + u_yy + u_zz) - u * v^2 + F * (1 - u)  + noise * randn(-1,1)
v_t = Dv * (v_xx + v_yy + v_zz) + u * v^2 - (F + k) * v
```

A reaction-diffusion system is a system in which a dynamical system is attached to a diffusion equation, and it creates various patterns. This is an equation that simulates the chemical reaction between the chemicals $U$ and $V$. $U$ is called the activator and $V$ is called the repressor.

<br>

## Running with Docker

This project provides a self-contained, portable, and reproducible scientific software environment using Docker. It includes pre-compiled versions of **ParaView 5.13.2**, **ADIOS2**, **Ascent**, and the **Gray-Scott Miniapp**, ensuring that users can run complex in-situ visualization workflows without needing to build the dependencies themselves.

The Docker image can be built and run on **Linux, macOS, and Windows**.

### 1. Prerequisites

The only prerequisite is to have Docker installed on your system.

* **Windows / macOS:** Install [**Docker Desktop**](https://www.docker.com/products/docker-desktop/).
* **Linux:** Install [**Docker Engine**](https://docs.docker.com/engine/install/). It is also recommended to complete the [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/) to run Docker without `sudo`.

## 2. Quick Start: Running the Pre-Built Image (Recommended)

This is the fastest and easiest way to get started. This workflow downloads the ready-to-use image, saving you hours of compilation time.

### Step 2.1: Download the Pre-Built Image

Open a terminal or command prompt and run the following command to download the complete environment from the project's public GitLab Container Registry.

```bash
docker pull gitlab.kitware.com:4567/jameskress/kaust_visualization_vignettes/kaust-viz-app:latest
```

### Step 2.2: Run Simulations and Access Files

To run the container, you will create a "shared folder" that links a directory on your computer to a directory inside the container. This makes it easy to access your output files and resolves file permission issues.

1.  **Create a Local Data Directory:** On your computer, create a folder where you want your simulation outputs to be saved.
    ```bash
    mkdir data
    ```

2.  **Run the Container:** Use the command for your operating system to start the container. This command links your new `data` folder to `/app/data` inside the container and ensures you have the correct file permissions.

    **On Linux or macOS (in any terminal):**
    ```bash
    docker run -it --rm \
      -e HOST_UID=$(id -u) \
      -e HOST_GID=$(id -g) \
      -v "$(pwd)/data:/app/data" \
      gitlab.kitware.com:4567/jameskress/kaust_visualization_vignettes/kaust-viz-app:latest
    ```
    **On Windows (in a PowerShell terminal):**
    ```powershell
    # Note: On Windows, the UID/GID mapping is handled automatically by Docker Desktop.
    docker run -it --rm -v "${PWD}/data:/app/data" gitlab.kitware.com:4567/jameskress/kaust_visualization_vignettes/kaust-viz-app:latest
    ```
    **On Windows (in a Command Prompt `cmd.exe`):**
    ```cmd
    :: Note: On Windows, the UID/GID mapping is handled automatically by Docker Desktop.
    docker run -it --rm -v "%cd%/data:/app/data" gitlab.kitware.com:4567/jameskress/kaust_visualization_vignettes/kaust-viz-app:latest
    ```
    You are now inside the container with a clean command prompt: `vizuser@<container_id>:/app/data$`.

3.  **Set Up Your Run Directory:** The container includes a script to easily copy the application and its default settings into your shared folder. Run this script once.
    ```bash
    # Inside the container, set up your run directory
    setup_rundir.sh
    ```
    You will now see the `kvvm-gray-scott` executable and all the `settings-*.json` files in your shared directory.

4.  **Run a Simulation:** Now you can run the simulation using the local executable and settings files.
    ```bash
    # Navigate to the shared data directory
    cd /app/data

    # Run the simulation using the local executable and settings files
    mpirun -np 2 ./kvvm-gray-scott --settings-file=./settings-catalyst-insitu.json
    ```

5.  **Exit and Access Your Files:** When the simulation is done, exit the container.
    ```bash
    exit
    ```
    Your output files (images, VTK files, etc.) are now in the `data` folder on your computer.

### 3. For Developers: Building the Image from Source

Follow these instructions if you need to modify the environment or build the image yourself.

> **Warning:** This build process compiles several large scientific libraries. It can take a **very long time** (potentially several hours) and will consume a significant amount of disk space.

#### Step 3.1: Clone and Build the Image

1.  **Clone this Repository:**
    ```bash
    git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git
    cd KAUST_Visualization_Vignettes
    ```

2.  **Build the Image:** From the root directory of the repository, run the following command. This will create a local Docker image named `kaust-viz-app`.
    ```bash
    docker build -t kaust-viz-app .
    ```

#### Step 3.2: Run Simulations and Access Files

This workflow is identical to the user workflow, but you will use your locally-built image name (`kaust-viz-app`) instead of the full registry path.

1.  **Create a Local Data Directory:**
    ```bash
    mkdir data
    ```

2.  **Run the Container:**
    **On Linux or macOS (in any terminal):**
    ```bash
    docker run -it --rm \
      -e HOST_UID=$(id -u) \
      -e HOST_GID=$(id -g) \
      -v "$(pwd)/data:/app/data" \
      kaust-viz-app
    ```
    **On Windows (in PowerShell or Command Prompt):**
    ```bash
    # PowerShell
    docker run -it --rm -v "${PWD}/data:/app/data" kaust-viz-app

    # Command Prompt
    docker run -it --rm -v "%cd%/data:/app/data" kaust-viz-app
    ```

3.  **Set Up and Run a Simulation:**
    ```bash
    # Inside the container, set up your run directory
    setup_rundir.sh

    # Run the simulation
    mpirun -np 2 ./kvvm-gray-scott --settings-file=./settings-catalyst-insitu.json
    ```

4.  **Exit and Access Your Files:**
    ```bash
    exit
    ```

<br>

## How to build locally

Make sure `MPI`, and `VTK` are installed. These are non-optional dependencies. You can also enable `Catalyst`, `Ascent`, or `Kombyne` for more visualization options.

`ADIOS2` is required for checkpointing and for restarting a sim from a given checkpoint. If `ADIOS2` is not enabled then the checkpoint and restart options will be ignored in the settings.

### Catalyst

The easiest way to get `Catalyst` and `VTK` is to use the `ParaView Superbuild`. This will also enable easy live viewing from `Catalyst` in `ParaView`.

```
Catalyst needs to be built with the SAME MPI compiler as gray-scott

git clone --recursive https://gitlab.kitware.com/paraview/paraview-superbuild.git
cd paraview-superbuild
git checkout v6.0.0
cd ..
mkdir paraview-build
cd paraview-build
ccmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DUSE_SYSTEM_mpi=ON -DUSE_SYSTEM_python3=ON -DENABLE_catalyst=ON -DENABLE_mpi=ON -DENABLE_netcdf=ON -DENABLE_hdf5=ON -DENABLE_python3=ON -DENABLE_openmp=ON  ../paraview-superbuild
make -j
```

### Ascent

To build `Ascent`, follow one of the methods listed in the [documentation](https://ascent.readthedocs.io/en/latest/#). Below is the method that we have tested.

```
git clone --recursive https://github.com/alpine-dav/ascent.git
cd ascent
env prefix=build env enable_mpi=ON enable_openmp=ON  ./scripts/build_ascent/build_ascent.sh
export Ascent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent
```

### ADIOS2

To build `ADIOS2`, follow one of the methods listed in the [documentation](https://adios2.readthedocs.io/en/latest/). Below is the method that we have tested.

```
git clone https://github.com/ornladios/ADIOS2.git
mkdir adios2-build
cd adios2-build
cmake ../ADIOS2/ -DADIOS2_USE_MPI=ON -DADIOS2_BUILD_EXAMPLES=ON -DCMAKE_INSTALL_PREFIX=../adios2-install
make -j
```

### Kombyne

`Kombyne` is a closed source, paid, commercial in situ software. They do have a `lite` version, which we make use of in this repo, that is free. We cannot distribute the source, as such you have to get your free download from there [here](https://www.ilight.com/kombyne-lite-downloads-4/).

```
Download Kombyne-Lite from the Inteligent Light website.

cd /path/to/install
tar zxvf kombyne-lite-1.0.0-ubuntu18-gcc7.5-openmpi.tar.gz

Then, in your cmake configuration file, just set the location, for example:
kombynelite_DIR=/home/kressjm/packages/kombynelite-v1.5-linux-x86_64/lib/cmake/kombynelite
```

### Building Gray-Scott

> 💡 **Note:** `Ascent` and `Kombyne` cannot be enabled at the same time due to library conflicts.

```
cd <path_to_gray-scott>
mkdir build
cd build
cmake \
-Dcatalyst_DIR=/home/kressjm/packages/paraview-src/build_5.13.3/install/lib/cmake/catalyst-2.0 \
-DVTK_DIR=/home/kressjm/packages/paraview-src/build_5.13.3/install/lib/cmake/paraview-5.13/vtk \
-DAscent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent \
-DADIOS2_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/adios2-build \
-Dkombynelite_DIR=/home/kressjm/packages/kombynelite-v1.5-linux-x86_64/lib/cmake/kombynelite \
-DENABLE_TIMERS=1 \
-DCMAKE_BUILD_TYPE=DEBUG \
-DENABLE_ASCENT=ON \
-DENABLE_CATALYST=ON \
-DENABLE_ADIOS2=ON \
-DENABLE_KOMBYNELITE=OFF \
-DCMAKE_INSTALL_PREFIX=../install \
../

make
make install
```

Running `make install` will move all the interesting settings and implementation specific scripts into the `install` directory for easy use.

### Building In Transit Analysis Code (Optional)

In order to enable in-transit visualization, we have created a reader code that connects to the simulation's ADIOS2 data stream. It leverages Ascent for visualization and allows for powerful `MxN` analysis where `M` simulation ranks are analyzed by `N` analysis ranks.

This is an optional extension to Gray-Scott, if you want to test in transit visualization and experience the data staging capabilities of `ADIOS` you will need to build this extension.

#### Step 1: Dependencies

The reader requires the following libraries to be installed. Follow the instructions in this `README` to get them ready:

- MPI
- ADIOS2
- Ascent (& Conduit, which is part of the Ascent build)

#### Step 2: Configure and Build

If you have `ADIOS2` and `Ascent` built all you have to do is enable one more flag in the main cmake invocation to enable the analysis reader.

```
-DBUILD_ANALYSIS_READER=ON
```

For example:

```
cd <path_to_gray-scott>
mkdir build
cd build
cmake \
-Dcatalyst_DIR=/home/kressjm/packages/paraview-src/build_5.13.3/install/lib/cmake/catalyst-2.0 \
-DVTK_DIR=/home/kressjm/packages/paraview-src/build_5.13.3/install/lib/cmake/paraview-5.13/vtk \
-DAscent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent \
-DADIOS2_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/adios2-build \
-DENABLE_TIMERS=1 \
-DCMAKE_BUILD_TYPE=DEBUG \
-DENABLE_ASCENT=ON \
-DENABLE_CATALYST=ON \
-DENABLE_ADIOS2=ON \
-DENABLE_KOMBYNELITE=OFF \
-DBUILD_ANALYSIS_READER=ON \
-DCMAKE_INSTALL_PREFIX=../install \
../

make
make install
```

---

<br>

## Running with ADIOS2 I/O and/or Checkpointing

`ADIOS2` is an optional dependency that enables high-performance, parallel I/O. If enabled during compilation, it provides two major features:

1.  **High-Performance Visualization Output:** Writing data to scalable and self-describing ADIOS BP files.
2.  **Checkpoint/Restart:** The ability to save and restore the complete simulation state.

The behavior of the ADIOS2 engine (e.g., transport method, performance tuning) can be modified at runtime by editing the **`/configs/adios2_configs/adios2.xml`** file, without needing to recompile the simulation.

### High-Performance Data Output

The ADIOS2 writer adds **Fides** metadata directly into the output BP file. This schema allows visualization tools like ParaView to understand the parallel data layout and correctly interpret the grid structure. The writer also embeds all simulation parameters as attributes, ensuring the data is fully self-describing for provenance and reproducibility.

#### Step 1: ⚙️ Configure the Writer

To use the ADIOS2 writer, you must set the `output_type` to `"adios"` in your JSON settings file. You can choose one of three data handling strategies:

| Strategy                    | Description                                                                                                                                  | JSON Flags                                               |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **Zero-Copy (Recommended)** | Highest performance. ADIOS2 reads data directly from the simulation's memory, avoiding any data copies.                                      | `"adios_memory_selection": true`, `"adios_span": false`  |
| **ADIOS-Managed (Span)**    | ADIOS2 provides a memory buffer, and the application copies its data into it. Avoids memory allocations in the application's I/O path.       | `"adios_memory_selection": false`, `"adios_span": true`  |
| **Local Copy (Default)**    | A local copy of the data is created and passed to ADIOS2. Easiest to understand but less performant due to the extra memory allocation/copy. | `"adios_memory_selection": false`, `"adios_span": false` |

#### Step 2: 🚀 Execute the Simulation

Once your settings file is configured, create a run directory and execute the simulation.

```bash
# Navigate to your project's installation directory
cd <path_to_install>

# Create a dedicated directory for the run
mkdir run-adios
cd run-adios

# Link the adios2.xml config file into the run directory
ln -s ../configs/adios2_configs/adios2.xml .

# Run the simulation (example uses the zero-copy settings)
mpirun -np 16 ../kvvm-gray-scott --settings-file=../configs/miniapp-settings/settings-adios-memselect.json
```

#### Step 3: ✅ Verify and Visualize

You can inspect the contents of the output file with the `bpls` command-line tool and visualize the data in ParaView.

1.  **Inspect with `bpls`:**

    ```bash
    bpls -al gs-adios-memselect.bp
    ```

    <details>
    <summary>Click to see sample bpls output</summary>

    ```
    File info:
      of variables:   3
      of attributes:  15
      statistics:     Min / Max

      attribute: F
        type:      double
        value:     0.01

      attribute: k
        type:      double
        value:     0.05

      attribute: adios_memory_selection
        type:      string
        value:     true

      attribute: Fides_Data_Model
        type:      string
        value:     uniform

      ... and so on for all other attributes ...
    ```

    </details>

2.  **Visualize in ParaView:**
    1.  Open your `.bp` file in ParaView (e.g., `gs-adios-memselect.bp`).
    2.  In the "Open File" dialog, make sure to select the **`ADIOS2FidesReader`** or **`FidesReader`** depending on ParaView version.
    3.  You will initially see the data with visible gaps between the blocks from each MPI rank.
    4.  To create a seamless image, select the dataset in the `Pipeline Browser` and apply the filter **`Filters` -> `Data Analysis` -> `Stitch Image Data With Ghosts`**.
    5.  The output of the `Stitch` filter will be a single, continuous grid ready for further visualization.

---

### Checkpoint & Restart

#### Step 1: ⚙️ Configure Checkpointing

To save or restore a simulation, edit the relevant flags in your JSON settings file.

- **To Save Checkpoints:**
  - `"checkpoint": true`
  - `"checkpoint_freq": 100` (Save every 100 steps)
  - `"checkpoint_output": "ckpt.bp"` (The output filename)
- **To Restart from a Checkpoint:**
  - `"restart": true`
  - `"restart_input": "ckpt.bp"` (The file to read from)

#### Step 2: 🚀 Execute the Simulation

Run the simulation using the same number of processes that the checkpoint was created with.

```bash
# Example command to restart from a checkpoint
mpirun -np 16 kvvm-gray-scott --settings-file=settings-vtk-pvti.json --logging-level=INFO
```

#### Step 3: ✅ Verify the Restart

The console will print messages confirming that it is reading the checkpoint file and restarting from the correct step.

<details>
<summary>Click to see sample restart output</summary>

```bash
(   0.258s) [Rank_0         ]            restart.cpp:81    INFO| Attempting to restart from file: ckpt.bp
(   0.318s) [Rank_0          ]            restart.cpp:124   INFO| Successfully read checkpoint. Restarting from step 10000
(   0.269s) [Rank_0         ]               main.cpp:239   INFO| Restarting simulation from step 10000

========================================
grid:                 128x128x128
restart:          from step 10000
...
========================================
```

</details>

---

<br>

## Running with VTK

VTK is a mandatory dependency of this code. We use it for logging and for basic output from the simulation. Below is how to run the `pvti` writer with Gray-Scott.

### How to run with the `pvti` writer

This is the standard output method using the mandatory VTK dependency. It saves the full simulation grid as a series of parallel VTK Image Data (`.pvti`) files, which are ideal for basic post-processing and analysis in visualization tools like ParaView.

### Step 1: ⚙️ Configure Settings

This run mode uses the **`settings-vtk-pvti.json`** configuration file. Before running, ensure the `output_type` within this file is set to `"pvti"`.

#### Step 2: 🚀 Execute the Simulation

Once the settings are confirmed, you can execute the simulation. It's good practice to create a separate directory for each run.

```bash
# Navigate to your project's installation directory
cd <path_to_install>

# Create a dedicated directory for the run
mkdir run-vtk
cd run-vtk

# Run the simulation with 32 processes using the vtk settings file
mpirun -np 32 ../kvvm-gray-scott --settings-file=../settings-vtk-pvti.json --logging-level=INFO
```

#### Step 3: ✅ Verify the Output

The console will display the run parameters and confirm that the simulation is writing output at each `plotgap` step. In your `run-vtk` directory, you will find a `.pvti` file for each output step, along with the corresponding `.vti` files containing the partitioned data.

<details>
<summary>Click to see sample output</summary>

```bash
========================================
grid:                 64x64x64
restart:              no
steps:                100
plotgap:              10
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:     grayScott-%04ts.vti
output_type:          pvti
...
process layout:       4x4x2
local grid size:      16x16x32
========================================
(   0.336s) [Rank_0          ]               main.cpp:273   INFO| Simulation at step 10 writing output step     1
(   0.358s) [Rank_0          ]               main.cpp:273   INFO| Simulation at step 20 writing output step     2
(   0.374s) [Rank_0          ]               main.cpp:273   INFO| Simulation at step 30 writing output step     3
```

</details>

---

<br>

## Running with Catalyst

Catalyst is an optional dependency and will allow you to use the power of ParaView to create great visualization pipelines and renderings. Below are some examples on ways to use Catalyst.

### How to run with catalyst file writer

This method uses Catalyst's file I/O capabilities to save the simulation's output data directly to disk as VTK partitioned datasets (`.vtpd`). This is useful for capturing the full dataset at specific timesteps for post-processing and analysis in ParaView or other visualization tools.

> 💡 **Note:** You must edit the settings file to provide the correct paths for your Catalyst installation.

#### Step 1: ⚙️ Configure Settings

Before running, you must edit the **`configs/miniapp-settings/settings-catalyst-file-io.json`** file.

1.  Ensure the `output_type` is set to `"catalyst_io"`.
2.  Set the `catalyst_lib_path` to the absolute path of your ParaView/Catalyst library installation.

#### Step 2: 🚀 Execute the Simulation

Once your settings file is configured, create a run directory and execute the simulation using `mpirun`.

```bash
# Navigate to your project's installation directory
cd <path_to_install>

# Create a dedicated directory for the run
mkdir run-catalyst-io
cd run-catalyst-io

# Run the simulation with 4 processes
mpirun -np 4 ../kvvm-gray-scott --settings-file=../settings-catalyst-file-io.json --logging-level=INFO
```

#### Step 3: ✅ Verify the Output

If successful, the console will display the run parameters and confirm that the simulation is writing output at each `plotgap` step. You will find the generated `.vtpd` files inside your `run-catalyst-io` directory.

<details>
<summary>Click to see sample output</summary>

```bash
========================================
grid:                 64x64x64
restart:              no
steps:                100
plotgap:              10
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:     grayScott-%04ts.vtpd
output_type:          catalyst_io
catalyst_script_path: test-catalyst.py
catalyst_script:      catalyst_pipeline.py
catalyst_lib_path:    /home/kressjm/packages/paraview-src/build_5.11.1/install/lib/catalyst
process layout:       2x2x1
local grid size:      32x32x64
========================================
(   0.439s) [pvbatch.0       ]               main.cpp:245   INFO| Simulation at step 10 writing output step     1
(   0.474s) [pvbatch.0       ]               main.cpp:245   INFO| Simulation at step 20 writing output step     2
(   0.493s) [pvbatch.0       ]               main.cpp:245   INFO| Simulation at step 30 writing output step     3
```

</details>

---

### How to run with catalyst in situ

This guide explains how to run the simulation with live, in-situ visualization and data extraction using ParaView Catalyst.

> 💡 **Note:** You must edit the settings file to provide the correct paths for your Catalyst installation.

#### Step 1: ⚙️ Configure Your Pipeline

Before running, you must edit the **`configs/miniapp-settings/settings-catalyst-insitu.json`** file.

1.  Set the `catalyst_lib_path` to the absolute path of your ParaView/Catalyst library installation.
2.  Set the `catalyst_script_path` to the absolute path of the pipeline script you wish to use from the options below.

##### Available Pipeline Scripts

Choose one of the following scripts for your analysis:

| Script                       | Description                                                                                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `catalyst-extract-jpg.py`    | **(Image Export)** Creates a full volume rendering colored by the 'v' scalar field and saves the visualization as a JPG image at each timestep.                                                       |
| `catalyst-multi-pipeline.py` | **(Advanced Visualization)** Renders both a semi-transparent volume of the full dataset and a solid clipped surface to reveal internal structures, saving the result as a PNG image at each timestep. |
| `catalyst-save-data.py`      | **(Data Export)** Saves the mesh and fields as a VTK file at each timestep. Ideal for post-hoc analysis.                                                                                              |

#### Step 2: 🚀 Execute the Simulation

Once your settings file is configured, create a run directory and execute the simulation using `mpirun`.

```bash
# Navigate to your project's installation directory
cd <path_to_install>

# Create a dedicated directory for the run
mkdir run-catalyst-insitu
cd run-catalyst-insitu

# Run the simulation with 4 processes
mpirun -np 4 ../kvvm-gray-scott --settings-file=../settings-catalyst-insitu.json --logging-level=INFO
```

#### Step 3: ✅ Verify the Output

If the simulation starts correctly, your console will display the run parameters, confirming which Catalyst script is being used.

<details>
<summary>Click to see sample output</summary>

```bash
========================================
grid:                 64x64x64
restart:              no
steps:                100
plotgap:              10
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:     grayScott-%04ts.vtpd
output_type:          catalyst
catalyst_script_path: /home/kressjm/packages/gray-scott/KAUST_Visualization_Vignettes/Miniapps/gray-scott/configs/catalyst_scripts/catalyst-extract-contour_v.py
catalyst_script:      catalyst-extract-contour_v.py
catalyst_lib_path:    /home/kressjm/packages/paraview-src/build_5.11.1/install/lib/catalyst
process layout:       2x2x1
local grid size:      32x32x64
========================================
```

</details>

---

### How to run with catalyst in situ and connect live (locally or on remote host)

This guide explains how to connect a ParaView GUI to the simulation in real-time. This allows you to interactively inspect data, change visualization parameters, and view results as they are being generated, either on your local machine or from a remote server.

> 💡 **Note:** You must edit the settings file to provide the correct paths for your Catalyst installation.

#### Step 1: ⚙️ Configure the Simulation

First, prepare the simulation environment. This involves editing the configuration file and setting an environment variable to tell the simulation where to find your ParaView session.

1.  **Edit the settings file:** Open **`configs/miniapp-settings/settings-catalyst-insitu.json`**.

    - Set the `catalyst_lib_path` to the absolute path of your ParaView/Catalyst library installation.
    - Set the `catalyst_script_path` to the absolute path of the pipeline script you wish to use (e.g., `catalyst-multi-pipeline.py`).

2.  **Prepare the run directory:** In your terminal, create a directory for the run and set the `CATALYST_CLIENT` environment variable. This variable must be the **IP address of the machine running the ParaView GUI**.

    ```bash
    # Navigate to your project's installation directory
    cd <path_to_install>

    # Create a dedicated directory for the run
    mkdir run-catalyst-live
    cd run-catalyst-live

    # Set the viewer's IP address (e.g., localhost or a remote IP)
    export CATALYST_CLIENT=<your_viewer_IP_address>
    ```

#### Step 2: 🖥️ Set Up the ParaView Viewer

Next, open the ParaView application and prepare it to receive the connection from the simulation.

1.  **Launch ParaView:** Start the ParaView GUI on your viewing machine.

2.  **Start the Catalyst Connection:**
    - Go to the menu `Catalyst` -> `Connect`.
    - ParaView will now pause and wait for the simulation to connect to it.

> **💡 Important MPI Note:** If your simulation will run in parallel with MPI (e.g., `mpirun -np 4`), you must first start a parallel ParaView server (`pvserver`) and connect to it. If you skip this, you will only see data from a single process.
>
> 1.  In a **separate terminal**, start `pvserver`: `mpirun -np 4 pvserver`
> 2.  In the ParaView GUI, connect to this server (`File` -> `Connect`).
> 3.  _Then_, proceed with `Catalyst` -> `Connect`.

#### Step 3: 🚀 Run the Simulation & View Results

Finally, with ParaView waiting for a connection, go back to your first terminal and launch the simulation.

```bash
# This command is run in the same terminal where you set CATALYST_CLIENT
mpirun -np 4 ../kvvm-gray-scott --settings-file=../settings-catalyst-insitu.json --logging-level=INFO
```

<details>
<summary>Click to see sample output</summary>

```bash
========================================
grid:                 64x64x64
restart:              no
steps:                100
plotgap:              10
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:     grayScott-%04ts.vtpd
output_type:          catalyst
catalyst_script_path: /home/kressjm/packages/gray-scott/KAUST_Visualization_Vignettes/Miniapps/gray-scott/configs/catalyst_scripts/catalyst-extract-contour_v.py
catalyst_script:      catalyst-extract-contour_v.py
catalyst_lib_path:    /home/kressjm/packages/paraview-src/build_5.11.1/install/lib/catalyst
process layout:       2x2x1
local grid size:      32x32x64
========================================
```

</details>

---

<br>

## Running with Ascent

Ascent is an optional dependency and will allow you to use the power of Ascent, trigger, VTK-m, and more, to create great visualization pipelines and renderings. Below are some examples on ways to use Ascent.

### Step 1: ⚙️ Configure Your Pipeline

> 💡 **Note:** You must copy the `ascent_options.yaml` and the `ascent_actions` file you are using into your run directory. Ascent looks for a file called `ascent_options.yaml` when it runs, if it is not there, it will run a default action. In addition, you can change the actions you have ascent do by changing the name of the actions script in the options file.

Ascent uses a two-file system:

1.  **`ascent_options.yaml`**: A controller file that tells Ascent which actions to perform.
2.  **Actions File**: A YAML file (e.g., `ascent-extract-png.yaml`) containing the actual visualization and I/O instructions.

To choose which visualization to run, you must edit **`ascent_options.yaml`** and change the `actions_file` key to point to one of the scripts listed below.

#### Available Actions Scripts

| Script                       | Description                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ascent-extract-png.yaml`    | **(Image Export)** Performs a volume rendering of the **'v'** scalar field and saves the visualization as a series of PNG images.                                         |
| `ascent-multi-pipeline.yaml` | **(Advanced Visualization)** Renders both a semi-transparent volume and a solid clipped surface of the **'u'** field into a single composite PNG image for each timestep. |
| `ascent-save-data.yaml`      | **(Data Export)** Saves the simulation data to an HDF5 file. **Known Limitation:** This script overwrites its output file at each timestep.                               |

### Step 2: 🚀 Execute the Simulation

Once you have configured `ascent_options.yaml` to point to your desired actions file, you can run the simulation.

#### ⚠️ Troubleshooting HDF5 Version Errors

If your simulation crashes with an `HDF5 library version mismatched error`, it means your system is loading an older, incompatible HDF5 library. To fix this, you must force the system to load the correct library using the `LD_PRELOAD` environment variable **before** running `mpirun`.

You will need to replace the path with the location of the `libhdf5.so` file from your specific Ascent installation.

```bash
# Example command to fix HDF5 version conflicts
export LD_PRELOAD=/path/to/your/ascent/install/lib/libhdf5.so
```

#### Run Command

```bash
# Navigate to your project's installation directory
cd <path_to_install>

# Create a dedicated directory for the run
mkdir run-ascent
cd run-ascent

# Create symbolic links to the necessary Ascent files
# The options file tells Ascent which actions file to use
ln -s ../configs/ascent_scripts/ascent_options.yaml .

# Link all available action scripts so they can be found
ln -s ../configs/ascent_scripts/ascent-extract-png.yaml .
ln -s ../configs/ascent_scripts/ascent-multi-pipeline.yaml .
ln -s ../configs/ascent_scripts/ascent-save-data.yaml .

# Run the simulation with 4 processes
mpirun -np 4 ../kvvm-gray-scott --settings-file=../configs/miniapp-settings/settings-ascent.json --logging-level=INFO
```

### Step 3: ✅ Verify the Output

If the simulation starts correctly, your console will display the run parameters, confirming that the `output_type` is `ascent`. Depending on the script you chose, you will find PNG images or `hdf5` files in your run directory.

<details>
<summary>Click to see sample output</summary>

```bash
========================================
grid:                 64x64x64
restart:              no
steps:                100
plotgap:              10
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:     grayScott-%04ts.vti
output_type:          ascent
catalyst_script_path:
catalyst_lib_path:
process layout:       2x2x1
local grid size:      32x32x64
========================================
```

</details>

---

<br>

## Running with Kombyne

Kombyne is an optional dependency that provides in-situ capabilities, allowing you to create visualization pipelines and renderings directly from the simulation. Kombyne is a commercial in situ product, as such, this repo makes use of the `lite` version which is free, but not folly featured. Below are instructions on how to configure and run the included Kombyne examples.

### Step 1: ⚙️ Configure Your Pipeline

To run with Kombyne, you must first edit the **`/configs/miniapp-settings/settings-kombyne.json`** file.

Inside this file, you need to set the `kombynelite_script_path` key to the name of the in-situ script you wish to execute from the options below.

**Example `settings-kombyne.json`:**

```json
{
    ...
    "output_type": "kombyne",
    "kombynelite_script_path": "kombyne-extract-png.yaml"
    ...
}
```

#### Available In-Situ Scripts

| Script                        | Description                                                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `kombyne-extract-png.yaml`    | **(Image Export)** Performs a rendering of a slice of the scalar field and saves the visualization as a series of PNG images.               |
| `kombyne-multi-pipeline.yaml` | **(Advanced Visualization)** Renders two seperate images, first, a slice and second, an isosurface, creating a PNG image for each timestep. |
| `kombyne-save-data.yaml`      | **(Data Export)** Saves the simulation data to a \*.vtm file at each time step.                                                             |

> 💡 **Note:** Kombyne does not support the same actions that the other in situ libraries in this miniapp do, as a result, its renderings are close approximations to what the other in situ systems produce.

### Step 2: 🚀 Execute the Simulation

Once you have configured the settings file to point to your desired script, you can run the simulation.

```bash
# Navigate to your project's installation directory
cd <path_to_install>

# Create a dedicated directory for the run
mkdir run-kombyne
cd run-kombyne

# Create symbolic links to the necessary Kombyne scripts
ln -s ../configs/kombyne_scripts/kombyne-extract-png.yaml .
ln -s ../configs/kombyne_scripts/kombyne-multi-pipeline.yaml .
ln -s ../configs/kombyne_scripts/kombyne-save-data.yaml .

# Run the simulation with 4 processes
mpirun -np 4 ../kvvm-gray-scott --settings-file=../configs/miniapp-settings/settings-kombyne.json --logging-level=INFO
```

### Step 3: ✅ Verify the Output

If the simulation starts correctly, your console will display the run parameters, confirming that the `output_type` is `kombyne`. Depending on the script you chose, you will find PNG images or data files in your run directory.

<details>
<summary>Click to see sample console output</summary>

```bash
========================================
grid:                 128x128x128
restart:              no
steps:                100
plotgap:              10
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:
output_type:          kombyne
kombynelite_script_path: kombyne-extract-png.yaml
process layout:       2x2x1
local grid size:      64x64x64
========================================
```

</details>

---

<br>

## ⏱️ Performance Timers and Visualization

This project includes an optional feature to collect and visualize detailed performance timers, helping you understand and analyze the simulation's performance characteristics. The same code and script are used for both the reader and writer performance timers.

### Enabling Timers

To instrument the code and collect performance data, you must enable the timers during the CMake configuration step by setting the `ENABLE_TIMERS` option to `ON` (or `1`).

```
Example of enabling timers during CMake configuration
cmake -DENABLE_TIMERS=ON ..
```

When you run a simulation that was built with timers enabled, a new directory named `writer_timers/` will be created in the run directory. This folder will be populated with `.csv` files—one for each MPI rank—containing detailed timing information for each simulation step.

### Visualizing the Timers

A Python script is provided to easily parse all the generated timer files and create a comprehensive summary plot.

#### Prerequisites

The script depends on the **pandas**, **matplotlib**, and **numpy** libraries. You can install them using pip:

```
pip install pandas matplotlib numpy
```

#### Running the Script

```
python3 visualize-gray-scott-timers.py
```

This will process all `.csv` files in the `writer_timers/` subdirectory and generate an image file named `gray_scott_timers_summary.png`.

The summary image contains four plots providing a comprehensive overview of the run's performance:

1. **Timers per Step**: A line plot showing the mean time for each instrumented region, with shading to indicate the minimum and maximum times across all ranks. This is useful for seeing how performance changes over time and identifying rank-to-rank variation.

2. **Timers (stacked)**: A stacked bar chart showing the composition of the total step time, averaged across all ranks. This helps identify which operations are the most expensive.

3. **System Stats per Step**: A dual-axis plot showing memory usage (RSS) and CPU time (user/system) per step.

4. **Total Step Time by Rank**: A line plot showing the total wall-clock time for each step, with a separate line for each MPI rank. This is excellent for diagnosing load imbalance issues.


### Ascent specific Performance Analysis
Ascent has built in timings for filters, we can enable this and visualize where time is being spent in Ascent. 

#### How to Enable Ascent Timings
To get detailed performance data, you need to instruct Ascent to generate timing files. This is done by creating or editing an Ascent options file (commonly named `ascent_options.yaml`) in your run directory.

Set the `timings` option to `"true"` as shown below.

`ascent_options.yaml`:

```yaml
runtime:
  type: "ascent"
  vtkm:
    backend: "openmp"
actions_file: "ascent_actions.yaml" # Or your specific actions file
messages: "quiet"
timings: "true" # <-- This is the important flag
```

When you run your `analysis-reader` program with this file present, Ascent will generate one raw text file for each MPI rank. Each file contains a list of internal operations and the time each one took for every timestep.

#### Parsing the Raw Timing Files
The raw text files are not suitable for direct analysis. The `ascent_parse_timings.py` script reads all these files, correctly orders the data by MPI rank, and transposes it into a single, structured JSON file that is organized by operation and timestep.

##### Usage
Navigate to the directory containing the `ascent_filter_timings_*.csv` files and run the script:

```bash
python3 ascent_parse_timings.py
```

This will produce a single output file named `ascent_timings_summary.json`. This file is the input for the plotting script.

#### Visualizing the Performance Data
The `ascent_timings_plotter.py` script reads the `ascent_timings_summary.json` file and generates a multi-panel PNG image that provides a comprehensive overview of the performance.

##### Usage
To generate the plot image, run the script and provide the path to the JSON file:

```bash
python3 ascent_timings_plotter.py ascent_timings_summary.json
```

This will save a file named ascent_performance_breakdown.png.

#### Interactive Plotting
To open the plot in an interactive window (in addition to saving the file), use the `--show` flag:

```bash
python3 plot_ascent_performance.py ascent_timings_summary.json --show
```

### Kombyne specific Performance Analysis

Kombyne has a built-in timing infrastructure that can be used to generate detailed performance data. This document outlines how to enable these timers and use the provided script to visualize where time is being spent during a simulation.

#### How to Enable Kombyne Timings

To get performance data, simply export the following to your environment before execution: 

When enabled, Kombyne will generate one `timings.####.txt` file for each MPI rank in your run directory. Each file contains a detailed, hierarchical breakdown of internal operations and the time each one took.

*(Note: Please refer to your specific Kombyne simulation's documentation for the exact flag or option to enable timer output if it's not on by default.)*

#### Visualizing the Performance Data

The `kombyne_timings_plotter.py` script is an all-in-one tool that parses all raw `timings.*.txt` files, aggregates the total time spent in each operation across all ranks, and generates a sunburst plot summarizing the results.

##### Dependencies

Before running the script, you need to ensure you have the required Python packages installed. This script relies on `pandas` for data manipulation and `plotly` for plotting. To export the plot as a PDF, `kaleido` is also required. You can install all of them with the following command:

```
pip install --user pandas plotly "kaleido==0.1.*"

```

*(Note: A specific version of Kaleido is recommended for compatibility with recent Plotly versions.)*

##### Usage

Navigate to the directory containing the `timings.*.txt` files and run the script:

```
python3 kombyne_sunbukombyne_timings_plotter.py

```

This will process all timing files and save a PDF file named `kombyne_sunburst_performance.pdf`. This plot provides an intuitive, hierarchical view of the total time distribution.



<br>

## 🧪 Configuring the Gray-Scott Simulation

All simulation behavior, from the chemical reaction-diffusion model to data I/O and checkpointing, is controlled via a JSON settings file (e.g., `settings-vtk-pvti.json`).

### Simulation Parameters

The parameters are organized into three main groups:

#### Core Gray-Scott Parameters

These parameters control the reaction-diffusion model itself. Small changes here can dramatically alter the resulting patterns.

| Key     | Description                                                                                            |
| ------- | ------------------------------------------------------------------------------------------------------ |
| `L`     | The size of the global simulation grid, creating an **L x L x L** cube.                                |
| `Du`    | The diffusion coefficient for chemical **U**.                                                          |
| `Dv`    | The diffusion coefficient for chemical **V**.                                                          |
| `F`     | The **feed rate** of chemical **U**.                                                                   |
| `k`     | The **kill rate** of chemical **V**.                                                                   |
| `dt`    | The duration of each **timestep**.                                                                     |
| `noise` | The magnitude of the initial random **noise** injected into the system to kickstart pattern formation. |

> **Note:** The decomposition of the grid across processes is determined automatically by `MPI_Dims_create`.

#### I/O & In-Situ Parameters

These control the simulation's execution length and how data is saved or processed live.

| Key                       | Description                                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| `steps`                   | The total number of timesteps to simulate.                                                  |
| `plotgap`                 | How often to save output (e.g., a value of 10 saves data every 10 steps).                   |
| `output_file_name`        | A template for the output filename, ending in `.vti`, `.vtpd`, or `.bp`.                    |
| `output_type`             | The output mode: `pvti`, `catalyst_io`, `catalyst_insitu`, `adios`, `ascent`, or `kombyne`. |
| `catalyst_script_path`    | **(Catalyst Only)** The absolute path to the Python Catalyst pipeline script.               |
| `catalyst_lib_path`       | **(Catalyst Only)** The absolute path to your Catalyst library installation.                |
| `kombynelite_script_path` | **(Kombyne Only)** The path to the Kombyne Lite Python script.                              |
| `adios_config`            | **(ADIOS Only)** The path to the ADIOS2 XML configuration file.                             |
| `adios_span`              | **(ADIOS Only)** A boolean to enable ADIOS span functionality for in-transit processing.    |
| `adios_memory_selection`  | **(ADIOS Only)** A boolean to enable ADIOS memory selection.                                |

#### Checkpointing Parameters (Requires ADIOS)

Use these parameters to save and restart a simulation from a specific state.

| Key                 | Description                                                             |
| ------------------- | ----------------------------------------------------------------------- |
| `checkpoint`        | Set to `true` to enable saving checkpoint files.                        |
| `checkpoint_freq`   | How often (in steps) to save a checkpoint.                              |
| `checkpoint_output` | The filename for the output checkpoint file (e.g., `gs_checkpoint.bp`). |
| `restart`           | Set to `true` to restart the simulation from a checkpoint.              |
| `restart_input`     | The name of the checkpoint file to read from when restarting.           |

<table>
<thead>
<tr>
<th colspan="2">✨ Example Parameter Sets</th>
</tr>
</thead>
<tbody>
<tr>
<td colspan="2">
Here are several example parameter sets and the patterns they generate.
</td>
</tr>
<tr>
<td valign="top" width="50%">

Mitosis-like Patterns

Du: 0.2

Dv: 0.1

F: 0.02

k: 0.048

![](img/example1.jpg?raw=true)

</td>
<td valign="top" width="50%">

Worms and Loops

Du: 0.2

Dv: 0.1

F: 0.03

k: 0.0545

![](img/example2.jpg?raw=true)

</td>
</tr>
<tr>
<td valign="top" width="50%">

Labyrinthine Structures

Du: 0.2

Dv: 0.1

F: 0.03

k: 0.06

![](img/example3.jpg?raw=true)

</td>
<td valign="top" width="50%">

Spotted Patterns

Du: 0.2

Dv: 0.1

F: 0.01

k: 0.05

![](img/example4.jpg?raw=true)

</td>
</tr>
<tr>
<td valign="top" width="50%">

Coral Growth

Du: 0.2

Dv: 0.1

F: 0.02

k: 0.06

![](img/example5.jpg?raw=true)

</td>
<td valign="top" width="50%">
<!-- Empty cell for alignment -->
</td>
</tr>
</tbody>
</table>
