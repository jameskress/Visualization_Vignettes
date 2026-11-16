# Writes gs_build_info.h with the git state of the source tree and the
# compiler settings, for the run metadata (#26). Runs on every build (see
# the gs_build_info target); configure_file rewrites the header only when
# its contents change, so an unchanged tree recompiles nothing.
#
# Inputs (-D): SRC_DIR, OUT_FILE, TEMPLATE, and the GS_CXX_* / GS_BUILD_TYPE /
# GS_ENABLED_BACKENDS values from the configure step.

set(GS_GIT_COMMIT "unknown")
set(GS_GIT_DESCRIBE "unknown")
set(GS_GIT_DIRTY "-1")  # -1: not a git checkout
find_package(Git QUIET)
if(GIT_FOUND)
  execute_process(COMMAND ${GIT_EXECUTABLE} rev-parse HEAD
    WORKING_DIRECTORY ${SRC_DIR} OUTPUT_VARIABLE _commit
    RESULT_VARIABLE _rc OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
  if(_rc EQUAL 0)
    set(GS_GIT_COMMIT "${_commit}")
    execute_process(COMMAND ${GIT_EXECUTABLE} describe --always --tags --dirty
      WORKING_DIRECTORY ${SRC_DIR} OUTPUT_VARIABLE GS_GIT_DESCRIBE
      OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
    # Tracked files only: build trees and scratch files do not make a run dirty.
    execute_process(COMMAND ${GIT_EXECUTABLE} status --porcelain --untracked-files=no
      WORKING_DIRECTORY ${SRC_DIR} OUTPUT_VARIABLE _status ERROR_QUIET)
    if(_status STREQUAL "")
      set(GS_GIT_DIRTY "0")
    else()
      set(GS_GIT_DIRTY "1")
    endif()
  endif()
endif()

# Not a git checkout (a tree exported with git archive, as the Shaheen
# builds are): take the commit from cmake/git_archive_commit.txt, which
# git archive fills in (export-subst in .gitattributes), or from the
# GS_SOURCE_COMMIT environment variable, for trees copied another way.
# The tree is then marked "archive", not dirty: it is exactly that commit
# as exported (or as the variable says).
if(GS_GIT_DIRTY STREQUAL "-1")
  set(_archived "")
  if(EXISTS "${SRC_DIR}/cmake/git_archive_commit.txt")
    file(STRINGS "${SRC_DIR}/cmake/git_archive_commit.txt" _archived LIMIT_COUNT 1)
  endif()
  if(_archived MATCHES "^[0-9a-f]+$")
    set(GS_GIT_COMMIT "${_archived}")
    set(GS_GIT_DESCRIBE "archive")
  elseif(DEFINED ENV{GS_SOURCE_COMMIT} AND NOT "$ENV{GS_SOURCE_COMMIT}" STREQUAL "")
    set(GS_GIT_COMMIT "$ENV{GS_SOURCE_COMMIT}")
    set(GS_GIT_DESCRIBE "GS_SOURCE_COMMIT")
  endif()
endif()

# Flags go into a C string literal: escape backslashes first, then quotes,
# so a flag such as -DFOO=\"bar\" stays one valid literal.
string(REPLACE "\\" "\\\\" GS_CXX_FLAGS "${GS_CXX_FLAGS}")
string(REPLACE "\"" "\\\"" GS_CXX_FLAGS "${GS_CXX_FLAGS}")
configure_file(${TEMPLATE} ${OUT_FILE} @ONLY)
