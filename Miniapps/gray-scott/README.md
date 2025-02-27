# KAUST Visualization Vignettes Miniapp - gray-scott

This is a 3D 7-point stencil code to simulate the following [Gray-Scott
reaction diffusion model](https://doi.org/10.1126/science.261.5118.189):

```
u_t = Du * (u_xx + u_yy + u_zz) - u * v^2 + F * (1 - u)  + noise * randn(-1,1)
v_t = Dv * (v_xx + v_yy + v_zz) + u * v^2 - (F + k) * v
```

A reaction-diffusion system is a system in which a dynamical system is attached to a diffusion equation, and it creates various patterns. This is an equation that simulates the chemical reaction between the chemicals $U$ and $V$. $U$ is called the activator and $V$ is called the repressor.

## How to build
Make sure MPI, VTK, and Catalyst are installed.

### Catalyst ###
The easiest way to get catalyst and VTK is to use the ParaView Superbuild. This will also enable easy live viewing from Catalyst in ParaView.

```
Catalyst needs to be built with the SAME MPI compiler as gray-scott

git clone --recursive https://gitlab.kitware.com/paraview/paraview-superbuild.git
cd paraview-superbuild
git checkout v5.13.2
cd ..
mkdir paraview-build
cd paraview-build
ccmake -DUSE_SYSTEM_mpi=ON -DUSE_SYSTEM_python3=ON -DENABLE_catalyst=ON -DENABLE_mpi=ON -DENABLE_netcdf=ON -DENABLE_hdf5=ON -DENABLE_python3=ON ../paraview-superbuild
make -j
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

## How to run with pvti writer
```
export LD_LIBRARY_PATH=<path_to>/paraview-build/install/lib
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

ccmake -DCMAKE_INSTALL_PREFIX=../install \
  -DENABLE_TIMERS=ON \
  -Dcatalyst_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/paraview-build/install/lib/cmake/catalyst-2.0 \
  -DVTK_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/paraview-build/install/lib/cmake/paraview-5.13/vtk \
  ../.

## How to run with catalyst file writer
```
edit settings file to use correct paths for your machine (configs/miniapp-settings/settings-catalyst-file-io.json)
cd <path_to_install>
mkdir run
cd run
ln -s ../bin/kvvm-gray-scott .
mpirun -np 4 kvvm-gray-scott --settings-file=../../configs/miniapp-settings/settings-catalyst-file-io.json --logging-level=INFO

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


## How to run with catalyst in situ
```
edit settings file to use correct paths for your machine (configs/miniapp-settings/settings-catalyst-insitu.json)
cd <path_to_install>
mkdir run
cd run
ln -s ../bin/kvvm-gray-scott .
mpirun -np 4 kvvm-gray-scott --settings-file=../../configs/miniapp-settings/settings-catalyst-insitu.json --logging-level=INFO

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


## How to run with catalyst in situ and connect live (locally or on remote host)
```
edit settings file to use correct paths for your machine (configs/miniapp-settings/settings-catalyst-insitu.json)
cd <path_to_install>
mkdir run
cd run
ln -s ../bin/kvvm-gray-scott .
export CATALYST_CLIENT=<your_viewer_IP>
Run ParaView GUI, start catalyst connection
mpirun -np 4 kvvm-gray-scott --settings-file=../../configs/miniapp-settings/settings-catalyst-insitu.json --logging-level=INFO
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


## How to change the parameters

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
