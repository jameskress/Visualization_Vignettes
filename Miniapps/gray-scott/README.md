# KAUST Visualization Vignettes Miniapp - gray-scott

This is a 3D 7-point stencil code to simulate the following [Gray-Scott
reaction diffusion model](https://doi.org/10.1126/science.261.5118.189):

```
u_t = Du * (u_xx + u_yy + u_zz) - u * v^2 + F * (1 - u)  + noise * randn(-1,1)
v_t = Dv * (v_xx + v_yy + v_zz) + u * v^2 - (F + k) * v
```

A reaction-diffusion system is a system in which a dynamical system is attached to a diffusion equation, and it creates various patterns. This is an equation that simulates the chemical reaction between the chemicals $U$ and $V$. $U$ is called the activator and $V$ is called the repressor.

## How to build

Make sure `MPI`, and `VTK` are installed. These are non-optional dependencies. You can also enable `Catalyst` and or `Ascent` for more visualization options.

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

### Building Gray-Scott

```
cd <path_to_gray-scott>
mkdir build
cd build
ccmake -DCMAKE_INSTALL_PREFIX=../install \
  -DENABLE_TIMERS=ON \
  -Dcatalyst_DIR=<path_to>/paraview-build/install/lib/cmake/catalyst-2.0 \
  -DVTK_DIR=<path_to>/paraview-build/install/lib/cmake/paraview-5.13/vtk \
  -DAscent_DIR=<path_to>/ascent/build/install/ascent-checkout/lib/cmake/ascent \
  -DADIOS2_DIR=<path_to>/adios2-build \
  -DENABLE_ASCENT=ON \
  -DENABLE_CATALYST=ON \
  -DENABLE_ADIOS2=ON \
  -DCMAKE_INSTALL_PREFIX=../install \
  ../.
make
make install
```

Running `make install` will move all the interesting settings and implementation specific scripts into the `install` directory for easy use.

## Running Gray-Scott from a Checkpoint

To launch Gray-Scott from a checkpoint file, you will need to launch the simulation using the same number of processes and the same settings as the checkpoint file was originally created from. A restart file is a great way to be able to launch the simulation from an interesting point without having to rerun all of the initial time steps.

Checkpointing is enabled by setting `"checkpoint": true`` in the json config file.

Checkpoint restarts are enabled by setting `"restart": true`` in the json config file.

```
cd <path to>/install
mpirun -np 16 kvvm-gray-scott --settings-file=settings-vtk-pvti.json --logging-level=INFO

	Running ./kvvm-gray-scott with:
		--settings-file=settings-vtk-pvti.json
		--logging-level=INFO

	 - Number of tasks=16 My rank=0 Running on KW61316.kaust.edu.sa
(   0.258s) [Rank_0         ]            restart.cpp:81    INFO| Attempting to restart from file: ckpt.bp
(   0.318s) [Rank_0          ]            restart.cpp:124   INFO| Successfully read checkpoint. Restarting from step 10000
(   0.269s) [Rank_0         ]               main.cpp:239   INFO| Restarting simulation from step 10000

========================================
grid:                 128x128x128
restart:          from step 10000
checkpoint:           yes
checkpoint_freq:      100000
checkpoint_output:    ckpt.bp
steps:                10001
plotgap:              10001
F:                    0.01
k:                    0.05
dt:                   2
Du:                   0.2
Dv:                   0.1
noise:                1e-07
output_file_name:     grayScott-%04ts.vti
output_type:          pvti
catalyst_script_path:
catalyst_lib_path:
adios_config:         adios2.xml
process layout:       4x2x2
local grid size:      32x64x64
========================================

(   0.373s) [Rank_0          ]               main.cpp:319   INFO| Simulation at step 10001 writing output step     1

```

## Running with VTK

VTK is a mandatory dependency of this code. We use it for logging and for basic output from the simulation. Below is how to run the `pvti` writer with Gray-Scott.

### How to run with pvti writer

```
cd <path to>/install
mpirun -np 32 kvvm-gray-scott --settings-file=settings-vtk-pvti.json --logging-level=INFO

	Running kvvm-gray-scott with:
		--settings-file=settings-vtk-pvti.json
		--logging-level=INFO

	 - Number of tasks=32 My rank=0 Running on KW61316.kaust.edu.sa
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
output_type:
catalyst_script_path:
catalyst_lib_path:
process layout:       4x4x2
local grid size:      16x16x32
========================================
(   0.336s) [Rank_0          ]               main.cpp:273   INFO| Simulation at step 10 writing output step     1
(   0.358s) [Rank_0          ]               main.cpp:273   INFO| Simulation at step 20 writing output step     2
(   0.374s) [Rank_0          ]               main.cpp:273   INFO| Simulation at step 30 writing output step     3


```

## Running with VTK

VTK is a mandatory dependency of this code. We use it for logging and for basic output from the simulation. Below is how to run the `pvti` writer with Gray-Scott.

### How to run with the `pvti` writer

```bash
cd <path to>/install
mpirun -np 32 ./kvvm-gray-scott --settings-file=settings-vtk-pvti.json --logging-level=INFO
```
#### Sample Output
```
    Running ./kvvm-gray-scott with:
        --settings-file=settings-vtk-pvti.json
        --logging-level=INFO

     - Number of tasks=32 My rank=0 Running on KW61316.kaust.edu.sa
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

---

## Running with ADIOS2

`ADIOS2` is an optional dependency that enables high-performance, parallel I/O. If enabled during compilation, it provides two major features:
1.  **Checkpoint/Restart:** The ability to save and restore the complete simulation state.
2.  **High-Performance Visualization Output:** Writing data to ADIOS BP files, which are scalable and self-describing.

The BP file writer adds **Fides** metadata directly into the output file. This schema allows visualization tools like ParaView to understand the parallel data layout and correctly interpret the grid structure. The writer also embeds all simulation parameters as attributes, ensuring the data is fully self-describing for provenance and reproducibility.

### How to run with the ADIOS2 writer

To use the ADIOS2 writer, you must set the `output_type` to `"adios"` in your JSON settings file and specify an output filename ending in `.bp`. The writer supports three different data handling strategies, which can be selected via boolean flags in the settings file.

#### 1. Zero-Copy from Simulation Memory (Recommended)

This is the highest-performance method. It avoids any data copies by instructing ADIOS2 to read the core simulation data directly from the application's ghosted memory arrays.

**`settings-adios-memselect.json`**
```json
{
    "L": 128,
    "F": 0.01,
    "k": 0.05,
    "dt": 2.0,
    "Du": 0.2,
    "Dv": 0.1,
    "noise": 1e-7,
    "steps": 100,
    "plotgap": 10,
    "output_type": "adios",
    "output_file_name": "gs-adios-memselect.bp",
    "adios_memory_selection": true,
    "adios_span": false,
    "adios_config": "adios2.xml"
}
```

**Run Command:**
```bash
cd <path to>/install
mpirun -np 16 ./kvvm-gray-scott --settings-file=settings-adios-memselect.json
```

---
#### 2. Using ADIOS-Managed Arrays (Span)

This method asks ADIOS2 to provide a memory buffer, and the application then copies its data into that buffer. This avoids memory allocations in the application's I/O path.

**`settings-adios-span.json`**
```json
{
    "L": 128,
    "F": 0.01,
    "k": 0.05,
    "dt": 2.0,
    "Du": 0.2,
    "Dv": 0.1,
    "noise": 1e-7,
    "steps": 100,
    "plotgap": 10,
    "output_type": "adios",
    "output_file_name": "gs-adios-span.bp",
    "adios_memory_selection": false,
    "adios_span": true,
    "adios_config": "adios2.xml"
}
```

---
#### 3. Using Local Copied Arrays (Default)

This is a simple method where a local `std::vector` is created to hold a copy of the core data, which is then passed to ADIOS2. It is easy to understand but less performant due to the extra memory allocation and copy.

**`settings-adios-localcopy.json`**
```json
{
    "L": 128,
    "F": 0.01,
    "k": 0.05,
    "dt": 2.0,
    "Du": 0.2,
    "Dv": 0.1,
    "noise": 1e-7,
    "steps": 100,
    "plotgap": 10,
    "output_type": "adios",
    "output_file_name": "gs-adios-localcopy.bp",
    "adios_memory_selection": false,
    "adios_span": false,
    "adios_config": "adios2.xml"
}
```
---

### Inspecting the Output with `bpls`

You can verify the contents of your output file, including all the metadata and attributes, using the `bpls` command-line tool provided with ADIOS2. The `-al` flags provide a detailed "long" listing of attributes.

```bash
bpls -al gs-adios-memselect.bp
```
**Sample Output:**
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

### Visualizing in ParaView

The Fides metadata allows ParaView to read the distributed `.bp` file as a single, coherent dataset.

1.  Open your `.bp` file in ParaView (e.g., `gs-adios-memselect.bp`).
2.  In the "Open File" dialog, make sure to select the **`ADIOS2FidesReader`**.
3.  You will initially see the data with visible, cell-wide gaps between the blocks from each MPI rank. This is a normal artifact of viewing partitioned data before it has been stitched.
4.  To create a seamless image, select the dataset in the `Pipeline Browser` and apply the filter **`Filters` -> `Data Analysis` -> `Stitch Image Data With Ghosts`**.
5.  The output of the `Stitch` filter will be a single, continuous grid. You can now use this object for all further visualization (Contour, Slice, Volume Rendering, etc.).



## Running with Catalyst

Catalyst is an optional dependency and will allow you to use the power of ParaView to create great visualization pipelines and renderings. Below are some examples on ways to use Catalyst.

### How to run with catalyst file writer

> 💡 **Note:** You must edit the settings file to provide the correct paths for your Catalyst installation.

```
edit settings file to use correct paths for your machine (configs/miniapp-settings/settings-catalyst-file-io.json)
cd <path_to_install>
mkdir run-catalyst-io
cd run-catalyst-io
mpirun -np 4 ../kvvm-gray-scott --settings-file=../settings-catalyst-file-io.json --logging-level=INFO

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

### How to run with catalyst in situ

> 💡 **Note:** You must edit the settings file to provide the correct paths for your Catalyst installation.

```
edit settings file to use correct paths for your machine (configs/miniapp-settings/settings-catalyst-insitu.json)
cd <path_to_install>
mkdir run-catalyst-insitu
cd run-catalyst-insitu
mpirun -np 4 ../kvvm-gray-scott --settings-file=../settings-catalyst-insitu.json --logging-level=INFO

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

### How to run with catalyst in situ and connect live (locally or on remote host)

> 💡 **Note:** You must edit the settings file to provide the correct paths for your Catalyst installation.

```
edit settings file to use correct paths for your machine (configs/miniapp-settings/settings-catalyst-insitu.json)
cd <path_to_install>
mkdir run-catalyst-live
cd run-catalyst-live
export CATALYST_CLIENT=<your_viewer_IP>
```

> Run ParaView GUI, start catalyst connection
>
> If you are running with MPI, you have to manually start a `pvserver` with the number of procs that you are using for the simulation, or you will just see one block from the simulation.
>
> i.e. `mpirun -np 4 pvserver`
> Then, connect to that pvserver from paraview
> Then, start catalyst.

```
mpirun -np 4 ../kvvm-gray-scott --settings-file=../settings-catalyst-insitu.json --logging-level=INFO
view the results in ParaView

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

## Running with Ascent

Ascent is an optional dependency and will allow you to use the power of Ascent, trigger, VTK-m, and more, to create great visualization pipelines and renderings. Below are some examples on ways to use Ascent.

### How to run with catalyst in situ

> 💡 **Note:** You must copy the `ascent_options.yaml` and the `ascent_actions` file you are using into your run directory. Ascent looks for a file called `ascent_options.yaml` when it runs, if it is not there, it will run a default action. In addition, you can change the actions you have ascent do by changing the name of the actions script in the options file.

```
cd <path_to_install>
mkdir run-ascent
cd run-ascent
ln -s ../ascent_options.yaml .
ln -s ../ascent-extract-png.yaml .
ln -s ../ascent-slice-iso-png.yaml .

mpirun -np 4 ../kvvm-gray-scott --settings-file=settings-ascent.json --logging-level=INFO


	Running ../kvvm-gray-scott with:
		--settings-file=../settings-ascent.json
		--logging-level=INFO

	 - Number of tasks=4 My rank=0 Running on KW61316.kaust.edu.sa
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

## How to change the parameters of Gray-Scott

Edit settings.json to change the parameters for the simulation.

| Key                  | Description                              |
| -------------------- | ---------------------------------------- |
| L                    | Size of global array (L x L x L cube)    |
| Du                   | Diffusion coefficient of U               |
| Dv                   | Diffusion coefficient of V               |
| F                    | Feed rate of U                           |
| k                    | Kill rate of V                           |
| dt                   | Timestep                                 |
| steps                | Total number of steps to simulate        |
| plotgap              | Number of steps between output           |
| noise                | Amount of noise to inject                |
| output_file_name     | filename ending in 'vti' or 'vtpd'       |
| output_type          | pvti/catalyst_io/catalyst_insitu/ascent  |
| catalyst_script_path | path to catalyst script                  |
| catalyst_lib_path    | path to catalyst lib                     |
| checkpoint           | true/false: turn on or off checkpointing |
| checkpoint_freq      | How often to checkpoint                  |
| checkpoint_output    | Name of the checkpoint file (\*.bp)      |
| restart              | true/false: launch sim from checkpoint   |
| restart_input        | Name of the checkpoint file to read      |

Decomposition is automatically determined by MPI_Dims_create.

## Examples

| D_u | D_v | F    | k      | Output                         |
| --- | --- | ---- | ------ | ------------------------------ |
| 0.2 | 0.1 | 0.02 | 0.048  | ![](img/example1.jpg?raw=true) |
| 0.2 | 0.1 | 0.03 | 0.0545 | ![](img/example2.jpg?raw=true) |
| 0.2 | 0.1 | 0.03 | 0.06   | ![](img/example3.jpg?raw=true) |
| 0.2 | 0.1 | 0.01 | 0.05   | ![](img/example4.jpg?raw=true) |
| 0.2 | 0.1 | 0.02 | 0.06   | ![](img/example5.jpg?raw=true) |
