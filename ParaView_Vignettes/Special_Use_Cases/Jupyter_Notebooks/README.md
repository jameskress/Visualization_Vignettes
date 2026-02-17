# Shaheen III Interactive Visualization Guide: ParaView + Jupyter

This guide explains how to run interactive ParaView scripts on Shaheen III compute nodes using Jupyter Lab.

**Warning:** This has only been tested using the Jupyter Lab workflow where you create a tunel to the compute nodes using the instructions printed to your terminal when you run the batch job. Running through VSCode, may or may not work. 

Because Shaheen uses a specialized Cray environment, we cannot simply `pip install paraview`. Instead, we must use a **Wrapped Kernel** that allows a standard Conda environment (running Jupyter) to load the system-optimized ParaView modules (for MPI and rendering).


## Part 0: Concepts & Theory: ParaView on HPC

Running visualization on a supercomputer like Shaheen requires understanding a few key concepts that differ from running ParaView on your laptop.

### Why "Headless" Rendering?
Shaheen compute nodes do not have physical monitors or standard graphics cards attached. Standard 3D applications usually crash because they cannot find an "X Server" (the window system).
* **The Fix:** We force ParaView to use **OSMesa** (Off-Screen Mesa), a software library that performs 3D rendering on the CPU without needing a window system. This is why you see `export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow` in our scripts.

### Why a "Wrapped Kernel"?
We need two conflicting things:
1.  **Flexibility:** We want to manage our own Python packages (like Jupyter, Matplotlib, Pandas) using Conda.
2.  **Performance:** We need ParaView to use the system's high-speed MPI libraries (Cray MPICH) to render across hundreds of cores.
* **The Problem:** If you just `pip install paraview`, you get a generic version that doesn't know how to talk to Shaheen's high-speed network.
* **The Solution:** We create a **Wrapper Script**. This script loads the optimized system modules first (setting up paths for MPI and ParaView), and *then* launches our Conda Python environment. This gives us the best of both worlds.

### Rendering Modes
* **Local (Serial) Rendering:** The notebook itself does the rendering.
    * *Pros:* Simplest setup.
    * *Cons:* Limited to 1 CPU core. Will crash if data is too large for one process.
* **Remote (Parallel) Rendering:** The notebook connects to a separate `pvserver` running on 192+ cores.
    * *Pros:* Can handle massive datasets. Rendering is distributed.
    * *Cons:* Requires launching a separate server process.
* **Static Images:** In Jupyter, we typically render a frame, save it as a PNG, and display it. We do *not* usually have a live, rotatable 3D window inside the notebook (unless using advanced web frameworks like Trame, which is outside the scope of this basic guide), and have proven not possible in the past on Shaheen.

---

## Part 1: One-Time Setup (The "Wrapped" Kernel)

You only do this part once, then can reuse it over and over again. 

First, login to shaheen, and navigate to your scrith directory. Next, follow the instructions below which allows us to use a simple Bash script to load the system modules before starting Python. This avoids manual path editing and ensures all Cray/MPI libraries are found.

### 1. Download and Install Miniconda (If Required)

*If you do not have Conda installed, follow these steps.*

```bash
cd ${SCRATCH_IOPS}

# 1. Download the Miniconda installer
wget [https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh](https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh)

# 2. Run the installer (install to your SCRATCH directory to save HOME quota)
# Follow the prompts. When asked for install location, use something like: /scratch/$USER/miniconda3
bash Miniconda3-latest-Linux-x86_64.sh -b -p ${SCRATCH_IOPS}/miniconda3

# 3. Initialize Conda (and restart your shell afterwards)
source ${SCRATCH_IOPS}/miniconda3/bin/activate
conda init
```

### 2. Create the Base Environment

*If you already have a `pv_env` environment, you can skip to Step 3.*

```bash
# Load Conda
# (Adjust this path if you installed Miniconda somewhere else)
source ${SCRATCH_IOPS}/miniconda3/etc/profile.d/conda.sh

# Create environment
conda create -n pv_env python=3.12
conda activate pv_env

# Install Jupyter components only (ParaView comes from the system)
conda install -c conda-forge jupyterlab ipykernel
```

### 3. Create the Wrapper Script

Create a file named `~/pv_kernel_wrapper.sh`. This script sets up the environment for every notebook cell. This is can be placed in your miniconda folder for eas of access:

**File Content for `~/pv_kernel_wrapper.sh`:**

