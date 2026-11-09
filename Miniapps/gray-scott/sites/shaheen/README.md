# Running with Catalyst on a workq node: set the OSMesa window first

The Catalyst implementation in `software/paraview-build` is an EGL build. On a
`workq` node, which has no GPU, its EGL window creation falls into the system
Mesa (`libEGL_mesa` / `libgallium`) and segfaults in `_glapi_add_dispatch` at
the first render, on a handful of ranks, before any image is written (21 Oct
2026, core backtrace). The superbuild also carries OSMesa, so tell VTK to use
its own offscreen window and EGL is never touched:

```bash
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
srun ... ./gray-scott --settings-file=settings.json
```

The simulation alone (`output_type: none`) is unaffected; only the Catalyst
render path needs it. A 256^3 run on one node (64 ranks x 3 threads) with a
JPG every 10 steps is the HPC Saudi 2026 live demo.

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
```bash
cd /scratch/kressjm
module load python
python3 -m venv perf_env
source perf_env/bin/activate
pip install --upgrade pip
pip install pandas numpy matplotlib
```

## Generate the stats
```bash
# reduce_timers.py reads either format: the per-rank writer_timers/*.csv files
# of runs made before #26 (the 2026 WOIV runs), or a newer run's perf/<run>
# directory (steps/rank_*.jsonl). The summary CSV is the same, so
# plot_performance.py works on both. scripts/perf_report.py (README.md,
# Performance) also reads new runs.
python3 reduce_timers.py paper1_func_N0064_baseline/writer_timers summary_baseline.csv
python3 reduce_timers.py paper1_func_N0064_inline_adios_data/writer_timers summary_adios_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_ascent_data/writer_timers summary_ascent_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_ascent_render/writer_timers summary_ascent_render.csv
python3 reduce_timers.py paper1_func_N0064_inline_catalyst_data/writer_timers summary_catalyst_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_catalyst_render/writer_timers summary_catalyst_render.csv
python3 reduce_timers.py paper1_func_N0064_transit_catalyst_render/writer_timers summary_catalyst_intransit_render.csv
python3 reduce_timers.py paper1_func_N0064_transit_ascent_render/writer_timers summary_ascent_intransit_render.csv
python3 reduce_timers.py paper1_func_N0064_inline_kombyne_data/writer_timers summary_kombyne_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_kombyne_render/writer_timers summary_kombyne_render.csv
python3 plot_performance.py
# A run from a current build: pass its perf/<run> directory instead
# (replace <run> with the run directory name, e.g. 20261109-105657_none_np2).
python3 reduce_timers.py paper1_func_N0064_baseline/perf/<run> summary_baseline.csv
```
