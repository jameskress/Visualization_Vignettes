#!/bin/bash
#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
OSVERSION=$(cat /etc/os-release | awk -F 'NAME=' '{print $2; exit;}')
echo "Loading modules for OS Version: $OSVERSION"
case "$OSVERSION" in
"\"CentOS\""*) # Ibex
    module load ffmpeg
    module load visit/3.3.2
  ;;
"\"SLES\""*) # Shaheen    
    module load ffmpeg
    module load visit/3.3.3
  ;;
*)
    echo ERROR: Unrecognised operating system $osversion
    exit 1 # terminate and indicate error
  ;;
esac




