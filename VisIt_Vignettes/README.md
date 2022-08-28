# VisIt Vignettes

## What is VisIt
VisIt is an interactive, parallel analysis and visualization tool for scientific data. VisIt contains a rich set of visualization features so you can
view your data in a variety of ways. It can be used to visualize scalar and vector fields defined on two- and three-dimensional (2D and 3D) structured and
unstructured meshes. 

VisIt was developed to analyze extremely large datasets using distributed memory computing resources. KVL provides VisIt installs on Ibex and Shaheen to facilitate large scale distributed visualizations. The VisIt server running on Ibex and Shaheen may be used in a headless batch processing mode, however to use the GUI only Ibex is supported.


## Repo Organization
This subfolder is organized as follows:
- ``ibexVisIt`` folder contains example scripts of running VisIt in ``batch`` and ``interactive python`` modes
- ``shaheenVisIt`` folder contains example scripts of running VisIt ``batch`` and ``interactive python`` modes
- ``createVisItMovie.sh`` is a script to generate a movie from images generated with VisIt
- Information on VisIt and how to use it on KAUST computing resources is given below


## Overview of VisIt at KAUST
There are essentially two ways to use VisIt at KAUST:
1. Interactivelly
    1. KAUST IT Remote workstations: [Remote Workstations](https://myws.kaust.edu.sa/)
    2. Locally on your laptop or desktop. Kaust IT installs VisIt as a module on KAUST Ubuntu systems. Otherwise you can download a binary from the VisIt website: [VisIt](https://visit-dav.github.io/visit-website/releases-as-tables/#latest).
    3. Client/Server mode: a GUI client runs on your local machine and the data is processed on KAUST HPC resources. 
2. Batch mode: a python script is executed either locally or on KAUST HPC resources.


### Using VisIt Interactively on Ibex
It is possible to run a local VisIt client to display and interact with your data while the VisIt server runs in an Ibex batch job, allowing interactive analysis of very large data sets. You will obtain the best performance by running the VisIt client on your local computer and running the server on Ibex with the same version of VisIt. It is highly recommended to check the available VisIt versions using ``module avail visit`` on the system you plan to connect to with VisIt.

**WARNING**: Using a different version of VisIt than what is available on IBEX will most likely fail. 

If this is your first time using VisIt on KAUST resources you will need to have VisIt load the KAUST host profile to be able to connect to KAUST systems. VisIt is distributed with the KAUST profiles, so they can be directly loaded from the VisIt GUI as follows:
1. 
2. Click “Apply” and make sure to save the settings (Options/Save Settings).
Exit and re-launch VisIt.

After successfully completing the above steps, you should now be able to connect to Ibex.


#### Remote GUI Usage
After setting up and installing ParaView, you can connect to KAUST systems remotely to visualize your data interactively through ParaView's GUI.
1. Go to ``File/Connect`` and select Ibex (provided it was successfully imported).
2. Click on ``Connect`` and change the values in the Connection Options box.
    1. A dialog box follows, in which you must enter in your username the number of nodes to reserve and a duration to reserve them for. This is also where you can also select which CPU or GPU partition to use.
    2. It is recommended to use the CPU partition only, as the GPU partitions are VERY busy. To do this select **Node Group: CPU**.
3. When you click OK, a windows command prompt or ``xterm`` pops up. In this window enter your credentials at the login prompt.
4. When your job reaches the top of the queue, the main window will be returned to your control. At this point you are connected and can open files that reside
there and visualize them interactively.


Once you have VisIt installed and set up on your local computer:

-  Open VisIt on your local computer.
-  Go to: "File→Open file" or click the "Open" button on the GUI.
-  Click the "Host" dropdown menu on the "File open" window that popped
   up and choose "Ibex".
-  This will prompt you for your Ibex password, unless you have passwordless ssh setup.
-  Navigate to the appropriate file.
-  Once you choose a file, you will be prompted for the number of nodes
   and processors you would like to use.
-  Once specified, the server side of VisIt will be launched, and you
   can interact with your data.

### Using VisIt Interactively on Shaheen II
Shaheen II does not currently allow for ``client/server`` connections with VisIt. Therefore, you should just use ``batch`` mode with a python script on Shaheen. 

We expect to be able to use ``client/server`` mode on the upcoming Shaheen III system. 


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


### For more information on VisIt
[Documentation](https://visit-sphinx-github-user-manual.readthedocs.io/en/develop/index.html)
