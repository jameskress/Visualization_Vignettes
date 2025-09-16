# =========================================================================
# Stage 1: The "Builder"
# This stage has all the tools needed to compile ParaView, ADIOS2, etc.
# =========================================================================
FROM ubuntu:22.04 AS builder

# Set an environment variable to avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install all build-time dependencies
# This includes compilers, CMake, Git, MPI, Python, HDF5, NetCDF, and OpenGL libraries
RUN apt-get update && apt-get install -y -qq \
    build-essential \
    cmake \
    git \
    libopenmpi-dev \
    openmpi-bin \
    python3-dev \
    python3-pip \
    libgl1-mesa-dev \
    libosmesa6-dev \
    libxt-dev \
    libnetcdf-dev \
    libhdf5-dev \
    libfmt-dev \
    wget \
    ca-certificates \
    gpg \
    curl \
    flex \
    bison \
    && rm -rf /var/lib/apt/lists/*

# --- Install/Upgrade Python build dependencies needed by the superbuild ---
# An older version of pip can cause issues with modern packages.
# We upgrade pip and its core components, and ensure flit-core is present.
RUN pip3 install --upgrade --quiet pip setuptools wheel
RUN pip3 install --quiet flit-core

# --- Upgrade CMake to a version required by ParaView Superbuild ---
# The default Ubuntu 22.04 CMake is too old. We'll use the official Kitware APT repo.
# We explicitly install both cmake and cmake-data with the same version to avoid dependency issues.
RUN wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | gpg --dearmor - | tee /usr/share/keyrings/kitware-archive-keyring.gpg >/dev/null && \
    echo 'deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ jammy main' | tee /etc/apt/sources.list.d/kitware.list >/dev/null && \
    apt-get update && \
    apt-get install -y cmake=3.28.1* cmake-data=3.28.1* && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory for all our source code builds
WORKDIR /builds

# --- Build and Install ADIOS2 ---
# We will install it to a custom prefix to keep it organized
RUN git clone --quiet https://github.com/ornladios/ADIOS2.git adios2-src
RUN cmake -S adios2-src -B adios2-build \
    -DCMAKE_INSTALL_PREFIX=/opt/adios2 \
    -DADIOS2_USE_MPI=ON \
    -DBUILD_TESTING=OFF
RUN cmake --build adios2-build -j$(nproc)
RUN cmake --install adios2-build


# --- Build and Install ParaView via Superbuild ---
# This is a major build and will take a significant amount of time.
# The superbuild handles fetching and building ParaView, Catalyst, VTK, and other dependencies.
ARG PARAVIELD_VERSION=v5.13.2
RUN git clone --quiet --recursive -b ${PARAVIELD_VERSION} https://gitlab.kitware.com/paraview/paraview-superbuild.git
WORKDIR /builds/paraview-superbuild/build
RUN cmake \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DUSE_SYSTEM_mpi=ON \
    -DUSE_SYSTEM_python3=OFF \
    -DENABLE_catalyst=ON \
    -DENABLE_mpi=ON \
    -DENABLE_netcdf=ON \
    -DENABLE_hdf5=ON \
    -DENABLE_python3=ON \
    -DENABLE_openmp=ON \
    -DENABLE_osmesa=ON \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    ..
# Limiting parallel jobs to 2 to avoid running out of memory, a common issue on large builds.
RUN cmake --build . -j2

# Reset WORKDIR for any subsequent builds
WORKDIR /builds

# --- Build and Install Ascent ---
RUN git clone --quiet --recursive https://github.com/alpine-dav/ascent.git ascent-src
WORKDIR /builds/ascent-src
# Checkout a stable, tagged release instead of the main development branch
RUN git checkout v0.9.5
# The build script uses environment variables for configuration.
# We set the installation prefix to /opt/ascent to keep it organized.
RUN env prefix=/opt/ascent enable_mpi=ON enable_openmp=ON ./scripts/build_ascent/build_ascent.sh

# Reset WORKDIR for any subsequent builds
WORKDIR /builds


# --- Build other dependencies (Fides, Viskores, etc.) ---
# You would follow a similar pattern for your other dependencies.
# For example:
# RUN git clone <fides_repo_url> fides-src
# RUN cmake -S fides-src -B fides-build -DCMAKE_INSTALL_PREFIX=/opt/fides ...
# RUN cmake --build fides-build -j$(nproc)
# RUN cmake --install fides-build


# =========================================================================
# Stage 2: The "Final" Image
# This is the clean, small image you will distribute. It only contains
# the runtime dependencies and the installed software from the builder stage.
# =========================================================================
FROM ubuntu:22.04

# --- Install RUNTIME dependencies AND build tools for the user code ---
# The -dev packages are needed to compile the user code against these libraries.
RUN apt-get update && apt-get install -y -qq \
    build-essential \
    libopenmpi-dev \
    openmpi-bin \
    python3 \
    python3-pip \
    git \
    libgl1 \
    libopengl0 \
    libosmesa6 \
    libxt6 \
    libnetcdf19 \
    libhdf5-103 \
    wget \
    ca-certificates \
    gpg \
    vim \
    nano \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# --- Upgrade CMake in the final image to match the builder stage ---
# This is required because the pre-built Ascent libraries require a modern CMake.
RUN wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | gpg --dearmor - | tee /usr/share/keyrings/kitware-archive-keyring.gpg >/dev/null && \
    echo 'deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ jammy main' | tee /etc/apt/sources.list.d/kitware.list >/dev/null && \
    apt-get update && \
    apt-get install -y cmake=3.28.1* cmake-data=3.28.1* && \
    rm -rf /var/lib/apt/lists/*

# Copy the installed software from the "builder" stage
COPY --from=builder /opt/adios2 /opt/adios2
COPY --from=builder /builds/paraview-superbuild/build/install /opt/paraview
COPY --from=builder /opt/ascent /opt/ascent
# Add COPY lines for your other installed dependencies here
# COPY --from=builder /opt/fides /opt/fides
# COPY --from=builder /opt/viskores /opt/viskores
# ... etc.

# --- Install Python plotting libraries into ParaView's Python ---
# We must use the pip associated with ParaView's self-contained Python to install packages.
RUN /opt/paraview/bin/python3 -m pip install numpy pandas matplotlib

# --- Create a stable symlink to the versioned HDF5 directory ---
# This makes the environment resilient to minor version changes from the Ascent build.
# We remove the trailing slash from the source path glob for robustness.
RUN ln -s /opt/ascent/install/hdf5-* /opt/ascent/install/hdf5

# --- IMPORTANT: Set Environment Variables ---
# This makes the installed libraries and executables discoverable by the system.
ENV PATH="/opt/paraview/bin:${PATH}"
# The Ascent build script places many libraries in versioned subdirectories.
# We add them all here using wildcards for resilience.
ENV LD_LIBRARY_PATH="/opt/paraview/lib:/opt/adios2/lib:/opt/ascent/install/ascent-checkout/lib:/opt/ascent/install/conduit-*/lib:/opt/ascent/install/raja-*/lib:/opt/ascent/install/umpire-*/lib:/opt/ascent/install/mfem-*/lib:/opt/ascent/install/silo-*/lib:/opt/ascent/install/vtk-m-*/lib:/opt/ascent/install/zlib-*/lib:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}"
# The CMAKE_PREFIX_PATH helps CMake find all your custom-built packages
# We add /opt/ascent/install so CMake can find Ascent's dependencies like Conduit.
ENV CMAKE_PREFIX_PATH="/opt/ascent/install:/opt/paraview/lib/cmake/paraview-5.13:/opt/paraview/lib/cmake/catalyst-2.0:/opt/adios2/lib/cmake/adios2:/opt/ascent/lib/cmake/ascent"

