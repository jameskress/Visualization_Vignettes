#------------------------------------------------------------------------------#
# Distributed under the OSI-approved Apache License, Version 2.0. See
# accompanying file Copyright.txt for details.
#------------------------------------------------------------------------------#

cmake_minimum_required(VERSION 3.12)

project(KAUST_Visualization_Vignettes_Miniapp
        VERSION 0.1.0
        LANGUAGES C CXX)


# Make sure RPATH is used for installed targets
set(CMAKE_SKIP_BUILD_RPATH FALSE)
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib")
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

#------------------------------------------------------------------------------#
# C++ Standard
#------------------------------------------------------------------------------#
set(CMAKE_CXX_STANDARD 17 CACHE STRING "C++ Standard level to use (17)")
set_property(CACHE CMAKE_CXX_STANDARD PROPERTY STRINGS "17")
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

#------------------------------------------------------------------------------#
# Enforce out-of-source builds
#------------------------------------------------------------------------------#
if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_CURRENT_BINARY_DIR)
  message(FATAL_ERROR
    "In-source builds are not supported. Please create a separate build directory.")
endif()

#------------------------------------------------------------------------------#
# Build Options
#------------------------------------------------------------------------------#
option(ENABLE_TIMERS "Timers ON/OFF" OFF)

if(ENABLE_TIMERS)
  add_definitions(-DENABLE_TIMERS)
endif()

# Default to Release build
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build." FORCE)
endif()

set(CMAKE_CXX_FLAGS_DEBUG "-g -rdynamic")

#------------------------------------------------------------------------------#
# Writer Options
#------------------------------------------------------------------------------#
option(ENABLE_CATALYST "Enable Catalyst writer" OFF)
option(ENABLE_ASCENT "Enable Ascent writer" OFF)
option(ENABLE_ADIOS2 "Enable ADIOS2" OFF)
option(ENABLE_KOMBYNELITE "Enable Kombyne lite in situ writer" OFF)

# --- Check for conflicting in situ library options ---
set(INSITU_LIBRARIES_ENABLED 0)
if(ENABLE_ASCENT)
  math(EXPR INSITU_LIBRARIES_ENABLED "${INSITU_LIBRARIES_ENABLED}+1")
endif()
if(ENABLE_KOMBYNELITE)
  math(EXPR INSITU_LIBRARIES_ENABLED "${INSITU_LIBRARIES_ENABLED}+1")
endif()

if(INSITU_LIBRARIES_ENABLED GREATER 1)
  message(FATAL_ERROR "Ascent and Kombyne cannot be enabled at the same time due to conflicting dependencies (Conduit). Please enable only one.")
endif()

# Define preprocessor macros based on CMake options
if(ENABLE_CATALYST)
  add_definitions(-DUSE_CATALYST)
endif()

if(ENABLE_ASCENT)
  add_definitions(-DUSE_ASCENT)
endif()

if(ENABLE_ADIOS2)
  add_definitions(-DUSE_ADIOS2)
endif()

if(ENABLE_KOMBYNELITE)
  add_definitions(-DUSE_KOMBYNE)
endif()

#------------------------------------------------------------------------------#
# Dependencies
#------------------------------------------------------------------------------#

# MPI
set(_components C CXX)
if(CMAKE_Fortran_COMPILER_LOADED)
  list(APPEND _components Fortran)
endif()

find_package(MPI COMPONENTS ${_components})

if(MPI_FOUND)
  add_definitions(-DOMPI_SKIP_MPICXX -DMPICH_SKIP_MPICXX)
  list(APPEND _components MPI)
endif()

# VTK (Required)
find_package(VTK REQUIRED COMPONENTS
  CommonCore
  IOXML
  IOParallelXML
  ParallelMPI
  FiltersCore
)

if(NOT VTK_FOUND)
  message(FATAL_ERROR "VTK not found. Set VTK_DIR to the installation directory.")
endif()

# Catalyst (Optional)
if(ENABLE_CATALYST)
  find_package(catalyst 2.0 REQUIRED)

  if(NOT catalyst_FOUND)
    
  endif()

  message(STATUS "Catalyst writer enabled.")
endif()

