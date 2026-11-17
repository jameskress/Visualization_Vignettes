#!/bin/bash
#
# Visualization Vignettes
#
# Author: James Kress, <james@jameskress.com>
#

module swap PrgEnv-"${PE_ENV,,}" PrgEnv-gnu/8.6.0
module unload gcc-native
# GCC 13.3.1: the compiler of the ParaView 6.2.1 superbuild in software/ (17 Nov 2026).
module load gcc-native/13.2
module unload cray-python
module load cmake/3.28.3
export CRAYPE_LINK_TYPE=dynamic
module unload cray-libsci
