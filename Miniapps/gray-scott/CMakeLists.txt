#------------------------------------------------------------------------------#
# Distributed under the OSI-approved Apache License, Version 2.0. See
# accompanying file Copyright.txt for details.
#------------------------------------------------------------------------------#

cmake_minimum_required(VERSION 3.22)

project(Visualization_Vignettes_Miniapp
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
option(ENABLE_GPU "Enable GPU execution (no effect yet; organizes the GPU work in phase 4, #38)" OFF)
if(ENABLE_GPU)
  message(STATUS "ENABLE_GPU is ON but no GPU code exists yet; building the CPU version.")
endif()
option(BUILD_ANALYSIS_READER "Build the in-situ analysis reader" OFF)

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
  find_package(ADIOS2 REQUIRED COMPONENTS MPI)

  if(ADIOS2_FOUND)
      message(STATUS "Found ADIOS2 version ${ADIOS2_VERSION}.")
    
      if(ADIOS2_MPI_FOUND)
        message(STATUS "ADIOS2 MPI support: ENABLED")
      else()
        message(WARNING "ADIOS2 MPI support: DISABLED. The 'mpi' DataPlane will be unavailable.")
      endif()

  else()
      message(FATAL_ERROR "ADIOS2 not found. Set ADIOS2_DIR to the installation directory.")
  endif()

  message(STATUS "ADIOS2 features enabled.")
endif()


# Kombyne (Optional)
if(ENABLE_KOMBYNELITE)
  find_package(kombynelite REQUIRED)
  
  if(kombynelite_FOUND)
    message(STATUS "Kombyne lite found config at: ${kombynelite_DIR}")

    # 1. Calculate the installation root
    # kombynelite_DIR is likely .../lib/cmake/kombynelite
    # We need to go up 3 levels to get to the base folder
    get_filename_component(KOMBYNE_INSTALL_ROOT "${kombynelite_DIR}/../../.." ABSOLUTE)
    
    message(STATUS "Kombyne Install Root: ${KOMBYNE_INSTALL_ROOT}")

    # 2. Manually define the Bundled Conduit Libraries
    # Order matters for static linking! 
    # Usually: Relay -> Blueprint -> Conduit
    set(KOMBYNE_BUNDLED_LIBS 
        "${KOMBYNE_INSTALL_ROOT}/lib/libconduit_relay.a"
        "${KOMBYNE_INSTALL_ROOT}/lib/libconduit_blueprint.a"
        "${KOMBYNE_INSTALL_ROOT}/lib/libconduit.a"
    )

    # 3. Add the include directory so we can find conduit headers
    include_directories("${KOMBYNE_INSTALL_ROOT}/include")

  else()
    message(FATAL_ERROR "Kombyne lite not found. Set kombynelite_DIR.")
  endif()

  message(STATUS "Kombyne lite enabled with bundled Conduit.")
endif()

#------------------------------------------------------------------------------#
# Common Library: PerfLogger and run metadata (README.md, Performance)
#------------------------------------------------------------------------------#
# gs_build_info.h records the git commit, dirty state, compiler and flags in
# every run's metadata.json. It is regenerated on every build so it never
# describes an older tree; it is rewritten only when its contents change.
set(GS_GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
string(TOUPPER "${CMAKE_BUILD_TYPE}" _gs_bt)
string(STRIP "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${_gs_bt}}" _gs_flags)
set(_gs_backends "pvti")
foreach(_b CATALYST ASCENT ADIOS2 KOMBYNELITE)
  if(ENABLE_${_b})
    string(TOLOWER "${_b}" _bl)
    string(APPEND _gs_backends ",${_bl}")
  endif()
endforeach()
add_custom_target(gs_build_info
  COMMAND ${CMAKE_COMMAND}
          -DSRC_DIR=${CMAKE_CURRENT_SOURCE_DIR}
          -DOUT_FILE=${GS_GENERATED_DIR}/gs_build_info.h
          -DTEMPLATE=${CMAKE_CURRENT_SOURCE_DIR}/cmake/gs_build_info.h.in
          -DGS_CXX_COMPILER=${CMAKE_CXX_COMPILER}
          -DGS_CXX_COMPILER_ID=${CMAKE_CXX_COMPILER_ID}
          -DGS_CXX_COMPILER_VERSION=${CMAKE_CXX_COMPILER_VERSION}
          "-DGS_CXX_FLAGS=${_gs_flags}"
          -DGS_BUILD_TYPE=${CMAKE_BUILD_TYPE}
          -DGS_ENABLED_BACKENDS=${_gs_backends}
          -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/gs_build_info.cmake
  BYPRODUCTS ${GS_GENERATED_DIR}/gs_build_info.h
  VERBATIM
  COMMENT "Recording git state and compiler settings for run metadata")

add_library(common common/perf_logger.cpp common/run_metadata.cpp common/alloc_count_weak.cpp)
add_dependencies(common gs_build_info)
target_include_directories(common PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
                                  PRIVATE ${GS_GENERATED_DIR})
target_link_libraries(common PUBLIC MPI::MPI_C)

if(ENABLE_TIMERS)
  # Any target that links common inherits this definition.
  target_compile_definitions(common PUBLIC ENABLE_TIMERS)
  message(STATUS "Performance Timers are ENABLED")
endif()

#------------------------------------------------------------------------------#
# Executable and Sources
#------------------------------------------------------------------------------#
# The simulation core (solver, halo exchange, settings) is a library so the
# numerical regression test in tests/ links the same code the miniapp runs.
# It depends on MPI only; the writers and their SDKs stay in the executable.
add_library(gray-scott-core STATIC
  simulation/gray-scott.cpp
  simulation/settings.cpp
)
target_include_directories(gray-scott-core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/simulation
)
target_link_libraries(gray-scott-core PUBLIC MPI::MPI_C)

set(SRC_FILES
  simulation/main.cpp
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

# Test-only allocation counter (#25): replaces the global allocation
# functions in the executable so the performance log can report heap
# allocations per step. Off by default; never use it for timing runs.
option(GS_COUNT_ALLOCATIONS "Count heap allocations per step (test builds only)" OFF)
# The counter wraps malloc through glibc's __libc_* entry points.
# The counts reach the performance log only through the timer build.
if(GS_COUNT_ALLOCATIONS AND NOT ENABLE_TIMERS)
  message(FATAL_ERROR "GS_COUNT_ALLOCATIONS needs ENABLE_TIMERS=ON; without timers the counts are not logged")
endif()
if(GS_COUNT_ALLOCATIONS AND NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
  message(FATAL_ERROR "GS_COUNT_ALLOCATIONS needs Linux with glibc (it wraps __libc_malloc and friends)")
endif()
if(GS_COUNT_ALLOCATIONS)
  list(APPEND SRC_FILES common/alloc_counter.cpp)
  message(STATUS "Allocation counter is ENABLED (test build, not for timing)")
endif()

add_executable(gray-scott ${SRC_FILES})

#------------------------------------------------------------------------------#
# Linking
#------------------------------------------------------------------------------#
target_link_libraries(gray-scott PRIVATE
  gray-scott-core
  common
  MPI::MPI_C
  ${VTK_LIBRARIES}
)

target_include_directories(gray-scott PRIVATE
  ${VTK_INCLUDE_DIRS}
)

if(ENABLE_CATALYST)
  target_link_libraries(gray-scott PRIVATE catalyst::catalyst)
endif()

if(ENABLE_ASCENT)
  target_link_libraries(gray-scott PRIVATE
    ascent::ascent_mpi
    conduit::conduit_mpi
  )
endif()

if(ENABLE_ADIOS2)
  target_link_libraries(gray-scott PRIVATE adios2::cxx11_mpi)
endif()

if(ENABLE_KOMBYNELITE)
  target_link_libraries(gray-scott PRIVATE 
      kombynelite
      ${KOMBYNE_BUNDLED_LIBS}
      MPI::MPI_CXX          
  )

  target_link_options(gray-scott PRIVATE "-Wl,--allow-shlib-undefined")
  # For the run metadata; the package config may not set a version.
  if(NOT kombynelite_VERSION)
    set(kombynelite_VERSION "unknown")
  endif()
  target_compile_definitions(gray-scott PRIVATE GS_KOMBYNE_VERSION="${kombynelite_VERSION}")
endif()


#------------------------------------------------------------------------------#
# Analysis Reader (Optional)
#------------------------------------------------------------------------------#
if(BUILD_ANALYSIS_READER)
  # The reader requires both ADIOS2 and Ascent to be enabled.
  if(NOT ENABLE_ADIOS2 OR NOT ENABLE_ASCENT)
    message(FATAL_ERROR "BUILD_ANALYSIS_READER requires both ENABLE_ADIOS2 and ENABLE_ASCENT to be ON.")
  endif()
  add_subdirectory(analysis)
endif()


#------------------------------------------------------------------------------#
# Tests (CTest)
#------------------------------------------------------------------------------#
option(GS_BUILD_TESTS "Build the numerical regression tests (run with ctest)" ON)
if(GS_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()


#------------------------------------------------------------------------------#
# Install Rules
#------------------------------------------------------------------------------#
install(TARGETS gray-scott
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

install(DIRECTORY configs/kombyne_scripts/
        DESTINATION .
        FILES_MATCHING PATTERN "*.yaml")

install(DIRECTORY configs/adios2_configs/
        DESTINATION .
        FILES_MATCHING PATTERN "*.xml")

# Install script files
install(DIRECTORY scripts/
        DESTINATION .
        FILES_MATCHING 
        PATTERN "*.py"
        PATTERN "*.sh")

# Install miscellaneous top-level files that aren't in a subdirectory.
install(FILES
  README.md
  DESTINATION .
)
# The README links to the detailed guide under docs/, and the guide shows
# the pattern images under img/; install both at the same relative paths.
install(FILES docs/build-and-run-guide.md docs/in-situ-backends.md DESTINATION docs)
install(DIRECTORY img/ DESTINATION img FILES_MATCHING PATTERN "*.jpg")
