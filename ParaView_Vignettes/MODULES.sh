#!/bin/bash
#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
# Check OS so we know what machine we are on
OSVERSION=$(cat /etc/os-release | awk -F 'NAME=' '{print $2; exit;}')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"\"Rocky Linux\""*) # Ibex

    # get latest paraview version number from ibex, and then load the pv we really want
    module load paraview
    currentVersion=$EBVERSIONPARAVIEW
    module unload paraview

    modVar=$1
    if [ "$modVar" = "egl" ]; then
        echo "Loading paraview egl variant"
        module load paraview/$currentVersion-gnu-egl
    else
        echo "Loading paraview mesa variant"
        module load paraview/$currentVersion-gnu-mesa
    fi
  ;;
"\"SLES\""*) # Shaheen
    module load paraview
  ;;
*)
    echo ERROR: Unrecognised operating system $osversion
    exit 1 # terminate and indicate error
  ;;
esac