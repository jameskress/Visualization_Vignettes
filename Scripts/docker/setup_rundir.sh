#!/bin/bash
# This script copies the pre-compiled Gray-Scott application and its
# default configuration files into the user's shared data directory.

set -e

# Define the target directory explicitly to ensure it's always correct.
TARGET_DIR="/app/data"

echo "Copying application files and default settings to ${TARGET_DIR}..."

# Copy all contents from the image's install directory to the target directory.
cp -r /app/install/* "${TARGET_DIR}/"

echo "Setup complete. Your run directory (${TARGET_DIR}) is now populated."
echo "You can now run simulations from here, for example:"
echo "mpirun -np 2 ./kvvm-gray-scott --settings-file=./settings-catalyst-insitu.json"

