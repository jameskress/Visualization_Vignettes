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
OSVERSION=$( < /etc/os-release awk -F 'NAME=' '{print $2; exit;}')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"\"CentOS\""* | "\"Rocky Linux\""* | "\"Red Hat Enterprise Linux\""* | "\"AlmaLinux\""*) # Ibex
    module load ffmpeg
    module load visit/3.4.1
  ;;
"\"SLES\""*) # Shaheen
    module load ffmpeg
    module load visit/3.4.1
  ;;
*)
    echo ERROR: Unrecognised operating system "$OSVERSION"
    exit 1 # terminate and indicate error
  ;;
esac

# Recorded for the vignettes and for the log. The engine that the
# customlauncher submits must be this same version.
export VV_VISIT_MODULE="visit/3.4.1"
echo "Loaded VisIt module: $VV_VISIT_MODULE"
