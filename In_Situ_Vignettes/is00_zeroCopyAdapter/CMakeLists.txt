#
# is00_zeroCopyAdapter
#
# Needs Conduit and MPI only -- no renderer, no display, no GPU. That is
# deliberate: this is the vignette you can still run when the graphics stack
# is broken, and it is the one that catches the defect class (silent deep
# copies in the adapter) that costs the most at scale.
#
add_insitu_vignette(is00_zeroCopyAdapter
  SOURCES is00_zeroCopyAdapter.cpp
  LIBS    conduit::conduit conduit::conduit_blueprint
  RANKS   1 2 4
  ARGS    --size=32 --cycles=100
)

# The Python validator re-checks the emitted log independently of the exit
# code, so a vignette that starts exiting 0 while printing FAIL is still caught.
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_FOUND)
  add_test(NAME is00_zeroCopyAdapter.validate
           COMMAND ${Python3_EXECUTABLE}
                   ${CMAKE_CURRENT_SOURCE_DIR}/is00_validate.py
                   --binary $<TARGET_FILE:is00_zeroCopyAdapter>
                   --mpiexec ${MPIEXEC_EXECUTABLE}
                   --ranks 2)
  set_tests_properties(is00_zeroCopyAdapter.validate PROPERTIES TIMEOUT 600)
endif()

install(FILES is00_actions.yaml is00_validate.py DESTINATION .)
