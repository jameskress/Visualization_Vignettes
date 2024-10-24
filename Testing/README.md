# Regression and Performance Testing

This `test_suite.py` is designed to allow us to track the performance and regression testing of installations of **VisIt** and **ParaView** on **Ibex** and **Shaheen**. These tests can also be run on your local machine, and make for a conveneint method to run each of the exampels in either the **ParaView** or **VisIt** directories without manually running each of them 

## ParaView Testing

### Local Machine Test Runs
```
export PARAVIEW_PATH="/home/kressjm/packages/ParaView-5.13.1-MPI-Linux-Python3.10-x86_64/bin"
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1 
```

### Ibex CPU Test Runs

```
module load paraview/5.13.1-gnu-mesa
```

```
srun   --cpus-per-task=12 --ntasks=1  --time=00:40:00  --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-cpu
```

### Ibex GPU Test Runs

```
module load paraview/5.13.1-gnu-egl
```

```
srun  --gres=gpu:v100:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-v100
```

```
srun  --gres=gpu:rtx2080ti:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-rtx2080ti
```

```
srun  --gres=gpu:p6000:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-p6000
```

```
srun --gres=gpu:p100:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-p100
```

```
srun --gres=gpu:gtx1080ti:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-gtx1080ti
```

```
srun --gres=gpu:a100:1  --cpus-per-task=12 --ntasks=1  --time=00:40:00 --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type ParaView --paraview_version 5.13.1  --machine_name ibex-egl-a100
```



## VisIt Testing

### Local Machine Test Runs

```
export VISIT_PATH="/home/kressjm/packages/visit3_4_1.linux-x86_64/bin/"
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1
```

### Ibex CPU Test Runs

```
module load visit/3.4.1
module load ffmpeg
```

```
srun   --cpus-per-task=12 --ntasks=1  --time=00:40:00  --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1  --machine_name ibex-cpu
```


### Ibex GPU Test Runs

```
module load visit/3.4.1
module load ffmpeg
```

There were missing python packages on my initial run, so this may come up in future installs as well. It was fixed by using the visit pip3 to install the pacakges
```
pip3 install pytz
pip3 install six
pip3 install pyparsing
pip3 install psutil
```


```
srun   --cpus-per-task=12 --ntasks=1  --time=00:40:00  --mem=100G --pty /bin/bash
python test_suite.py /ibex/scratch/kressjm/KAUST_Visualization_Vignettes/ --test_type VisIt --visit_version 3.4.1  --machine_name ibex-gpu
```
