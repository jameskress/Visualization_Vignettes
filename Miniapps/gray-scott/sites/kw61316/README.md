# paraview superbuild
Build the paraview superbuild to get catalyst and libcatalyst_paraview

Configurations options:
catalyst
mpi
netcdf
hdf5
python3

use_system_mpi
use_system_python3


Debugging Catalyst
export CATALYST_DEBUG=1


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