# --- FIX for HDF5 version mismatch ---
# We must use LD_PRELOAD to force the dynamic linker to load the correct HDF5
# library from Ascent's installation before it finds the older system version.
# We use the stable symlink created above for resilience.
ENV LD_PRELOAD="/opt/ascent/install/hdf5/lib/libhdf5.so"

# --- Create a non-root user that will be modified by the entrypoint script ---
# The -m flag creates a home directory, which is needed by applications like Matplotlib.
RUN groupadd -r viz && useradd --no-log-init -r -m -g viz vizuser

# Set the main application directory
WORKDIR /app

# Create a directory for mounting host data and set permissions
RUN mkdir /app/data && chown -R vizuser:viz /app/data
# Create a separate directory for the installed user application
RUN mkdir /app/install && chown -R vizuser:viz /app/install

# Copy your application's source code into the container
# This copies the entire project, including the Miniapps subdirectory
COPY . .

# Change ownership of the copied files to the new user.
# This must be done *before* switching to the non-root user.
RUN chown -R vizuser:viz /app

# --- Automatically update Catalyst settings files ---
# This finds all catalyst-related JSON settings files and replaces any existing
# library path with the correct path inside the container. This must be run
# before switching to the non-root user if permissions are restricted.
RUN find /app -name "settings-catalyst*.json" -print0 | xargs -0 sed -i 's|"catalyst_lib_path": ".*"|"catalyst_lib_path": "/opt/paraview/lib/catalyst"|g'

# --- Set up the entrypoint and setup scripts ---
# The scripts are now copied from the scripts/docker subdirectory
COPY Scripts/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY Scripts/docker/setup_rundir.sh /usr/local/bin/setup_rundir.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/setup_rundir.sh

# --- Build the user's application as the final step of the image build ---
# We switch to the non-root user temporarily just for this build step.
USER vizuser
WORKDIR /app/Miniapps/gray-scott
RUN rm -rf build
# We now install the application to /app/install, which serves as a template for the user.
RUN cmake -S . -B build \
    -DENABLE_TIMERS=1 \
    -DBUILD_ANALYSIS_READER=ON \
    -DCMAKE_BUILD_TYPE=RELEASE \
    -DENABLE_ASCENT=ON \
    -DENABLE_CATALYST=ON \
    -DENABLE_ADIOS2=ON \
    -DENABLE_KOMBYNELITE=OFF \
    -DCMAKE_INSTALL_PREFIX=/app/install && \
    cmake --build build -j$(nproc) && \
    cmake --install build

# Switch back to the root user before setting the entrypoint.
# This ensures the entrypoint script will be run as root.
USER root

# The entrypoint script takes over as the initial process
ENTRYPOINT ["entrypoint.sh"]

# Set the default starting directory for the container.
# The entrypoint script will drop the user into this directory.
WORKDIR /app/data

# Define the default command to be executed by the entrypoint script.
# The entrypoint will switch to 'vizuser' before running this command.
CMD ["/bin/bash"]