```bash
#!/bin/bash

# --- 1. Load the Module ---
# This automatically sets LD_LIBRARY_PATH and PYTHONPATH to the current version.
module load paraview

# --- 2. The Filter ---
# The module adds two paths:
# This command rewrites PYTHONPATH to keep ONLY paths containing "site-packages".
export PYTHONPATH=$(echo $PYTHONPATH | tr ':' '\n' | grep "site-packages" | paste -sd: -)

# --- 3. Force Headless Rendering ---
# Crucial for Shaheen compute nodes which have no display attached
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow

# --- 4. Run the Conda Python Kernel ---
# UPDATE THE PATH BELOW to match your specific Conda environment location!
exec ${SCRATCH_IOPS}/miniconda3/envs/pv_env/bin/python -m ipykernel_launcher -f "$1"
```

**Make it executable:**

```bash
chmod +x ~/pv_kernel_wrapper.sh
```

### 4. Register the Kernel with Jupyter

Next, wer have to tell Jupyter to use your wrapper script instead of the default Python executable.

```bash
# 1. Create the kernel directory
python -m ipykernel install --prefix "${SCRATCH_IOPS}" --name paraview_system --display-name "ParaView System (Wrapper)"

# 2. Overwrite the kernel.json to use our wrapper
# (Adjust the path to pv_kernel_wrapper.sh if needed)
cat <<EOF > ${SCRATCH_IOPS}/share/jupyter/kernels/paraview_system/kernel.json
{
 "argv": [
  "${SCRATCH_IOPS}/miniconda3/pv_kernel_wrapper.sh",
  "{connection_file}"
 ],
 "display_name": "ParaView System (Wrapper)",
 "language": "python"
}
EOF
```

## Part 2: Submitting the Job (`submit_jupyter.sh`)

Finially, we can launch Jupyter Lab. The only tested method to get this to work is using the script below, which sets up tunnels to your local we browser, and you can use Jupyter Lab as normal. This script allocates a compute node, starts Jupyter, and prints the SSH tunnel command you need. Follow the instructions printed to you slurm job script file after the job launches. 

**Important:** Update the account to your own account (e.g., `k01`). Make sure that you update the path in SETUP CONDA if needed.

**Create file: `submit_jupyter.sh`**

```bash
#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=192
#SBATCH --cpus-per-task=1
#SBATCH --partition=workq
#SBATCH --time=03:30:00
#SBATCH --job-name=jupyter
#SBATCH --output=slurm-%j.log   # Standard output log
#SBATCH --error=slurm-%j.err    # Standard error log
#SBATCH --account=k01

export LC_ALL=C.UTF-8
export LANG=C.UTF-8
unset DISPLAY

# --- 1. SETUP CONDA ONLY ---
echo "Setting up Conda"
# We unset PYTHONPATH so Conda doesn't get confused during startup
unset PYTHONPATH
# UPDATE THIS PATH to your conda installation
source ${SCRATCH_IOPS}/miniconda3/etc/profile.d/conda.sh
conda activate pv_env

# --- 2. JUPYTER CONFIG ---
echo "Setting up Jupyter configs"
export JUPYTER_CONFIG_DIR="${SCRATCH_IOPS}/.jupyter"
export JUPYTER_DATA_DIR="${SCRATCH_IOPS}/.local/share/jupyter"
export JUPYTER_RUNTIME_DIR="${SCRATCH_IOPS}/.local/share/jupyter/runtime"
export IPYTHONDIR="${SCRATCH_IOPS}/.ipython"
export JUPYTER_PATH="${SCRATCH_IOPS}/share/jupyter:${JUPYTER_PATH}"

# --- 3. LAUNCH ---
echo "Launching Jupyter Lab"
node=$(hostname -s)
user=$(whoami)
submit_host=${SLURM_SUBMIT_HOST}

# Find free ports
port=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
# Secondary port (useful for other services, if needed)
tb_port=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')

# Start Jupyter in the background
jupyter lab --no-browser --port=${port} --port-retries=0 --ip=${node} &
pid=$!
sleep 10

# --- 4. PRINT INSTRUCTIONS ---
echo " "
echo "========================================================================"
echo "1. Run this command on your local laptop to create the tunnel:"
echo "   ssh -L ${port}:${node}:${port} -L ${tb_port}:${node}:${tb_port} ${user}@${submit_host}.hpc.kaust.edu.sa"
echo " "
echo "2. Open your web browser to:"
jupyter server list | awk '{print $1}' | sed "s/localhost:${port}/127.0.0.1:${port}/"
echo "========================================================================"
echo " "

wait $pid
```

**To submit:**

```bash
sbatch submit_jupyter.sh
```

**To connect:**

1. Check the output file (e.g., `slurm-12345.out`).
2. Run the SSH tunnel command printed in the log on your local machine.
3. Copy the URL starting with `http://127.0.0.1:...` from the log and paste it into your browser.

