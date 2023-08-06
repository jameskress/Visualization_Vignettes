#!/bin/bash
#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
OSVERSION=$(lsb_release -sir | awk -F '.' '{ print $1 }')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"CentOS"*) # Ibex
    module load ffmpeg
    module load visit/3.3.2
  ;;
"SUSE"*) # Shaheen    
    module use  /sw/vis/xc40.modules
    module load VisIt/3.3.2-el7gnu9.3.0
    module load ffmpeg
  ;;
*)
    echo ERROR: Unrecognised operating system $osversion
    exit 1 # terminate and indicate error
  ;;
esac




