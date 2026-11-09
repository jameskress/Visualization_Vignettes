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
