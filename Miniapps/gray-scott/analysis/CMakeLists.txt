cmake_minimum_required(VERSION 3.12)
project(GrayScottAnalysisReader)

# C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Fetch nlohmann_json automatically
include(FetchContent)
FetchContent_Declare(
  nlohmann_json
  GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG "v3.11.3"
)
FetchContent_MakeAvailable(nlohmann_json)

# Find dependencies
find_package(MPI REQUIRED)
# The top-level CMakeLists.txt has usually found ADIOS2 already, and ADIOS2
# 2.11's config fails if asked twice ("imported target adios2::cxx11 already
# exists"), so look only when this directory is built on its own.
if(NOT TARGET adios2::cxx11_mpi)
  find_package(ADIOS2 REQUIRED COMPONENTS MPI)
endif()
find_package(Conduit REQUIRED)
find_package(Ascent REQUIRED)
#find_package(Viskores REQUIRED)
#find_package(Fides REQUIRED)

# Extend Fides to include rapidjson
#get_target_property(FIDES_INCLUDE_DIR fides INTERFACE_INCLUDE_DIRECTORIES)
#target_include_directories(fides INTERFACE
#  ${FIDES_INCLUDE_DIR}/fides/thirdparty/rapidjson
#)

# Create the executable
add_executable(analysis-reader
  main.cpp
  adios_reader.cpp
  ascent_backend.cpp
  adios_writer_backend.cpp
  readonly_backend.cpp
  backend_factory.cpp
)

# The reader's library path is a DT_RPATH by default, which the dynamic
# loader searches before LD_LIBRARY_PATH. GS_READER_RUNPATH writes a
# DT_RUNPATH instead, searched after LD_LIBRARY_PATH, so a job can load
# ParaView from a node-local copy put first on LD_LIBRARY_PATH
# (generate_experiments.py --catalyst-stage). Off by default; turn it on only
# in builds used with staging.
option(GS_READER_RUNPATH "Link analysis-reader with DT_RUNPATH (LD_LIBRARY_PATH wins) instead of DT_RPATH" OFF)
if(GS_READER_RUNPATH)
  target_link_options(analysis-reader PRIVATE "-Wl,--enable-new-dtags")
else()
  target_link_options(analysis-reader PRIVATE "-Wl,--disable-new-dtags")
endif()

# Include directories from targets
target_include_directories(analysis-reader PRIVATE
  ${MPI_INCLUDE_PATH}
  ${ADIOS2_INCLUDE_DIRS}
  ${Conduit_INCLUDE_DIRS}
  ${Ascent_INCLUDE_DIRS}
#  ${Viskores_INCLUDE_DIRS}
#  ${Fides_INCLUDE_DIRS}
)

#if (NOT Viskores::ENABLE::RENDERING)
#  message(FATAL_ERROR "Viskores must be built with rendering on.")
#endif()

# Viskores libraries
#set(VISKORES_LIBS viskores::cont viskores::filter viskores::io)

# Link all dependencies
target_link_libraries(analysis-reader PRIVATE
  common
  MPI::MPI_CXX
  adios2::cxx11_mpi
  conduit::conduit_mpi
  ascent::ascent_mpi
  nlohmann_json::nlohmann_json
#  ${VISKORES_LIBS}
#  fides
)

# Optional Catalyst
if(ENABLE_CATALYST)
  target_sources(analysis-reader PRIVATE catalyst_backend.cpp)
  target_include_directories(analysis-reader PRIVATE ${catalyst_INCLUDE_DIRS})
  target_link_libraries(analysis-reader PRIVATE catalyst::catalyst)
endif()

# Install
install(TARGETS analysis-reader RUNTIME DESTINATION .)

# Install miscellaneous top-level files that aren't in a subdirectory.
install(FILES
  DESTINATION .
)
