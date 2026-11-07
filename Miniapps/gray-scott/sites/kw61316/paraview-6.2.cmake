# ParaView 6.2 superbuild for the KVL workstation (KW61316), as built on 2026-11-07 (#19).
#
# The miniapp links VTK and Catalyst from this build, and Catalyst loads the same
# ParaView at run time, so there is only one VTK in the process.
#
# Needs CMake 3.25 or newer (the system has 3.22.1): CMake 3.31.9 lives under
# ~/packages/cmake-3.31.9-linux-x86_64. Use with the v6.2.0 tag of
# paraview-superbuild (a worktree, submodules initialized):
#
#   git -C ~/packages/paraview-src/paraview-superbuild worktree add ../superbuild-v6.2.0 v6.2.0
#   git -C ~/packages/paraview-src/superbuild-v6.2.0 submodule update --init
#   mkdir ~/packages/paraview-src/build_6.2.0 && cd ~/packages/paraview-src/build_6.2.0
#   ~/packages/cmake-3.31.9-linux-x86_64/bin/cmake -G Ninja \
#       -C <repo>/Miniapps/gray-scott/sites/kw61316/paraview-6.2.cmake \
#       ~/packages/paraview-src/superbuild-v6.2.0
#   ninja -j 48          # about 12 minutes on the workstation
#
# Result: ~/packages/paraview-src/build_6.2.0/install (760 MB), with
#   lib/cmake/paraview-6.2/vtk   (VTK_DIR for the miniapp)
#   lib/cmake/catalyst-2.0       (catalyst_DIR)
#   lib/catalyst                 (catalyst_lib_path / CATALYST_IMPLEMENTATION_PATHS)

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "")
set(paraview_SOURCE_SELECTION "6.2.0" CACHE STRING "")
set(PARAVIEW_BUILD_EDITION "CANONICAL" CACHE STRING "")
set(SUPERBUILD_DEFAULT_INSTALL "paraview/TGZ" CACHE STRING "")
set(BUILD_TESTING OFF CACHE BOOL "")

set(ENABLE_paraview ON CACHE BOOL "")
set(ENABLE_catalyst ON CACHE BOOL "")
set(ENABLE_mpi ON CACHE BOOL "")
set(USE_SYSTEM_mpi ON CACHE BOOL "")          # Open MPI 4.1.2, same as the miniapp
set(ENABLE_python3 ON CACHE BOOL "")
set(USE_SYSTEM_python3 ON CACHE BOOL "")
set(Python3_EXECUTABLE "/usr/bin/python3" CACHE FILEPATH "")   # 3.10, has headers; another 3.12 on PATH does not
set(ENABLE_hdf5 ON CACHE BOOL "")
set(ENABLE_netcdf ON CACHE BOOL "")
set(ENABLE_nlohmannjson ON CACHE BOOL "")
set(ENABLE_openmp ON CACHE BOOL "")
set(ENABLE_cxx11 ON CACHE BOOL "")
