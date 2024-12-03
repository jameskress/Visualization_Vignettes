# ParaView_Vignettes

[ParaView_Vignettes Repository](https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes/-/tree/master/ParaView_Vignettes?ref_type=heads)

## What is ParaView
ParaView is an open-source, multi-platform data analysis and visualization application. ParaView users can quickly build visualizations to analyze their data using qualitative and quantitative techniques. The data exploration can be done interactively in 3D or programmatically using ParaView’s batch processing capabilities.

ParaView was developed to analyze extremely large datasets using distributed memory computing resources. KVL provides ParaView server installs on Ibex and Shaheen to facilitate large scale distributed visualizations. The ParaView server running on Ibex and Shaheen may be used in a headless batch processing mode or an interactive GUI mode.


## Repo Organization
This subfolder is organized as follows:
- Individual examples each have their own directory. Each directory contains:
    - ``ex*.py`` various example scripts showing the use of ParaView from python
    - ``ex*_shaheen_runScript.sbat`` Shaheen batch scripts showing how to run ParaView with ``pvbatch``
    - ``ex*_ibex_runScript.sbat`` Ibex batch scripts showing how to run ParaView with ``pvbatch``
    - ``createParaViewMovie.sh`` Script to generate a movie from images generated with ParaView
- ``MODULES.sh`` is a module file that the batch scripts use to load the correct versions of modules
- Information on ParaView and how to use it on KAUST computing resources is given below

### Example Details
1. ``ex00`` - This script shows how to create a data source and query information about the mesh, variables, and more
2. ``ex01`` - This script shows how to create a data source and create a screenshot and save it to disk
3. ``ex02`` - This script shows how to create a data source and take a series of screenshots while moving the camera and createing a movie
4. ``ex03`` - This script shows how to animate the visualization of multiple iso surface values, showing different segments of a static data set
5. ``ex04`` - This script shows how to animate the progress of streamlines in a flow field
6. ``ex05`` - This script shows how to load and step through a multi time step file and take a screenshot per step
7. ``ex06`` - This script shows how to load and create a complex visualization for a large data file


