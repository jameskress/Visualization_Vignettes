# Building Ascent
Ascent was not properly passing the `cc` and `CC` compiler wrappers to all of its sub builds. Below is what worked on the last build. 

***!! NOTE !!*** Compiler paths will have to be updated as the cray environment changes.

```bash
git clone --recursive https://github.com/alpine-dav/ascent.git
cd ascent

cat > shaheen-host-config.cmake << EOL
# shaheen-host-config.cmake

# Forcefully add the C++17 standard flag to the compiler flags.
# This is more direct than CMAKE_CXX_STANDARD and harder for Umpire to ignore.
set(CMAKE_CXX_FLAGS "\${CMAKE_CXX_FLAGS} -std=c++17" CACHE STRING "C++ Compiler Flags" FORCE)

# Also add the filesystem library to the linker flags for good measure.
set(CMAKE_EXE_LINKER_FLAGS "\${CMAKE_EXE_LINKER_FLAGS} -lstdc++fs" CACHE STRING "Linker Flags" FORCE)
EOL

export CC=/opt/cray/pe/craype/2.7.32/bin/cc
export CXX=/opt/cray/pe/craype/2.7.32/bin/CC

env prefix=build enable_mpi=ON enable_openmp=ON \
    ./scripts/build_ascent/build_ascent.sh -H shaheen-host-config.cmake
```

# ADIOS2
ADIOS worked following the README instructions.



# Performance scripts

## Creating python environment
cd /scratch/kressjm
module load python
python3 -m venv perf_env
source perf_env/bin/activate
pip install --upgrade pip
pip install pandas numpy matplotlib

## Generate the stats
python3 /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/sites/shaheen/2026-WOIV-scripts/reduce_timers.py writer_timers/ summary_baseline.csv
python3 plot_performance.py