# Ascent (Optional)
if(ENABLE_ASCENT)
  find_package(Ascent REQUIRED)
  find_package(Conduit REQUIRED)

  if(NOT ASCENT_VERSION)
    message(FATAL_ERROR "Ascent not found. Set Ascent_DIR to the installation directory.")
  endif()

  message(STATUS "Ascent writer enabled.")
endif()

# ADIOS2 (Optional)
if(ENABLE_ADIOS2)
  find_package(ADIOS2 REQUIRED)

  if(ADIOS2_FOUND)
      message(STATUS "Found ADIOS2 version ${ADIOS2_VERSION}. Enabling ADIOS2 features.")
  else()
      message(FATAL_ERROR "ADIOS2 not found. Set ADIOS2_DIR to the installation directory.")
  endif()

  message(STATUS "ADIOS2 enabled.")
endif()


# Kombyne (Optional)
if(ENABLE_KOMBYNELITE)
  find_package(kombynelite REQUIRED)

  if(kombynelite_FOUND)
    message(STATUS "Kombyne lite found: kombynelite")
  else()
    message(FATAL_ERROR "Kombyne lite not found. Set kombynelite_DIR to the installation directory.")
  endif()

  message(STATUS "Kombyne lite enabled.")
endif()

#------------------------------------------------------------------------------#
# Executable and Sources
#------------------------------------------------------------------------------#
set(SRC_FILES
  simulation/main.cpp
  simulation/gray-scott.cpp
  simulation/settings.cpp
  simulation/writerPVTI.cpp
)

if(ENABLE_CATALYST)
  list(APPEND SRC_FILES simulation/writerCatalyst.cpp)
endif()

if(ENABLE_ASCENT)
  list(APPEND SRC_FILES simulation/writerAscent.cpp)
endif()

if(ENABLE_ADIOS2)
  list(APPEND SRC_FILES simulation/restart.cpp)
  list(APPEND SRC_FILES simulation/writerADIOS.cpp)
endif()

if(ENABLE_KOMBYNELITE)
  list(APPEND SRC_FILES simulation/writerKombyne.cpp)
endif()

add_executable(kvvm-gray-scott ${SRC_FILES})

#------------------------------------------------------------------------------#
# Linking
#------------------------------------------------------------------------------#
target_link_libraries(kvvm-gray-scott PRIVATE
  MPI::MPI_C
  ${VTK_LIBRARIES}
)

target_include_directories(kvvm-gray-scott PRIVATE
  ${VTK_INCLUDE_DIRS}
)

if(ENABLE_CATALYST)
  target_link_libraries(kvvm-gray-scott PRIVATE catalyst::catalyst)
endif()

if(ENABLE_ASCENT)
  target_link_libraries(kvvm-gray-scott PRIVATE
    ascent::ascent_mpi
    conduit::conduit_mpi
  )
endif()

if(ENABLE_ADIOS2)
  target_link_libraries(kvvm-gray-scott PRIVATE adios2::cxx11_mpi)
endif()

if(ENABLE_KOMBYNELITE)
  target_link_libraries(kvvm-gray-scott PRIVATE kombynelite)
endif()

#------------------------------------------------------------------------------#
# Install Rules
#------------------------------------------------------------------------------#
install(TARGETS kvvm-gray-scott
        RUNTIME DESTINATION .)

# Install config files and scripts from their respective directories.
# The trailing slash on the directory path ensures the *contents* of the
# directory are installed, not the directory itself.
install(DIRECTORY configs/miniapp-settings/
        DESTINATION .
        FILES_MATCHING PATTERN "*.json")

install(DIRECTORY configs/catalyst_scripts/
        DESTINATION .
        FILES_MATCHING PATTERN "*.py")

install(DIRECTORY configs/ascent_scripts/
        DESTINATION .
        FILES_MATCHING PATTERN "*.yaml")

# Use OPTIONAL in case these directories don't exist yet.
install(DIRECTORY configs/kombyne_scripts/
        DESTINATION .
        FILES_MATCHING PATTERN "*.yaml"
        OPTIONAL)

install(DIRECTORY configs/adios2_configs/
        DESTINATION .
        FILES_MATCHING PATTERN "*.xml"
        OPTIONAL)

# Install miscellaneous top-level files that aren't in a subdirectory.
install(FILES
  configs/cleanupRun.sh
  README.md
  DESTINATION .