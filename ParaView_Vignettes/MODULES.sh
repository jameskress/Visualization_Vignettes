#!/bin/bash
#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
# Check OS so we know what machine we are on
OSVERSION=$(lsb_release -sir | awk -F '.' '{ print $1 }')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"CentOS"*) # Ibex
    module load paraview/5.10.1-openmpi4.0.3-mesa
  ;;
"SUSE"*) # Shaheen
    module use  /sw/vis/xc40.modules
    module load ParaView/5.10.1-gnu11.2.0-mesa
    module load ffmpeg
  ;;
*)
    echo ERROR: Unrecognised operating system $osversion
    exit 1 # terminate and indicate error
  ;;
esac




