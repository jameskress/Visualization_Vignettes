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
find_package(ADIOS2 REQUIRED COMPONENTS MPI)
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
  backend_factory.cpp
)

target_link_options(analysis-reader PRIVATE "-Wl,--disable-new-dtags")

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