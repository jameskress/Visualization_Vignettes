#------------------------------------------------------------------------------#
# Distributed under the OSI-approved Apache License, Version 2.0.  See
# accompanying file Copyright.txt for details.
#------------------------------------------------------------------------------#
# 3.12 for object library support with Fortran modules
cmake_minimum_required(VERSION 3.12)
set(CMAKE_CXX_STANDARD 17 CACHE STRING "C++ Standard level to use (17)")
set_property(CACHE CMAKE_CXX_STANDARD PROPERTY STRINGS "17")
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

# Fail immediately if not using an out-of-source build
if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_CURRENT_BINARY_DIR)
  message(FATAL_ERROR
    "In-source builds are not supported.  Please create a build directory "
    "separate from the source directory")
endif()

project(KAUST_Visualization_Vignettes_Miniapp LANGUAGES C CXX VERSION 0.1.0)
option(ENABLE_TIMERS "Timers ON/OFF" OFF)

if(ENABLE_TIMERS)
  add_definitions(-DENABLE_TIMERS)
endif()

#------------------------------------------------------------------------------#
# Common dependencies
#------------------------------------------------------------------------------#
set(_components C CXX)
if(CMAKE_Fortran_COMPILER_LOADED)
  list(APPEND _components Fortran)
endif()

find_package(MPI COMPONENTS ${_components})
if(MPI_FOUND)
  # Workaround for various MPI implementations forcing the link of C++ bindings
  add_definitions(-DOMPI_SKIP_MPICXX -DMPICH_SKIP_MPICXX)

  list(APPEND _components MPI)
endif()

find_package(VTK REQUIRED COMPONENTS IOXML IOParallelXML ParallelMPI FiltersCore)
include_directories(${VTK_INCLUDE_DIRS})
message("vtk include dirs: " ${VTK_INCLUDE_DIRS})

#find_package(ADIOS2 2.7.1 REQUIRED COMPONENTS ${_components})
#find_package(Threads)
find_package(catalyst 2.0 REQUIRED)

#------------------------------------------------------------------------------#
# Top level build options
#------------------------------------------------------------------------------#
# Default to a Release build if not specified
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build." FORCE)
endif()

SET(CMAKE_CXX_FLAGS_DEBUG "-g -rdynamic")

add_executable(kvvm-gray-scott
  simulation/main.cpp
  simulation/gray-scott.cpp
  simulation/settings.cpp
  simulation/writerPVTI.cpp
  simulation/writerCatalyst.cpp
)

target_link_libraries(kvvm-gray-scott PRIVATE MPI::MPI_C ${VTK_LIBRARIES} catalyst::catalyst)

install(TARGETS kvvm-gray-scott
        RUNTIME DESTINATION .)

install(FILES  "configs/miniapp-settings/settings-catalyst-file-io.json"
               "configs/miniapp-settings/settings-catalyst-insitu.json"
               "configs/miniapp-settings/settings-vtk-pvti.json"
               "configs/catalyst_scripts/catalyst-extract-jpg.py"
               "configs/catalyst_scripts/catalyst-extract-contour_v.py"
               "README.md"
        DESTINATION .)
