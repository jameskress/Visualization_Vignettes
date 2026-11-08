# Numerical regression test for the simulation core (issue #15).
# Run from the build directory:  ctest --output-on-failure

add_executable(test_numerical_regression test_numerical_regression.cpp)
target_link_libraries(test_numerical_regression PRIVATE gray-scott-core)

set(GS_GOLDEN ${CMAKE_CURRENT_SOURCE_DIR}/golden/regression_L64_s500.txt)

# Extra mpiexec flags, e.g. --oversubscribe on a machine with fewer than 4 cores.
set(GS_TEST_MPIEXEC_PREFLAGS "" CACHE STRING "Extra flags placed before the test executable in mpiexec")
separate_arguments(_gs_preflags UNIX_COMMAND "${GS_TEST_MPIEXEC_PREFLAGS}")

set(_gs_hashes "")
foreach(np 1 2 4)
  set(_hash ${CMAKE_CURRENT_BINARY_DIR}/regression_hash_np${np}.txt)
  list(APPEND _gs_hashes ${_hash})
  add_test(NAME gs_regression_np${np}
    COMMAND ${MPIEXEC_EXECUTABLE} ${MPIEXEC_NUMPROC_FLAG} ${np} ${MPIEXEC_PREFLAGS} ${_gs_preflags}
            $<TARGET_FILE:test_numerical_regression> ${MPIEXEC_POSTFLAGS}
            --golden=${GS_GOLDEN} --hash-out=${_hash})
  set_tests_properties(gs_regression_np${np} PROPERTIES
    PROCESSORS ${np}
    TIMEOUT 300
    FIXTURES_SETUP gs_regression_hashes
    PASS_REGULAR_EXPRESSION "PASSED")
endforeach()

# Bitwise equivalence across rank counts: all three hash files must match.
add_test(NAME gs_regression_bitwise_1_2_4
  COMMAND ${CMAKE_COMMAND} "-DHASH_FILES=${_gs_hashes}"
          -P ${CMAKE_CURRENT_SOURCE_DIR}/compare_hashes.cmake)
set_tests_properties(gs_regression_bitwise_1_2_4 PROPERTIES
  FIXTURES_REQUIRED gs_regression_hashes)

# Backend ghost volume test (#24): every enabled backend counts the cells
# with u <= 0.3 at step 100 on 1, 2, 4 and 8 ranks; counts must match across
# rank counts and across backends. Needs Python 3, and pvpython for the
# readers of PVTI and Kombyne output, bpls for ADIOS2. CI builds no backends,
# so none of these tests exist there.
find_package(Python3 COMPONENTS Interpreter QUIET)
set(GS_PVPYTHON "" CACHE FILEPATH "pvpython used to read PVTI and Kombyne output in the ghost volume test")
if(NOT GS_PVPYTHON)
  find_program(GS_PVPYTHON_FOUND pvpython)
  if(GS_PVPYTHON_FOUND)
    set(GS_PVPYTHON ${GS_PVPYTHON_FOUND})
  endif()
endif()
set(_gs_gv_dir ${CMAKE_CURRENT_BINARY_DIR}/ghost_volume)
set(_gs_gv ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/ghost_volume/ghost_volume.py
           --exe $<TARGET_FILE:gray-scott> --workdir ${_gs_gv_dir}
           --mpiexec ${MPIEXEC_EXECUTABLE} "--mpiexec-preflags=${GS_TEST_MPIEXEC_PREFLAGS}")
