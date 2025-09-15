#!/bin/bash
# This script is designed to be the ENTRYPOINT of the Docker container.
# It modifies the 'vizuser' inside the container to match the UID and GID
# of the user on the host machine. This resolves file permission issues with
# bind mounts and provides a clean, named command prompt.

set -e

# Use environment variables passed to `docker run`, with a default of 1000.
HOST_UID=${HOST_UID:-1000}
HOST_GID=${HOST_GID:-1000}

# Get the original username and groupname from the image
USERNAME="vizuser"
GROUPNAME="viz"

# Modify the group and user to match the host's IDs
groupmod -g ${HOST_GID} ${GROUPNAME}
usermod -u ${HOST_UID} -g ${GROUPNAME} ${USERNAME}

# Re-set ownership of the user's home directory.
# This is crucial for applications like Matplotlib that write to $HOME.
chown -R ${HOST_UID}:${HOST_GID} /home/${USERNAME}

# Drop privileges and execute the command passed to `docker run` (e.g., "bash").
# The `exec` command replaces the shell process with the new command,
# ensuring that signals are handled correctly.
exec gosu ${USERNAME} "$@"