## Part 3: Launching the Visualization Server (Optional)

For parallel rendering (using all 192 cores), we run `pvserver` separately.

1. Open the Jupyter Interface in your browser.
2. Open a **Terminal** (File -> New -> Terminal).
3. Run this command:

   ```bash
   module load paraview
   export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
   
   # Launch the server on the current node
   srun -n 192 pvserver --force-offscreen-rendering
   ```

   *You should see "Waiting for client..."*

## Part 4: The Notebooks

**Important:** Ensure your Notebook Kernel is set to **"ParaView System (Wrapper)"**.

### Notebook A: Local Rendering

*Use this for simple rendering directly within the Jupyter kernel (single process).*

```python
from paraview.simple import *
from IPython.display import Image, display

# 1. Setup Pipeline
# Clean up any existing objects
def reset_pipeline():
    for _, src in list(GetSources().items()): Delete(src)
    for v in list(GetViews()): Delete(v)

reset_pipeline()

sphere = Sphere()
view = CreateView("RenderView")

# 2. Configure View
rep = Show(sphere, view)
view.CameraPosition = [0, 0, 3]
view.CameraFocalPoint = [0, 0, 0]

Render()

# 3. Display
fname = "/tmp/level1_local.png"
SaveScreenshot(fname, view, ImageResolution=[600, 400])
display(Image(filename=fname))

print("✅ Test complete: Local rendering")
```

### Notebook B: Connecting & Remote Rendering

*Use this to confirm the connection and render distributed geometry using the 192-core server.*

```python
import os
from paraview.simple import *
import paraview.servermanager as sm
from IPython.display import Image, display

# 1. Connect to pvserver
# If running srun -n 192 pvserver, it listens on localhost:11111
if not (sm.ActiveConnection and sm.ActiveConnection.IsRemote()):
    print("🔄 Connecting to remote pvserver...")
    Connect("127.0.0.1", 11111)
    print("✅ Connected to pvserver")
else:
    print("✅ Already connected to pvserver")

# 2. Reset Pipeline Helper
def reset_pipeline():
    for _, src in list(GetSources().items()): Delete(src)
    for v in list(GetViews()): Delete(v)
    print("♻️ Pipeline reset")

reset_pipeline()

# 3. Create Visualization
print("⚙️ Creating geometry...")
sphere = Sphere(ThetaResolution=60, PhiResolution=60)
elev = Elevation(Input=sphere)

# 4. Render
view = CreateView("RenderView")
view.ViewSize = [800, 600]
rep = Show(elev, view)

# Apply Coloring
ColorBy(rep, ("POINTS", "Elevation"))
lut = GetColorTransferFunction("Elevation")
lut.ApplyPreset("Blue to Red Rainbow", True)
lut.RescaleTransferFunction(0, 1)

ResetCamera()
Render()

# 5. Display Result
fname = "/tmp/remote_render.png"
SaveScreenshot(fname, view, ImageResolution=[800, 600])
display(Image(filename=fname))
```

### Notebook C: Loading Files (Silo/Exodus)

*Use this for real data read from file.*

```python
from paraview.simple import *
from IPython.display import Image, display

# (Ensure you are connected to pvserver using the code from notebook_remote_rendering.py)

# 1. Reset
for _, src in list(GetSources().items()): Delete(src)
for v in list(GetViews()): Delete(v)

# 2. Load Data
# Update this path to your actual data file
noise_file = "/sw/vis2/shaheen3/visit-src-3.4.2/install/data/noise.silo"

print(f"📂 Loading {noise_file}...")
noise = VisItSiloReader(registrationName='noise.silo', FileName=[noise_file])

# Optimization: Only load necessary arrays to save memory
noise.Set(
    MeshStatus=['Mesh', 'Mesh2D'],
    MaterialStatus=['1 air', '2 chrome'],
    PointArrayStatus=['hardyglobal']
)

noise.UpdatePipeline()

# 3. Visualize
view = CreateView("RenderView")
rep = Show(noise, view)

# Color by 'hardyglobal'
ColorBy(rep, ("POINTS", "hardyglobal"))
rep.SetRepresentationType("Surface")

lut = GetColorTransferFunction("hardyglobal")
lut.ApplyPreset("Blue to Red Rainbow", True)
lut.RescaleTransferFunctionToDataRange(True)

ResetCamera()
Render()

# 4. Save & Show
fname = "/tmp/silo_render.png"
SaveScreenshot(fname, view, ImageResolution=[800, 600])
display(Image(filename=fname))
print("✅ Render complete")