set(_gs_gv_backends "")
if(Python3_Interpreter_FOUND)
  if(ENABLE_CATALYST)
    get_filename_component(_cat_impl "${catalyst_DIR}/../../catalyst" ABSOLUTE)
    set(GS_CATALYST_IMPLEMENTATION_DIR "${_cat_impl}" CACHE PATH "Directory holding libcatalyst-paraview.so")
    add_test(NAME gs_ghost_volume_catalyst
      COMMAND ${_gs_gv} --backend catalyst --catalyst-lib ${GS_CATALYST_IMPLEMENTATION_DIR})
    list(APPEND _gs_gv_backends catalyst)
  endif()
  if(ENABLE_ASCENT)
    # Counts Ascent's own threshold extract with h5py.
    execute_process(COMMAND ${Python3_EXECUTABLE} -c "import h5py" RESULT_VARIABLE _gs_no_h5py OUTPUT_QUIET ERROR_QUIET)
    if(_gs_no_h5py EQUAL 0)
      add_test(NAME gs_ghost_volume_ascent COMMAND ${_gs_gv} --backend ascent)
      list(APPEND _gs_gv_backends ascent)
    else()
      message(STATUS "Ghost volume test: no h5py for ${Python3_EXECUTABLE}; Ascent skipped")
    endif()
  endif()
  if(GS_PVPYTHON)
    add_test(NAME gs_ghost_volume_pvti COMMAND ${_gs_gv} --backend pvti --pvpython ${GS_PVPYTHON})
    list(APPEND _gs_gv_backends pvti)
    if(ENABLE_KOMBYNELITE)
      add_test(NAME gs_ghost_volume_kombyne COMMAND ${_gs_gv} --backend kombyne --pvpython ${GS_PVPYTHON})
      list(APPEND _gs_gv_backends kombyne)
    endif()
  endif()
  if(ENABLE_ADIOS2)
    find_program(GS_BPLS bpls HINTS ${ADIOS2_DIR}/../../../bin)
    if(GS_BPLS)
      add_test(NAME gs_ghost_volume_adios COMMAND ${_gs_gv} --backend adios --bpls ${GS_BPLS})
      list(APPEND _gs_gv_backends adios)
    endif()
  endif()
endif()
foreach(b IN LISTS _gs_gv_backends)
  set_tests_properties(gs_ghost_volume_${b} PROPERTIES
    LABELS backends TIMEOUT 1800 PROCESSORS 8 RESOURCE_LOCK gs_ghost_volume
    FIXTURES_SETUP gs_ghost_volume PASS_REGULAR_EXPRESSION "PASSED")
endforeach()
if(_gs_gv_backends)
  add_test(NAME gs_ghost_volume_compare COMMAND ${Python3_EXECUTABLE}
           ${CMAKE_CURRENT_SOURCE_DIR}/ghost_volume/ghost_volume.py --compare ${_gs_gv_dir})
  set_tests_properties(gs_ghost_volume_compare PROPERTIES
    LABELS backends FIXTURES_REQUIRED gs_ghost_volume PASS_REGULAR_EXPRESSION "PASSED")
  message(STATUS "Ghost volume test backends: ${_gs_gv_backends}")
endif()

# Backend render check (#24, label render): each backend renders the same
# views on 1 and 4 ranks, headless through EGL, and the images must match
# (tests/render/render_check.py). Needs Python 3 with numpy and Pillow; the
# images stay in the build tree under tests/render/<backend>/ for review.
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import numpy, PIL" RESULT_VARIABLE _gs_no_pil OUTPUT_QUIET ERROR_QUIET)
set(_gs_rc_backends "")
if(Python3_Interpreter_FOUND AND _gs_no_pil EQUAL 0)
  set(_gs_rc ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/render/render_check.py
             --exe $<TARGET_FILE:gray-scott> --workdir ${CMAKE_CURRENT_BINARY_DIR}/render
             --mpiexec ${MPIEXEC_EXECUTABLE} "--mpiexec-preflags=${GS_TEST_MPIEXEC_PREFLAGS}")
  if(ENABLE_CATALYST)
    add_test(NAME gs_render_catalyst COMMAND ${_gs_rc} --backend catalyst --catalyst-lib ${GS_CATALYST_IMPLEMENTATION_DIR})
    list(APPEND _gs_rc_backends catalyst)
  endif()
  if(ENABLE_ASCENT)
    add_test(NAME gs_render_ascent COMMAND ${_gs_rc} --backend ascent)
    list(APPEND _gs_rc_backends ascent)
  endif()
  if(ENABLE_KOMBYNELITE)
    add_test(NAME gs_render_kombyne COMMAND ${_gs_rc} --backend kombyne)
    list(APPEND _gs_rc_backends kombyne)
  endif()
  if(GS_PVPYTHON)
    add_test(NAME gs_render_pvti COMMAND ${_gs_rc} --backend pvti --pvpython ${GS_PVPYTHON})
    list(APPEND _gs_rc_backends pvti)
  endif()
  foreach(b IN LISTS _gs_rc_backends)
    set_tests_properties(gs_render_${b} PROPERTIES
      LABELS "backends;render" TIMEOUT 1800 PROCESSORS 4 PASS_REGULAR_EXPRESSION "PASSED")
  endforeach()
  if(_gs_rc_backends)
    message(STATUS "Render check backends: ${_gs_rc_backends}")
  endif()
endif()
