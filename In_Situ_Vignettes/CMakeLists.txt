#------------------------------------------------------------------------------#
# Visualization Vignettes -- In Situ Vignettes
#
# Standalone build tree. It deliberately does NOT depend on the gray-scott
# miniapp: a vignette that needs the miniapp to compile cannot be used to
# debug the miniapp. Vignettes that want simulation-shaped data get it from
# common/insitu_harness.h instead.
#
# Configure:
#   cmake -S In_Situ_Vignettes -B build-insitu \
#         -DConduit_DIR=/opt/ascent/install/conduit-v0.9.2/lib/cmake/conduit \
#         -DAscent_DIR=/opt/ascent/install/ascent-checkout/lib/cmake/ascent \
#         -Dcatalyst_DIR=/opt/paraview/lib/cmake/catalyst-2.0
#   cmake --build build-insitu -j
#   ctest --test-dir build-insitu --output-on-failure
#------------------------------------------------------------------------------#
cmake_minimum_required(VERSION 3.16)

project(Visualization_Vignettes_InSitu
        VERSION 0.1.0
        LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE "RelWithDebInfo" CACHE STRING "Build type" FORCE)
endif()

if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_CURRENT_BINARY_DIR)
  message(FATAL_ERROR "In-source builds are not supported.")
endif()

include(CTest)

#------------------------------------------------------------------------------#
# Options
#------------------------------------------------------------------------------#
option(INSITU_ENABLE_ASCENT   "Build vignettes that drive Ascent"   OFF)
option(INSITU_ENABLE_CATALYST "Build vignettes that drive Catalyst" OFF)
option(INSITU_ENABLE_ADIOS2   "Build in-transit (SST) vignettes"    OFF)
option(INSITU_ENABLE_ASAN     "Build with AddressSanitizer + UBSan" OFF)

#------------------------------------------------------------------------------#
# Dependencies
#------------------------------------------------------------------------------#
find_package(MPI REQUIRED COMPONENTS C CXX)

# Conduit is the common currency: Ascent and ParaView-Catalyst both ship it,
# and every vignette speaks Blueprint. Ascent re-exports it, so accept either.
find_package(Conduit QUIET)
if(NOT Conduit_FOUND AND INSITU_ENABLE_ASCENT)
  find_package(Ascent REQUIRED)
endif()
if(NOT Conduit_FOUND AND NOT TARGET conduit::conduit)
  find_package(Conduit REQUIRED)
endif()

if(INSITU_ENABLE_ASCENT)
  find_package(Ascent REQUIRED)
endif()

if(INSITU_ENABLE_CATALYST)
  find_package(catalyst 2.0 REQUIRED)
endif()

if(INSITU_ENABLE_ADIOS2)
  find_package(ADIOS2 REQUIRED COMPONENTS MPI)
endif()

#------------------------------------------------------------------------------#
# Shared harness (header-only)
#------------------------------------------------------------------------------#
add_library(insitu_common INTERFACE)
target_include_directories(insitu_common INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/common)
target_link_libraries(insitu_common INTERFACE MPI::MPI_CXX)

if(INSITU_ENABLE_ASAN)
  target_compile_options(insitu_common INTERFACE
    -fsanitize=address,undefined -fno-omit-frame-pointer -g)
  target_link_options(insitu_common INTERFACE -fsanitize=address,undefined)
  message(STATUS "AddressSanitizer + UBSan ENABLED")
endif()

#------------------------------------------------------------------------------#
# Helper: register a vignette as one or more CTest cases.
#
# Every vignette is expected to exit non-zero on failure. That is the whole
# contract -- no baseline diffing, no log scraping, no "the harness only
# checks the text file" gap that lets image regressions through unnoticed.
#------------------------------------------------------------------------------#
function(add_insitu_vignette NAME)
  cmake_parse_arguments(V "" "" "SOURCES;LIBS;RANKS;ARGS" ${ARGN})

  add_executable(${NAME} ${V_SOURCES})
  target_link_libraries(${NAME} PRIVATE insitu_common ${V_LIBS})
  install(TARGETS ${NAME} RUNTIME DESTINATION .)

  if(NOT V_RANKS)
    set(V_RANKS 1)
  endif()

  foreach(NP IN LISTS V_RANKS)
    add_test(NAME ${NAME}.np${NP}
             COMMAND ${MPIEXEC_EXECUTABLE} ${MPIEXEC_NUMPROC_FLAG} ${NP}
                     ${MPIEXEC_PREFLAGS} $<TARGET_FILE:${NAME}>
                     ${MPIEXEC_POSTFLAGS} ${V_ARGS})
    set_tests_properties(${NAME}.np${NP} PROPERTIES
      TIMEOUT 600
      PROCESSORS ${NP}
      FAIL_REGULAR_EXPRESSION "FAIL;CHECK\\(S\\) FAILED")
  endforeach()
endfunction()

#------------------------------------------------------------------------------#
# Vignettes
#------------------------------------------------------------------------------#
add_subdirectory(is00_zeroCopyAdapter)

# Scheduled -- see In_Situ_Vignettes/README.md for the specification of each.
# add_subdirectory(is01_ghostCorrectness)
# add_subdirectory(is02_thresholdTrigger)
# add_subdirectory(is03_inTransitFailover)
# add_subdirectory(is04_liveSteering)

message(STATUS "")
message(STATUS "In Situ Vignettes configuration:")
message(STATUS "  Ascent   : ${INSITU_ENABLE_ASCENT}")
message(STATUS "  Catalyst : ${INSITU_ENABLE_CATALYST}")
message(STATUS "  ADIOS2   : ${INSITU_ENABLE_ADIOS2}")
message(STATUS "  Sanitizer: ${INSITU_ENABLE_ASAN}")
message(STATUS "")
