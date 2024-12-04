# Regression and Performance Testing

This `test_suite.py` is designed to allow us to track the performance and regression testing of installations of **VisIt** and **ParaView** on **Ibex** and **Shaheen**. These tests can also be run on your local machine, and make for a conveneint method to run each of the exampels in either the **ParaView** or **VisIt** directories without manually running each of them

## ParaView Testing

### Local Machine Test Runs

- Export the path to your ParaView install and run the ParaView tests:
```bash
export PARAVIEW_PATH="/home/kressjm/packages/ParaView-5.13.1-MPI-Linux-Python3.10-x86_64/bin"
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1
```

### Ibex CPU Test Runs

- First, load the necessary modules:
```bash
module load paraview/5.13.1-gnu-mesa
```

- Next, create a python virtual environment so that the necessary python packages exist:
```bash
python3 -m venv /ibex/scratch/kressjm/kvv_testing_paraview_env
cd kvv_testing_paraview_env/bin
source activate
pip3 install pandas
pip3 install matplotlib
pip3 install psutil
pip3 install scipy
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
```

- Next, run the ParaView tests:
```bash
srun   --cpus-per-task=12 --ntasks=1  --time=00:40:00  --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-cpu --non_gpu_machine
```

### Ibex GPU Test Runs

- First, load the necessary modules:
```bash
module load paraview/5.13.1-gnu-egl
```

- Next, create a python virtual environment so that the necessary python packages exist:
```bash
python3 -m venv /ibex/scratch/kressjm/kvv_testing_paraview_env
cd kvv_testing_paraview_env/bin
source activate
pip3 install pandas
pip3 install matplotlib
pip3 install psutil
pip3 install scipy
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
```

- Next, run the ParaView tests on the `v100 gpu`:
```bash
srun  --gres=gpu:v100:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-v100
```

- Next, run the ParaView tests on the `rtx2080ti gpu`:
```bash
srun  --gres=gpu:rtx2080ti:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-rtx2080ti
```

- Next, run the ParaView tests on the `p6000 gpu`:
```bash
srun  --gres=gpu:p6000:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-p6000
```

- Next, run the ParaView tests on the `p100 gpu`:
```bash
srun --gres=gpu:p100:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-p100
```

- Next, run the ParaView tests on the `gtx1080ti gpu`:
```bash
srun --gres=gpu:gtx1080ti:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-gtx1080ti
```

- Next, run the ParaView tests on the `a100 gpu`:
```bash
srun --gres=gpu:a100:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-a100
```


### Shaheen3 CPU Test Runs ###

- First, load the necessary modules:
```bash
module load paraview/5.13.1-mesa
```

- Next, create a python virtual environment so that the necessary python packages exist:
```bash
python3 -m venv /scratch/kressjm/kvv_testing_paraview_env
cd kvv_testing_paraview_env/bin
source activate
pip3 install pandas
pip3 install matplotlib
pip3 install psutil
pip3 install scipy
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
```

- Next, run the ParaView tests on the `workq` nodes:
```bash
srun --cpus-per-task=32 --ntasks=2  --time=00:40:00 --mem=200G -A k01 --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /scratch/kressjm/testing/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name shaheen3-cpu --non_gpu_machine
```

- Next, run the ParaView tests on the `PPN` CPU nodes:
```bash
srun --cpus-per-task=32 --ntasks=2 -p ppn --time=00:40:00 --mem=200G -A k01 --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /scratch/kressjm/testing/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name shaheen3-mesa-ppn --non_gpu_machine
```

### Shaheen3 GPU Test Runs ###

- First, load the necessary modules:
```bash
module load paraview/5.13.1-egl
```

- Next, create a python virtual environment so that the necessary python packages exist:
```bash
python3 -m venv /scratch/kressjm/kvv_testing_paraview_gpu_env
cd kvv_testing_paraview_gpu_env/bin
source activate
pip3 install pandas
pip3 install matplotlib
pip3 install psutil
pip3 install scipy
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
```

- Next, run the ParaView tests on the `PPN` GPU nodes:
```bash
srun --cpus-per-task=32 --ntasks=1 -p ppn -G 1 --time=00:40:00 --mem=200G -A k01 --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /scratch/kressjm/testing/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name shaheen3-mesa-ppn-gpu
```


## VisIt Testing

### Local Machine Test Runs

- Export the path to your VisIt install and run the VisIt tests:
```bash
export VISIT_PATH="/home/kressjm/packages/visit3_4_1.linux-x86_64/bin/"
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1
```

### Ibex CPU Test Runs

- First, load the necessary modules:
```bash
module load visit/3.4.1
module load ffmpeg
```

- Next, create a python virtual environment so that the necessary python packages exist:
```bash
python3 -m venv /ibex/scratch/kressjm/kvv_testing_visit_env
cd kvv_testing_visit_env/bin
source activate
pip3 install pytz
pip3 install six
pip3 install pyparsing
pip3 install psutil
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
``

- Next, run the VisIt tests:
```bash
srun   --cpus-per-task=12 --ntasks=1  --time=00:40:00  --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1  --machine_name ibex-cpu
```


### Ibex GPU Test Runs

- First, load the necessary modules:
```bash
module load visit/3.4.1
module load ffmpeg
```

- Next, create a python virtual environment so that the necessary python packages exist:
```bash
python3 -m venv /ibex/scratch/kressjm/kvv_testing_visit_env
cd kvv_testing_visit_env/bin
source activate
pip3 install pytz
pip3 install six
pip3 install pyparsing
pip3 install psutil
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
```

- Next, run the VisIt tests:
```bash
srun   --cpus-per-task=12 --ntasks=1  --time=00:40:00  --mem=100G --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1  --machine_name ibex-gpu
```


### Shaheen3 CPU Test Runs ###

- First, load the necessary modules:
```bash
module load visit/3.4.1
```

- Next, create a python virtual environment so that the necessary python packages exist (do this on a login node as compute nodes do not have network access):
```bash
python3 -m venv /scratch/kressjm/kvv_testing_visit_env
cd kvv_testing_visit_env/bin
source activate
pip3 install pytz
pip3 install pyparsing
pip3 install six
pip3 install psutil
pip3 install pandas
pip3 install matplotlib
pip3 install scipy
```

- When you are done testing and want to exit the `venv` do:
```bash
deactivate
```

- Next, run the VisIt tests on the `workq` nodes:
```bash
srun --cpus-per-task=32 --ntasks=2  -p workq --time=00:40:00 --mem=300G -A k01 --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python3 test_suite.py /scratch/kressjm/testing/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1 --machine_name shaheen3-cpu
```

- Next, run the VisIt tests on the `PPN` nodes:
```bash
srun --cpus-per-task=32 --ntasks=2 -p ppn --time=00:40:00 --mem=300G -A k01 --pty /bin/bash
cd KAUST_Visualization_Vignettes/Testing
python3 test_suite.py /scratch/kressjm/testing/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1 --machine_name shaheen3-ppn

```

## Continuous Integration
A GitLab CI pipeline is setup to run each time this repo is committed. It uses a GitLab Runner setup on an internal KVL system, `render-01`. This pipeline runs the `test_suite.py` for both ParaView and VisIt. The artifacts from these runs are saved for review. If the tests pass the CI pipeline will pass.

Pipeline artifacts can be found here: https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes/-/artifacts
