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
source /scratch/$USER/miniconda3/etc/profile.d/conda.sh
conda activate pv_env

# --- 2. JUPYTER CONFIG ---
echo "Setting up Jupyter configs"
# Redirect config to SCRATCH to avoid HOME quota limits
export JUPYTER_CONFIG_DIR=${SCRATCH_IOPS}/.jupyter
export JUPYTER_DATA_DIR=${SCRATCH_IOPS}/.local/share/jupyter
export JUPYTER_RUNTIME_DIR=${SCRATCH_IOPS}/.local/share/jupyter/runtime
export IPYTHONDIR=${SCRATCH_IOPS}/.ipython

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
