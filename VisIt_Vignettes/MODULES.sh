#!/bin/bash
#
# Visualization Vignettes
#
# MODULES.sh -- load the VisIt environment for the current cluster.
#
#     source ../MODULES.sh
#
# Sourced (never executed) by every .sbat script in this directory tree, so
# the module changes land in the job's own shell.
#
# KEEP THE VERSION IN STEP WITH THE CUSTOMLAUNCHER
#
# On Shaheen the compute engine is not launched by this script. VisIt submits
# it through the site's ~/.visit/customlauncher, whose Shaheen job submitter
# writes the module load into the job file itself:
#
#     def TFileLoadModules(self, tfile):
#         tfile.write("module load visit/3.4.1\n")
#
# That version is hard-coded there. If the version loaded here ever differs
# from the version loaded there, the client and the engine are different
# builds of VisIt, and the failure surfaces as a connection that opens and
# then dies on a protocol mismatch rather than as anything naming a version.
# Change one and you must change the other.
#
# On Ibex the same file loads no modules at all -- its TFileLoadModules call
# is commented out -- and relies on AddEnvironment() forwarding VISITHOME,
# VISITARCHHOME, VISITPLUGINDIR and LD_LIBRARY_PATH into the engine job. The
# engine therefore inherits whatever this script loaded, which is another
# reason to load it here rather than inside a vignette.
#
# THE IBEX OS TEST
#
# The Ibex branch used to match only "CentOS". Ibex has since moved to a
# RHEL 9 family OS -- the customlauncher's own sbatch path says so:
#
#     return ["/opt/slurm/cluster/ibex/install-v2/RedHat-9/bin/sbatch"]
#
# so a CentOS-only test falls through to the error branch, and because this
# file is sourced rather than executed, that `exit 1` terminates the whole
# batch job with a message about an unrecognised operating system. The RHEL
# rebuilds are matched alongside CentOS now; the CentOS case is kept so an
# older node still works.
#
# Author: James Kress, <james@jameskress.com>
#
# VV_VISIT_MODULE, if set, names the module to load on any cluster (a new
# build under test, made visible first with `module use`), as
# VV_PARAVIEW_MODULE does for ParaView.
if [ -n "${VV_VISIT_MODULE:-}" ]; then
    echo "VV_VISIT_MODULE=$VV_VISIT_MODULE given: loading it directly"
    module load ffmpeg 2>/dev/null   # Ibex has one, Shaheen III does not
    # A VisIt module already loaded (from the login environment, say)
    # conflicts with the requested one, so unload it first. The module then
    # prepends its own bin directory, so its visit is the one found below.
    module unload visit 2>/dev/null
    module load "$VV_VISIT_MODULE"
else
OSVERSION=$( < /etc/os-release awk -F 'NAME=' '{print $2; exit;}')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"\"CentOS\""* | "\"Rocky Linux\""* | "\"Red Hat Enterprise Linux\""* | "\"AlmaLinux\""*) # Ibex
    module load ffmpeg
    # visit/3.5.0 since 12 Nov 2026, the build the baselines were blessed
    # with. Until it is released into the site tree it lives in the vis2
    # tree. No fallback to the site default: an older VisIt fails the
    # baselines, which should be loud, not quiet.
    module use /sw/vis2/ibex-rl9-gpu.2026.11/modules
    module load visit/3.5.0
    # The full loaded name (visit/3.5.0-gnu, say), parsed as the check below does.
    VV_VISIT_MODULE="$(module list -t 2>&1 | sed -E 's/[(<].*$//' | grep -m1 '^visit/')"
  ;;
"\"SLES\""*) # Shaheen
    module load ffmpeg 2>/dev/null   # no ffmpeg module on Shaheen III; harmless
    # Spelled out so a new site default does not change what the suites
    # test; set VV_VISIT_MODULE to test another build. visit/3.5.0 since 12
    # Nov 2026, the build the baselines were blessed with; until it is
    # released into the site tree it lives in the vis2 tree.
    module use /sw/vis2/shaheen3.2026.11/modules
    module load visit/3.5.0
    VV_VISIT_MODULE="visit/3.5.0"
  ;;
*)
    echo ERROR: Unrecognised operating system "$OSVERSION"
    exit 1 # terminate and indicate error
  ;;
esac
fi

# Recorded for the vignettes and for the log. The engine that the
# customlauncher submits must be this same version.
export VV_VISIT_MODULE="${VV_VISIT_MODULE:-visit/3.5.0}"
# A short name (visit) loads the site default: record the full name loaded.
if [[ "$VV_VISIT_MODULE" != */* ]]; then
    vv_full="$(module list -t 2>&1 | sed -E 's/[(<].*$//' | grep -m1 "^$VV_VISIT_MODULE/")" \
        && VV_VISIT_MODULE="$vv_full"
    unset vv_full
fi
# Shaheen's Environment Modules 3.2 returns 0 even for a module it cannot
# find, and a visit already on PATH would hide a failed load, so check that
# this exact module is listed as loaded (one name per line with -t, with any
# "(default)" or "<aL>" tag dropped), so visit/3.4.2 never matches visit/3.4.20.
if ! module list -t 2>&1 | sed -E 's/[(<].*$//' | grep -qxF "$VV_VISIT_MODULE"; then
    echo "ERROR: $VV_VISIT_MODULE is not loaded" >&2
    # shellcheck disable=SC2317  # exit is reached when the file is run, not sourced
    return 1 2>/dev/null || exit 1
fi
# True if the executable $1 found on PATH lives in a PATH directory that
# module $2 itself adds, read from `module show` (Tcl modules print
# "prepend-path PATH <dir>", Lmod prints prepend_path("PATH","<dir>"); one
# entry may hold several directories joined by ":"). This
# rejects a same-named executable that was already on PATH from elsewhere.
vv_exe_from_module() {
    local exe dir d
    exe="$(command -v "$1")" || return 1
    dir="$(cd "$(dirname "$exe")" && pwd -P)" || return 1
    while IFS= read -r d; do
        [ -n "$d" ] && [ "$(cd "$d" 2>/dev/null && pwd -P)" = "$dir" ] && return 0
    done < <(module show "$2" 2>&1 | sed -nE \
        -e 's/^(prepend|append)-path[[:space:]]+PATH[[:space:]]+([^[:space:]]+).*/\2/p' \
        -e 's/^(prepend|append)_path\("PATH",[[:space:]]*"([^"]+)".*/\2/p' | tr ':' '\n')
    return 1
}
# The test harness looks in $VISIT_PATH before PATH. Point it at the visit
# this module supplies, so an inherited VISIT_PATH cannot select another build.
if vv_exe_from_module visit "$VV_VISIT_MODULE"; then
    VISIT_PATH="$(dirname "$(command -v visit)")"
    export VISIT_PATH
else
    echo "ERROR: the visit on PATH ($(command -v visit || echo none)) is not from $VV_VISIT_MODULE" >&2
    # shellcheck disable=SC2317  # exit is reached when the file is run, not sourced
    return 1 2>/dev/null || exit 1
fi
echo "Loaded VisIt module: $VV_VISIT_MODULE ($VISIT_PATH/visit)"
