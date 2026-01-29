#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=192
#SBATCH --cpus-per-task=1
#SBATCH --partition=workq
#SBATCH --time=03:30:00
#SBATCH --job-name=jupyter
#SBATCH --account=k01

export LC_ALL=C.UTF-8
export LANG=C.UTF-8
unset DISPLAY

# --- 1. SETUP CONDA ONLY ---
unset PYTHONPATH
source /scratch/kressjm/paraviewConda/miniconda3/etc/profile.d/conda.sh
conda activate pv_env

# --- 2. JUPYTER CONFIG ---
export JUPYTER_CONFIG_DIR=${SCRATCH_IOPS}/.jupyter
export JUPYTER_DATA_DIR=${SCRATCH_IOPS}/.local/share/jupyter
export JUPYTER_RUNTIME_DIR=${SCRATCH_IOPS}/.local/share/jupyter/runtime
export IPYTHONDIR=${SCRATCH_IOPS}/.ipython

# --- 3. LAUNCH ---
node=$(hostname -s)
user=$(whoami)
submit_host=${SLURM_SUBMIT_HOST}
port=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
tb_port=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')

jupyter lab --no-browser --port=${port} --port-retries=0 --ip=${node} &
pid=$!
sleep 10

echo " "
echo "ssh -L ${port}:${node}:${port} -L ${tb_port}:${node}:${tb_port} ${user}@${submit_host}.hpc.kaust.edu.sa"
echo " "
jupyter server list
wait $pid