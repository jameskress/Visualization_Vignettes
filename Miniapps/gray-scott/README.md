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

### Catalyst ###
The easiest way to get catalyst and VTK is to use the ParaView Superbuild. This will also enable easy live viewing from Catalyst in ParaView.

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

### Ascent ###
To build ascent, follow one of the methods listed in the Ascent documentation. Below is the method that we have tested. 

```
git clone --recursive https://github.com/alpine-dav/ascent.git
cd ascent
env prefix=build env enable_mpi=ON enable_openmp=ON  ./scripts/build_ascent/build_ascent.sh
export Ascent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent
```



### Building Gray-Scott ###
```
cd <path_to_gray-scott>
mkdir build
cd build
ccmake -DCMAKE_INSTALL_PREFIX=../install \
  -DENABLE_TIMERS=ON \
  -Dcatalyst_DIR=<path_to>/paraview-build/install/lib/cmake/catalyst-2.0 \
  -DVTK_DIR=<path_to>/paraview-build/install/lib/cmake/paraview-5.13/vtk \
  ../.
make
make install
```

Running install will move all the interesting settings and implementation specific scripts into the install directory for easy use.


## Running with VTK ##
VTK is a mandatory dependency of this code. We use it for logging and for basic output from the simulation. Below is how to run the `pvti` writer with Gray-Scott. 

### How to run with pvti writer ###
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

## Running with Catalyst ##
Catalyst is an optional dependency and will allow you to use the power of ParaView to create great visualization pipelines and renderings. Below are some examples on ways to use Catalyst. 


### How to run with catalyst file writer ###
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


### How to run with catalyst in situ ###
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


### How to run with catalyst in situ and connect live (locally or on remote host) ##
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

## Running with Ascent ##
Ascent is an optional dependency and will allow you to use the power of Ascent, trigger, VTK-m, and more, to create great visualization pipelines and renderings. Below are some examples on ways to use Ascent. 


### How to run with catalyst in situ ###
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


## How to change the parameters of Gray-Scott ##

Edit settings.json to change the parameters for the simulation.

| Key           | Description                           |
| ------------- | ------------------------------------- |
| L             | Size of global array (L x L x L cube) |
| Du            | Diffusion coefficient of U            |
| Dv            | Diffusion coefficient of V            |
| F             | Feed rate of U                        |
| k             | Kill rate of V                        |
| dt            | Timestep                              |
| steps         | Total number of steps to simulate     |
| plotgap       | Number of steps between output        |
| noise         | Amount of noise to inject             |
| output        | Output file/stream name               |
| adios_config  | ADIOS2 XML file name                  |

Decomposition is automatically determined by MPI_Dims_create.

## Examples

| D_u | D_v | F    | k      | Output
| ----|-----|------|------- | -------------------------- |
| 0.2 | 0.1 | 0.02 | 0.048  | ![](img/example1.jpg?raw=true) |
| 0.2 | 0.1 | 0.03 | 0.0545 | ![](img/example2.jpg?raw=true) |
| 0.2 | 0.1 | 0.03 | 0.06   | ![](img/example3.jpg?raw=true) |
| 0.2 | 0.1 | 0.01 | 0.05   | ![](img/example4.jpg?raw=true) |
| 0.2 | 0.1 | 0.02 | 0.06   | ![](img/example5.jpg?raw=true) |
