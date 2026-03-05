# IBEX specific notes

## Building software to run gray-scott

System openmpi does not include the mpi_cxx that is needed for kombyne. 


### Building openmpi
module load ucx/1.13.1/gnu11.2.1 
./configure --prefix=/ibex/scratch/kressjm/Visualization_Vignettes/software/openmpi-4.1.4-cxx \
            --enable-mpi-cxx \
            --with-slurm \
            --with-pmix=internal \
            --with-libevent=internal \
            --with-hwloc=internal \
            --with-ucx=/sw/rl9c/ucx/1.13.1/rl9_gnu11.2.1
make -j install
export PATH=/ibex/user/kressjm/Visualization_Vignettes/software/openmpi-4.1.4-cxx/bin:$PATH
export LD_LIBRARY_PATH=/ibex/user/kressjm/Visualization_Vignettes/software/openmpi-4.1.4-cxx/lib:$LD_LIBRARY_PATH
module load cmake/3.28.4/gnu-11.3.1


### ParaView
git clone --recursive https://gitlab.kitware.com/paraview/paraview-superbuild.git
cd paraview-superbuild
git checkout v6.0.0
cd ..
mkdir paraview-build
cd paraview-build
ccmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DUSE_SYSTEM_mpi=ON -DUSE_SYSTEM_python3=ON -DENABLE_catalyst=ON -DENABLE_mpi=ON -DENABLE_netcdf=ON -DENABLE_hdf5=ON -DENABLE_python3=ON -DENABLE_openmp=ON  ../paraview-superbuild
make -j

### Ascent
git clone --recursive https://github.com/alpine-dav/ascent.git
cd ascent
env prefix=build env enable_mpi=ON enable_openmp=ON  ./scripts/build_ascent/build_ascent.sh

### ADIOS
git clone [https://github.com/ornladios/ADIOS2.git
mkdir adios2-build
cd adios2-build
cmake ../ADIOS2/ -DADIOS2_USE_MPI=ON -DADIOS2_BUILD_EXAMPLES=ON -DCMAKE_INSTALL_PREFIX=../adios2-install
make -j install
