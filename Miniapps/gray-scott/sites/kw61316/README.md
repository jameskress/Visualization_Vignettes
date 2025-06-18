# paraview superbuild
Build the paraview superbuild to get catalyst and libcatalyst_paraview

Configurations options:
catalyst
mpi
netcdf
hdf5
python3
openmp

use_system_mpi
use_system_python3


Debugging Catalyst
export CATALYST_DEBUG=1

../../cmake-3.28.1-linux-x86_64/bin/cmake ../paraview-superbuild \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-9 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-9 \
  -DUSE_SYSTEM_mpi=ON \
  -DUSE_SYSTEM_python3=ON \
  -DENABLE_catalyst=ON \
  -DENABLE_mpi=ON \
  -DENABLE_netcdf=ON \
  -DENABLE_hdf5=ON \
  -DENABLE_python3=ON \
  -DENABLE_openmp=ON \
  -DENABLE_paraview=ON \
  -DENABLE_qt5=ON


## Settings file
''output_file_name'': The format of this string is extrememly important, as catalyst requires specific things to work correctly. Specifically, the time step information must explicilty list ''ts''
- ex: ''grayScott-%04ts.vtpd''


See if the following work
export CATALYST_IMPLEMENTATION_PATHS="<paraview-install-dir>/lib/catalyst"
export CATALYST_IMPLEMENTATION_NAME=paraview/home/kressjm/packages/gray-scott/KAUST_Visualization_Vignettes/Miniapps/gray-scott/README.md



# Ibex setup

souce ../../sites/ibex/MODULES.sh


cmake \
-Dcatalyst_DIR=/sw/vis/ibex-gpu/paraview-buildMesa-5.11.1/install/lib/cmake/catalyst-2.0 \
-DVTK_DIR=/sw/vis/ibex-gpu/paraview-buildMesa-5.11.1/install/lib/cmake/paraview-5.11/vtk \
../

make
mkdir run
cd run
ln -s ../kvvm-gray-scott .
ln -s ../../sites/ibex/run-ibex.sbat .
ln -s ../../sites/ibex/MODULES.sh .
ln -s ../../configs/miniapp-settings/ibex-settings-catalyst-file-io.json .


# ADIOS setup
install spack

```
cd /home/kressjm/spack
source share/spack/setup-env.sh 
spack install adios2
```

Installed here:
```
/home/kressjm/spack/opt/spack/linux-ubuntu22.04-zen2/gcc-9.5.0/adios2-2.10.2-5afosapsy4gnq2aj6tsfgoeseqstotsi
```

# Ascent setup

Had to edit my spack compilers and remove the newer ones as I am using 9.5.0 right now and spack was using the newer versions
```
vim ~/.spack/linux/compilers.yaml
```

```
git clone --recursive https://github.com/alpine-dav/ascent.git
cd ascent
env prefix=build env enable_mpi=ON enable_openmp=ON  ./scripts/build_ascent/build_ascent.sh
export Ascent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent
```


# adioscatalyst setup (This was an experiment, and does not work yet)
export ADIOS2_DIR=/home/kressjm/spack/opt/spack/linux-ubuntu22.04-zen2/gcc-9.5.0/adios2-2.8.0-ir6hgwpiqtyqpavutzj7asibbjqbfjzf
export catalyst_DIR=/home/kressjm/packages/catalyst/install

export catalyst_DIR=/home/kressjm/packages/paraview-src/build_5.12.0/superbuild/catalyst/build
export ParaView_DIR=/home/kressjm/packages/paraview-src/build_5.12.0/install

export CATALYST_IMPLEMENTATION_PATH=/home/kressjm/packages/adioscatalyst/build/lib/catalyst
export CATALYST_IMPLEMENTATION_NAME=adios


export CATALYST_IMPLEMENTATION_PATHS="/home/kressjm/packages/paraview-src/build_5.12.0/install/lib/catalyst"
export CATALYST_IMPLEMENTATION_NAME=paraview
bin/AdiosReplay ../Examples/Commons/adios2.xml


# Running locally

## Running Ascent from the install directoy
There is an issue with the install, the rpath is not working and libs are not being found

```
export LD_LIBRARY_PATH=/home/kressjm/packages/gray-scott/paraview-build-512/install/lib/:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/home/kressjm/packages/ascent/build/install/conduit-v0.9.3/lib/:$LD_LIBRARY_PATH
mpirun -np 1 kvvm-gray-scott --settings-file=settings-ascent.json --logging-level=TRACE
```

Modify the `settings-ascent.json` file to use the appropriate ascent_actions file. 

Ascent actions can be specified within the integration using Conduit Nodes and can be read in through a file. Actions files can be defined in both yaml or json, and if you are human, we recommend using yaml. Each time Ascent executes a set of actions, it will check for a file in the current working directory called ascent_actions.yaml or ascent_actions.json. If found, the current actions specified in code will be replaced with the contents of the yaml or json file. Then default name of the ascent actions file can be specified in the ascent_options.yaml or in the ascent options inside the simulation integration.




# Old build settings
~/packages/cmake-3.27.5-linux-x86_64/bin/cmake \
-Dcatalyst_DIR=/home/kressjm/packages/gray-scott/paraview-build-512/install/lib/cmake/catalyst-2.0 \
-DVTK_DIR=/home/kressjm/packages/gray-scott/paraview-build-512/install/lib/cmake/paraview-5.12/vtk \
-DAscent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent \
-DENABLE_TIMERS=1 \
-DCMAKE_BUILD_TYPE=DEBUG \
-DENABLE_ASCENT=ON \
-DENABLE_CATALYST=ON \
-DCMAKE_INSTALL_PREFIX=../install \
../




# ADIOS2 for checkpointing and restarting sim


