#------------------------------------------------------------------------------#
# Distributed under the OSI-approved Apache License, Version 2.0.  See
# accompanying file Copyright.txt for details.
#------------------------------------------------------------------------------#
# 3.12 for object library support with Fortran modules
cmake_minimum_required(VERSION 3.12)

# Fail immediately if not using an out-of-source build
if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_CURRENT_BINARY_DIR)
  message(FATAL_ERROR
    "In-source builds are not supported.  Please create a build directory "
    "separate from the source directory")
endif()

project(KAUST_Visualization_Vignettes_Miniapp LANGUAGES C CXX VERSION 0.1.0)


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

#find_package(ADIOS2 2.7.1 REQUIRED COMPONENTS ${_components})

find_package(Threads)

#------------------------------------------------------------------------------#
# Top level build options
#------------------------------------------------------------------------------#

# Default to a Release build if not specified
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build." FORCE)
endif()

set(CMAKE_CXX_STANDARD 11 CACHE STRING "C++ Standard level to use (11)")
set_property(CACHE CMAKE_CXX_STANDARD PROPERTY STRINGS "11;17")
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)


find_package(VTK REQUIRED)
include_directories(${VTK_INCLUDE_DIRS})
  
  
add_executable(kvvm-gray-scott
  simulation/main.cpp
  simulation/gray-scott.cpp
  simulation/settings.cpp
  simulation/writer.cpp
)
target_link_libraries(kvvm-gray-scott MPI::MPI_C ${VTK_LIBRARIES})
install(TARGETS kvvm-gray-scott 
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})

#add_executable(adios2-pdf-calc analysis/pdf-calc.cpp)
#target_link_libraries(adios2-pdf-calc MPI::MPI_C)
install(FILES "adios2.xml" "adios2-inline-plugin.xml" "adios2-fides-staging.xml"
                           "visit-bp4.session" "visit-bp4.session.gui" 
                           "visit-sst.session" "visit-sst.session.gui"                  
                           "simulation/settings-files.json"
                           "simulation/settings-staging.json"
                           "simulation/settings-inline.json"
                           "plot/decomp.py" "plot/gsplot.py" "plot/pdfplot.py"
                           "README.md" 
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/adios2-examples/gray-scott) 

install(DIRECTORY "catalyst"
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/adios2-examples/gray-scott) 


install(PROGRAMS "cleanup.sh" 
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/adios2-examples/gray-scott) 

