#!/bin/bash
#
# Visualization Vignettes
#
# MODULES.sh -- load the ParaView environment for the current cluster.
#
#     source ../MODULES.sh [egl|mesa]
#
# Sourced (never executed) by every .sbat script in this directory tree, so
# the module changes and the exports below land in the job's own shell.
#
# WHAT IT EXPORTS, AND WHY
#
#   VV_PARAVIEW_MODULE          The module name that was actually loaded.
#                               Testing/run_tests.py reads it to make the same
#                               backend decision when it launches pvbatch
#                               outside a batch script.
#
#   VTK_DEFAULT_OPENGL_WINDOW   Which VTK render-window class ParaView should
#                               instantiate.
#
# The second one is the important one. ParaView 6.0 stopped picking a render
# window from the build alone, and the site's own interactive launcher --
# run_pvserver.sbat, the script pv_launcher.sh submits for a reverse-connected
# GUI session -- selects it explicitly from the module name:
#
#     if [[ "$MODNAME" == *"mesa"* ]]; then
#         export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
#     elif [[ "$MODNAME" == *"egl"* ]]; then
#         export VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow
#     fi
#
# The batch vignettes load the same modules and render through the same
# libraries, so they need the same hint. Without it an -egl module can fall
# back to llvmpipe and still produce images -- correct-looking, roughly a
# hundred times slower, and indistinguishable from a GPU run in the output.
# That silent fallback is exactly what ex08_pvBackendCheck exists to catch,
# and setting this here is what gives it something true to check.
#
# An export already present in the environment is left alone: somebody who
# set it by hand is saying something this script cannot infer.
#
# Author: James Kress, <james@jameskress.com>
#
# Check OS so we know what machine we are on
OSVERSION=$( < /etc/os-release  awk -F 'NAME=' '{print $2; exit;}')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"\"Rocky Linux\""* | "\"Red Hat Enterprise Linux\""* | "\"AlmaLinux\""* | "\"CentOS\""*) # Ibex

    # get latest paraview version number from ibex, and then load the pv we really want
    module load paraview
    currentVersion=$EBVERSIONPARAVIEW
    module unload paraview

    modVar=$1
    if [ "$modVar" = "egl" ]; then
        echo "Loading paraview egl variant"
        VV_PARAVIEW_MODULE="paraview/$currentVersion-gnu-egl"
    else
        echo "Loading paraview mesa variant"
        VV_PARAVIEW_MODULE="paraview/$currentVersion-gnu-mesa"
    fi
    module load "$VV_PARAVIEW_MODULE"
  ;;
"\"SLES\""*) # Shaheen

    # get latest paraview version number from shaheen, and then load the pv we really want
    module swap PrgEnv-cray PrgEnv-gnu
    module load paraview
    currentVersion=$EBVERSIONPARAVIEW
    module unload paraview

    modVar=$1
    if [ "$modVar" = "egl" ]; then
        echo "Loading paraview egl variant"
        VV_PARAVIEW_MODULE="paraview/$currentVersion-egl"
    else
        echo "Loading paraview mesa variant"
        VV_PARAVIEW_MODULE="paraview/$currentVersion-mesa"
    fi
    module load "$VV_PARAVIEW_MODULE"

    module load ffmpeg
  ;;
*)
    echo ERROR: Unrecognised operating system "$OSVERSION"
    exit 1 # terminate and indicate error
  ;;
esac

export VV_PARAVIEW_MODULE
echo "Loaded ParaView module: $VV_PARAVIEW_MODULE"

# -----------------------------------------------------------------------------
# SELECT THE OPENGL BACKEND FOR PARAVIEW 6.0+
#
# Same test, on the same evidence, as the site's run_pvserver.sbat.
# -----------------------------------------------------------------------------
if [ -n "$VTK_DEFAULT_OPENGL_WINDOW" ]; then
    echo "Honouring VTK_DEFAULT_OPENGL_WINDOW=$VTK_DEFAULT_OPENGL_WINDOW from the environment."
elif [[ "$VV_PARAVIEW_MODULE" == *"mesa"* ]]; then
    echo "Detected Mesa module: forcing software rendering (OSMesa)."
    export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
elif [[ "$VV_PARAVIEW_MODULE" == *"egl"* ]]; then
    echo "Detected EGL module: forcing hardware rendering (EGL)."
    export VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow
else
    echo "Unknown variant in '$VV_PARAVIEW_MODULE'. Defaulting to standard behavior."
fi
