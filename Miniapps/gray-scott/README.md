# KAUST Visualization Vignettes Miniapp - gray-scott

This is a 3D 7-point stencil code to simulate the following [Gray-Scott
reaction diffusion model](https://doi.org/10.1126/science.261.5118.189):

```
u_t = Du * (u_xx + u_yy + u_zz) - u * v^2 + F * (1 - u)  + noise * randn(-1,1)
v_t = Dv * (v_xx + v_yy + v_zz) + u * v^2 - (F + k) * v
```

A reaction-diffusion system is a system in which a dynamical system is attached to a diffusion equation, and it creates various patterns. This is an equation that simulates the chemical reaction between the chemicals $U$ and $V$. $U$ is called the activator and $V$ is called the repressor.

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

## How to build

Make sure `MPI`, and `VTK` are installed. These are non-optional dependencies. You can also enable `Catalyst`, `Ascent`, or `Kombyne` for more visualization options.

`ADIOS2` is required for checkpointing and for restarting a sim from a given checkpoint. If `ADIOS2` is not enabled then the checkpoint and restart options will be ignored in the settings.

### Catalyst

The easiest way to get `Catalyst` and `VTK` is to use the `ParaView Superbuild`. This will also enable easy live viewing from `Catalyst` in `ParaView`.

```
Catalyst needs to be built with the SAME MPI compiler as gray-scott

git clone --recursive https://gitlab.kitware.com/paraview/paraview-superbuild.git
cd paraview-superbuild
git checkout v5.13.3
cd ..
mkdir paraview-build
cd paraview-build
ccmake -DUSE_SYSTEM_mpi=ON -DUSE_SYSTEM_python3=ON -DENABLE_catalyst=ON -DENABLE_mpi=ON -DENABLE_netcdf=ON -DENABLE_hdf5=ON -DENABLE_python3=ON -DENABLE_openmp=ON  ../paraview-superbuild
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
cmake ../ADIOS2/ -DADIOS2_BUILD_EXAMPLES=ON
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

> 💡 **Note:**  `Ascent` and `Kombyne` cannot be enabled at the same time due to library conflicts.

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
-DENABLE_ASCENT=OFF \
-DENABLE_CATALYST=ON \
-DENABLE_ADIOS2=ON \
-DENABLE_KOMBYNELITE=ON \
-DCMAKE_INSTALL_PREFIX=../install \
../

make
make install
```

Running `make install` will move all the interesting settings and implementation specific scripts into the `install` directory for easy use.
</div>

---

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

## Running with ADIOS2 I/O and/or Checkpointing 
`ADIOS2` is an optional dependency that enables high-performance, parallel I/O. If enabled during compilation, it provides two major features:
1.  **High-Performance Visualization Output:** Writing data to scalable and self-describing ADIOS BP files.
2.  **Checkpoint/Restart:** The ability to save and restore the complete simulation state.

The behavior of the ADIOS2 engine (e.g., transport method, performance tuning) can be modified at runtime by editing the **`/configs/adios2_configs/adios2.xml`** file, without needing to recompile the simulation.


### High-Performance Data Output

The ADIOS2 writer adds **Fides** metadata directly into the output BP file. This schema allows visualization tools like ParaView to understand the parallel data layout and correctly interpret the grid structure. The writer also embeds all simulation parameters as attributes, ensuring the data is fully self-describing for provenance and reproducibility.

#### Step 1: ⚙️ Configure the Writer

To use the ADIOS2 writer, you must set the `output_type` to `"adios"` in your JSON settings file. You can choose one of three data handling strategies:

| Strategy                               | Description                                                                                                                              | JSON Flags                                                               |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Zero-Copy (Recommended)** | Highest performance. ADIOS2 reads data directly from the simulation's memory, avoiding any data copies.                                    | `"adios_memory_selection": true`, `"adios_span": false`                  |
| **ADIOS-Managed (Span)** | ADIOS2 provides a memory buffer, and the application copies its data into it. Avoids memory allocations in the application's I/O path.      | `"adios_memory_selection": false`, `"adios_span": true`                   |
| **Local Copy (Default)** | A local copy of the data is created and passed to ADIOS2. Easiest to understand but less performant due to the extra memory allocation/copy. | `"adios_memory_selection": false`, `"adios_span": false`                  |


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

* **To Save Checkpoints:**
    * `"checkpoint": true`
    * `"checkpoint_freq": 100` (Save every 100 steps)
    * `"checkpoint_output": "ckpt.bp"` (The output filename)
* **To Restart from a Checkpoint:**
    * `"restart": true`
    * `"restart_input": "ckpt.bp"` (The file to read from)



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
</div>

---

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

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
</div>

---

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

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

| Script                             | Description                                                                                                                                                                                              |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `catalyst-extract-jpg.py`          | **(Image Export)** Creates a full volume rendering colored by the 'v' scalar field and saves the visualization as a JPG image at each timestep.                                                            |
| `catalyst-multi-pipeline.py`       | **(Advanced Visualization)** Renders both a semi-transparent volume of the full dataset and a solid clipped surface to reveal internal structures, saving the result as a PNG image at each timestep.         |
| `catalyst-save-data.py`    | **(Data Export)** Saves the mesh and fields as a VTK file at each timestep. Ideal for post-hoc analysis.                                        |


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
    * Set the `catalyst_lib_path` to the absolute path of your ParaView/Catalyst library installation.
    * Set the `catalyst_script_path` to the absolute path of the pipeline script you wish to use (e.g., `catalyst-multi-pipeline.py`).

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
    * Go to the menu `Catalyst` -> `Connect`.
    * ParaView will now pause and wait for the simulation to connect to it.

> **💡 Important MPI Note:** If your simulation will run in parallel with MPI (e.g., `mpirun -np 4`), you must first start a parallel ParaView server (`pvserver`) and connect to it. If you skip this, you will only see data from a single process.
>
> 1.  In a **separate terminal**, start `pvserver`: `mpirun -np 4 pvserver`
> 2.  In the ParaView GUI, connect to this server (`File` -> `Connect`).
> 3.  *Then*, proceed with `Catalyst` -> `Connect`.



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
</div>

---

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

## Running with Ascent

Ascent is an optional dependency and will allow you to use the power of Ascent, trigger, VTK-m, and more, to create great visualization pipelines and renderings. Below are some examples on ways to use Ascent.

### Step 1: ⚙️ Configure Your Pipeline

> 💡 **Note:** You must copy the `ascent_options.yaml` and the `ascent_actions` file you are using into your run directory. Ascent looks for a file called `ascent_options.yaml` when it runs, if it is not there, it will run a default action. In addition, you can change the actions you have ascent do by changing the name of the actions script in the options file.


Ascent uses a two-file system:
1.  **`ascent_options.yaml`**: A controller file that tells Ascent which actions to perform.
2.  **Actions File**: A YAML file (e.g., `ascent-extract-png.yaml`) containing the actual visualization and I/O instructions.

To choose which visualization to run, you must edit **`ascent_options.yaml`** and change the `actions_file` key to point to one of the scripts listed below.


#### Available Actions Scripts

| Script                        | Description                                                                                                                                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ascent-extract-png.yaml`     | **(Image Export)** Performs a volume rendering of the **'v'** scalar field and saves the visualization as a series of PNG images.                                                                                           |
| `ascent-multi-pipeline.yaml`  | **(Advanced Visualization)** Renders both a semi-transparent volume and a solid clipped surface of the **'u'** field into a single composite PNG image for each timestep.                                  |
| `ascent-save-data.yaml`       | **(Data Export)** Saves the simulation data to an HDF5 file. **Known Limitation:** This script overwrites its output file at each timestep.             |



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
</div>

---

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

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

| Script                        | Description                                                                                                                                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `kombyne-extract-png.yaml`    | **(Image Export)** Performs a rendering of a slice of the scalar field and saves the visualization as a series of PNG images.                                                                                                 |
| `kombyne-multi-pipeline.yaml` | **(Advanced Visualization)** Renders two seperate images, first, a slice and second, an isosurface, creating a PNG image for each timestep.                                         |
| `kombyne-save-data.yaml`      | **(Data Export)** Saves the simulation data to a *.vtm file at each time step. |

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
</div>

---

<div style="background-color: #f9f9f9; border: 1px solid #e1e1e1; border-radius: 8px; padding: 20px; margin-bottom: 20px;">

## 🧪 Configuring the Gray-Scott Simulation

All simulation behavior, from the chemical reaction-diffusion model to data I/O and checkpointing, is controlled via a JSON settings file (e.g., `settings-vtk-pvti.json`).


### Simulation Parameters

The parameters are organized into three main groups:

#### Core Gray-Scott Parameters

These parameters control the reaction-diffusion model itself. Small changes here can dramatically alter the resulting patterns.

| Key         | Description                                                                                             |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| `L`         | The size of the global simulation grid, creating an **L x L x L** cube.                                 |
| `Du`        | The diffusion coefficient for chemical **U**.                                                           |
| `Dv`        | The diffusion coefficient for chemical **V**.                                                           |
| `F`         | The **feed rate** of chemical **U**.                                                                    |
| `k`         | The **kill rate** of chemical **V**.                                                                    |
| `dt`        | The duration of each **timestep**.                                                                      |
| `noise`     | The magnitude of the initial random **noise** injected into the system to kickstart pattern formation.  |

> **Note:** The decomposition of the grid across processes is determined automatically by `MPI_Dims_create`.

#### I/O & In-Situ Parameters

These control the simulation's execution length and how data is saved or processed live.

| Key                         | Description                                                                                                            |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `steps`                     | The total number of timesteps to simulate.                                                                             |
| `plotgap`                   | How often to save output (e.g., a value of 10 saves data every 10 steps).                                              |
| `output_file_name`          | A template for the output filename, ending in `.vti`, `.vtpd`, or `.bp`.                                                       |
| `output_type`               | The output mode: `pvti`, `catalyst_io`, `catalyst_insitu`, `adios`, `ascent`, or `kombyne`.                              |
| `catalyst_script_path`      | **(Catalyst Only)** The absolute path to the Python Catalyst pipeline script.                                            |
| `catalyst_lib_path`         | **(Catalyst Only)** The absolute path to your Catalyst library installation.                                             |
| `kombynelite_script_path`   | **(Kombyne Only)** The path to the Kombyne Lite Python script.                                                           |
| `adios_config`              | **(ADIOS Only)** The path to the ADIOS2 XML configuration file.                                                          |
| `adios_span`                | **(ADIOS Only)** A boolean to enable ADIOS span functionality for in-transit processing.                                 |
| `adios_memory_selection`    | **(ADIOS Only)** A boolean to enable ADIOS memory selection.                                                             |

#### Checkpointing Parameters (Requires ADIOS)

Use these parameters to save and restart a simulation from a specific state.

| Key                 | Description                                                                 |
| ------------------- | --------------------------------------------------------------------------- |
| `checkpoint`        | Set to `true` to enable saving checkpoint files.                            |
| `checkpoint_freq`   | How often (in steps) to save a checkpoint.                                  |
| `checkpoint_output` | The filename for the output checkpoint file (e.g., `gs_checkpoint.bp`).     |
| `restart`           | Set to `true` to restart the simulation from a checkpoint.                  |
| `restart_input`     | The name of the checkpoint file to read from when restarting.               |


#### **✨ Example Parameter Sets**

Here are several example parameter sets and the patterns they generate.

#### Mitosis-like Patterns
* `Du`: 0.2
* `Dv`: 0.1
* `F`: 0.02
* `k`: 0.048

![](img/example1.jpg?raw=true)

#### Worms and Loops
* `Du`: 0.2
* `Dv`: 0.1
* `F`: 0.03
* `k`: 0.0545

![](img/example2.jpg?raw=true)

#### Labyrinthine Structures
* `Du`: 0.2
* `Dv`: 0.1
* `F`: 0.03
* `k`: 0.06

![](img/example3.jpg?raw=true)

#### Spotted Patterns
* `Du`: 0.2
* `Dv`: 0.1
* `F`: 0.01
* `k`: 0.05

![](img/example4.jpg?raw=true)

#### Coral Growth
* `Du`: 0.2
* `Dv`: 0.1
* `F`: 0.02
* `k`: 0.06

![](img/example5.jpg?raw=true)
</div>