## Overview of ParaView at KAUST
There are essentially two ways to use ParaView at KAUST:
1. Interactivelly
    1. Locally on your laptop or desktop. You can download a binary from Kitware: [ParaView](https://www.paraview.org/download/)
    2. Client/Server mode: a GUI client runs on your local machine and the data is processed on KAUST HPC resources.
2. Batch mode: a python script is executed either locally or on KAUST HPC resources.


### Using ParaView Interactively on Ibex
It is possible to run a local ParaView client to display and interact with your data while the ParaView server runs in an Ibex batch job (``client/server mode``), allowing interactive analysis of very large data sets. You will obtain the best performance by running the ParaView client on your local computer and running the server on Ibex with the same version of ParaView. It is *required* to check the available ParaView versions using ``module avail paraview`` on the system on which you plan to connect.

**WARNING**: Using a different version of ParaView than what is available on IBEX WILL fail.

**WARNING**: For macOS clients, it is necessary to install [XQuartz (X11)](https://www.xquartz.org/) to get a command prompt in which you will securely enter your credentials.

After local installation you must give ParaView the relevant server information to be able to connect to KAUST systems (comparable to VisIt's system of host
profiles). The following provides an example of doing so. Although several methods may be used, the one described should work in most cases.
* Step 1: Save the following ``default_servers.pvsc`` file to your local computer: [ibex_server](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ibex/default_servers.pvsc).
* Step 2: Start ParaView and then select ``File/Connect`` to begin.
* Step 3: Import Servers: Click ``Load Servers`` button and find the ``default_servers.pvsc`` file .

After successfully completing the above steps, you should now be able to connect to Ibex.


#### Remote GUI Usage
After setting up and installing ParaView, you can connect to KAUST systems remotely to visualize your data interactively through ParaView's GUI.
1. Go to ``File/Connect`` and select Ibex (provided it was successfully imported).
2. Click on ``Connect`` and change the values in the Connection Options box.
    1. A dialog box follows, in which you must enter in your username the number of nodes to reserve and a duration to reserve them for. This is also where you can also select which CPU or GPU partition to use.
    2. It is recommended to use the CPU partition only, as the GPU partitions are VERY busy. To do this select **Node Group: CPU**.
3. When you click OK, a windows command prompt or ``xterm`` pops up. In this window enter your credentials at the login prompt.
4. When your job reaches the top of the queue, the main window will be returned to your control. At this point you are connected and can open files that reside there and visualize them interactively.


### Using ParaView Interactively on Shaheen III
It is possible to run a local ParaView client to display and interact with your data while the ParaView server runs in an Shaheen batch job (``client/server mode``), allowing interactive analysis of very large data sets. You will obtain the best performance by running the ParaView client on your local computer and running the server on Shaheen with the same version of ParaView. It is *required* to check the available ParaView versions using ``module avail paraview`` on the system on which you plan to connect.


**WARNING**: Using a different version of ParaView than what is available on Shaheen WILL fail.

**WARNING**: For macOS clients, it is necessary to install [XQuartz (X11)](https://www.xquartz.org/) to get a command prompt in which you will securely enter your credentials.

After local installation you must give ParaView the relevant server information to be able to connect to KAUST systems (comparable to VisIt's system of host profiles). The following provides an example of doing so. Although several methods may be used, the one described should work in most cases.
* Step 1: Save the following ``default_servers.pvsc`` file to your local computer: [shaheen_server](https://gitlab.kaust.edu.sa/kvl/paraview-configs/-/blob/master/pvsc/ksl/default_servers.pvsc).
* Step 2: Start ParaView and then select ``File/Connect`` to begin.
* Step 3: Import Servers: Click ``Load Servers`` button and find the ``default_servers.pvsc`` file .

After successfully completing the above steps, you should now be able to connect to Shaheen.


### Using ParaView on Shaheen III GPU's ###

**Users must be in the `video` group**: All users who wish to use the PPN GPU's with ParaView must submit a ticket and ask to be part of the `video` group. Without this, ParaView will not find or use the GPU's.



### Using ParaView in Batch Processing Mode ###
See the examples in this repo for how to create a job script to run a ParaView python file.


### Creating a Python Trace for Batch Processing
One of the most convenient tools available in the GUI is the ability to convert (or "trace") interactive actions in ParaView to Python code. Users that repeat
a sequence of actions in ParaView to visualize their data may find the Trace tool useful. The Trace tool creates a Python script that reflects most actions
taken in ParaView, which then can be used by either PvPython or PvBatch (ParaView's Python interfaces) to accomplish the same actions.

To start tracing from the GUI, click on ``Tools/Start Trace``. An options window will pop up and prompt for specific Trace settings other than the default. Upon
starting the trace, any time you modify properties, create filters, open files, and hit Apply, etc., your actions will be translated into Python syntax. Once
you are finished tracing the actions you want to script, click ``Tools/Stop Trace``. A Python script should then be displayed to you and can be saved.


### Difference between ``pvbatch`` and ``pvpython``
ParaView comes with two command line programs that execute Python scripts: ``pvpython`` and ``pvbatch``. They are similar to the ``python`` executable that comes with Python distributions in that they accept Python scripts either from the command line or from a file and they feed the scripts to the Python interpreter.

The difference between ``pvpython`` and ``pvbatch`` is subtle and has to do with the way they establish the visualization service. ``pvpython`` is roughly equivalent to the paraview client GUI with the GUI replaced with the Python interpreter. It is a serial application that connects to a ParaView server (which can be either builtin or remote).

``pvbatch`` is roughly equivalent to ``pvserver`` except that commands are taken from a Python script rather than from a socket connection to a ParaView client. It is a parallel application that can be launched with mpirun (assuming it was compiled with MPI), but it cannot connect to another server; it is its own server.

In general, you should use ``pvpython`` if you will be using the interpreter interactively and ``pvbatch`` if you are running in parallel.

These examples will only use ``pvbatch``, if you want to interactively use ParaView from the command line you can start ``pvpython`` and interact with the interpreter in the same way as these example scipts.


### For more information on ParaView
[Documentation](https://docs.paraview.org/en/latest/index.html)


## How to Run Examples in This Repo

### ex*.py
1. Run scripts locally or log on to either Ibex (<username>@glogin.ibex.kaust.edu.sa) or Shaheen (<username>@shaheen.hpc.kaust.edu.sa)
2. Clone this repo in your scratch directory
    1. Locally wherever you like
        * ``git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git``
    2. Ibex:
        * ``cd /ibex/scratch/<username>``
        * ``git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git``
    3. Shaheen
        * ``cd /scratch/<username>``
        * ``git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git``
3. If using a cluster load the ParaView module file
    1. Ibex:
        * ``module load paraview``
    2. Shaheen
        * ``module load paraview``
4. Run the example locally or on one of the clusters
    1. Locally:
        1. We can run the *.py script directly on the command line, not using a batch script
    2. Clusters: From the scratch directory run the appropriate batch script for either Ibex or Shaheen:
        1. Ibex: ``sbatch ex*_ibex_runScribt.sbat``
        2. Shaheen:
            * Edit each Shaheen batch script by adding your account: ``vim ex*_shaheen_runScribt.sbat`` , and replace ``--account=<##>`` with your account
            * ``sbatch ex*_shaheen_runScribt.sbat``
5. View the output messages from the tests:
    1. Locally: the output will print live to the terminal while running
    2. Ibex: ``cat ex*.ibex.<job_number>.out``
    3. Shaheen: ``cat ex*.shaheen_<job_number>.out``
6. View images from tests that write images:
    1. Locally: use your preferred image viewer
    2. Ibex: ``display *.png``
        a. To view videos copy them to your local machine
    3. Shaheen ``display  *.png``
        a. To view videos copy them to your local machine
