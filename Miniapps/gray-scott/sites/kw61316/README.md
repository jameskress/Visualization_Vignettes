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

## ParaView 6.2 for the miniapp (2026-11-07, #19)

The miniapp builds against VTK and Catalyst from a ParaView 6.2 source build, because the 6.2 binary release ships no CMake configuration for either, and Catalyst must load the same ParaView the miniapp's VTK came from (otherwise two VTKs end up in one process).

* Recipe: `paraview-6.2.cmake` in this directory (a CMake initial-cache file; the header has the exact commands). It mirrors the options of the earlier 6.0.0 build: MPI with the system Open MPI, Python, Catalyst, HDF5, NetCDF, OpenMP.
* Needs CMake 3.25 or newer; the system has 3.22.1, so CMake 3.31.9 sits in `~/packages/cmake-3.31.9-linux-x86_64` (nothing system-wide changes).
* Install: `~/packages/paraview-src/build_6.2.0/install`. In `CMakeUserPresets.json`: `VTK_DIR` = `.../lib/cmake/paraview-6.2/vtk`, `catalyst_DIR` = `.../lib/cmake/catalyst-2.0`; settings files use `catalyst_lib_path` = `.../lib/catalyst`.
* Checked: `pvbatch` and `pvpython` 6.2.0 run (including 2-rank `pvbatch`); the miniapp builds with and without Catalyst; `settings-catalyst-insitu.json` runs on 1 and 2 ranks and writes its images; the binary links only 6.2 libraries.
* Rendering uses the system OpenGL with X, as the 6.0.0 build did. EGL (GPU, no display) and OSMesa (software, no display) are not switched on in this build; add them when headless rendering is needed.

## Running the Shaheen jobs locally (#76)

`run_generator_locally.py` runs the jobs of
`sites/shaheen/2026-WOIV-scripts/generate_experiments.py` on this machine
before they go to Shaheen III. It loads the generator itself and changes
only the sizes: 64^3, one "node" of `--ranks` ranks, a short initialisation
and short runs. Then it runs every Paper 1 job and the smallest Paper 2
strong, weak and in transit set and the #72 transport matrix at one small
size: inline as one `mpirun`, in transit as an
MPMD `mpirun` of the simulation and the analysis reader over SST. The
settings, `adios2.xml` and pipeline files are the generator's own.

```bash
python3 sites/kw61316/run_generator_locally.py \
    --aac build/aac --akc build/akc --work /tmp/gs-local \
    --catalyst-lib ~/packages/paraview-src/build_6.2.0/install/lib/catalyst \
    --ranks 2 4 --adios-matrix
```

* `--aac`: a build with ADIOS2, Ascent, Catalyst and the analysis reader.
  `--akc`: a build with Kombyne. Without it the Kombyne jobs are skipped.
* `--ranks 2 4` runs everything at both rank counts, then compares each
  job's images: at most 0.1% of pixels may differ by more than 24/255.
  In transit Catalyst slices are a known exception (#42) and are reported,
  not failed.
* `--adios-matrix` adds inline ADIOS2 data runs with every
  `adios_span` / `adios_memory_selection` combination.
* `--only <text>` runs only the jobs whose id contains the text.

It exits 1 if a job fails or an image comparison is over budget. A full
run at 2 and 4 ranks with `--adios-matrix` is 68 jobs and takes about
5 minutes on KW61316.

## Settings file

''output_file_name'': The format of this string is extrememly important, as catalyst requires specific things to work correctly. Specifically, the time step information must explicilty list ''ts''

- ex: ''grayScott-%04ts.vtpd''

See if the following work
export CATALYST_IMPLEMENTATION_PATHS="<paraview-install-dir>/lib/catalyst"
export CATALYST_IMPLEMENTATION_NAME=paraview/home/kressjm/packages/gray-scott/Visualization_Vignettes/Miniapps/gray-scott/README.md

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

To use a newer cmake
```bash
env PATH="/home/kressjm/packages/cmake-3.28.1-linux-x86_64/bin:$PATH" \
    prefix=build \
    enable_mpi=ON \
    enable_openmp=ON \
    ./scripts/build_ascent/build_ascent.sh
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

# ADIOS2 analysis reader

"output_type": "adios",
"output_file_name": "gs.bp"

<io name="SimulationOutput">
    <engine type="SST">
        <parameter key="DataTransport" value="MPI"/>
    </engine>
</io>

mpirun -np 2 ./analysis/analysis-reader \
 --engine=SST \
 --file=gs.bp \
 --vis=catalyst \
 --script=../configs/catalyst_scripts/catalyst-extract-jpg.py

mpirun -np 2 ./analysis/analysis-reader \
 --engine=SST \
 --file=gs.bp \
 --vis=ascent \
 --script=../configs/ascent_scripts/ascent-extract-png.yaml

#### Viskores (Required)

Viscores is the new brand of VTK-m, the VTK for emerging processor architectures. For now, only its basic options are required to build and use Fides.

```bash
git checkout https://github.com/Viskores/viskores.git
cd viskores
git checkout v1.0.0
git submodule update --init --recursive
mkdir viskores-build
cd viskores-build
cmake -DCMAKE_INSTALL_PREFIX=../viskores-install -DCMAKE_BUILD_TYPE=Release ../.
make -j8
```

#### Fides (Required)

```bash
git clone https://gitlab.kitware.com/vtk/fides.git
cd fides
git lfs install
git lfs pull
mkdir fides-build && cd fides-build
cmake \
    -DADIOS2_DIR=/home/kressjm/packages/Visualization_Vignettes/adios2-build \
    -DViskores_DIR=/home/kressjm/packages/Visualization_Vignettes/viskores/viskores-install/lib/cmake/viskores-1.0 \
    -DCMAKE_INSTALL_PREFIX=../fides-install \
    -DCMAKE_BUILD_TYPE=Release \
     ../.
make -j install
```

Current error in Fides:

```bash
INTERFACE_INCLUDE_DIRECTORIES "${_IMPORT_PREFIX}/include;${_IMPORT_PREFIX}/include/fides/predefined;${_IMPORT_PREFIX}/include/fides/xgc"
```

-DFides_DIR=/home/kressjm/packages/Visualization_Vignettes/fides/fides-install/lib/cmake/fides \
-DViskores_DIR=/home/kressjm/packages/Visualization_Vignettes/viskores/viskores-install/lib/cmake/viskores-1.0 \

Running with SST evpath
Reader
mpirun -np 3 ./analysis-reader --file=gs-adios-localcopy.bp --settings=settings-ascent.json --engine=SST

writer
mpirun -np 8 ./kvvm-gray-scott --settings-file=settings-adios-localcopy.json

Running with MPMD SST
mpirun -np 8 ./kvvm-gray-scott --settings-file=settings-adios-localcopy.json --mpi-split-color 0 \
 : \
 -np 3 ./analysis-reader --file=gs-adios-localcopy.bp --settings=settings-ascent.json --engine=SST --mpi-split-color 1



# Docker
Working on getting a docker image of this repo built so that the CI/CD pipeline will generate one on each commit allowing it to be downloaded and the code run with no building required. 

**locally**
From main dir run this to build the docker image locally for testing

```
docker build -t visualization-vignettes-app .
```
