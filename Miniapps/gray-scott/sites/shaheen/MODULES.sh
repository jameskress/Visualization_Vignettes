#!/bin/bash
#
# Visualization Vignettes
#
# Author: James Kress, <james@jameskress.com>
#

module swap PrgEnv-${PE_ENV,,} PrgEnv-gnu/8.5.0
module unload cray-python
module load cmake/3.28.3
export CRAYPE_LINK_TYPE=dynamic
module unload cray-libsci

