# VisIt Vignettes

[VisIt_Vignettes Repository](https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes/-/tree/master/VisIt_Vignettes?ref_type=heads)

## What is VisIt
VisIt is an interactive, parallel analysis and visualization tool for scientific data. VisIt contains a rich set of visualization features so you can view your data in a variety of ways. It can be used to visualize scalar and vector fields defined on two- and three-dimensional (2D and 3D) structured and unstructured meshes. 

VisIt was developed to analyze extremely large datasets using distributed memory computing resources. KVL provides VisIt installs on Ibex and Shaheen to facilitate large scale distributed visualizations. The VisIt server running on Ibex and Shaheen may be used in a headless batch processing mode, however to use the GUI only Ibex is supported.


## Repo Organization
This subfolder is organized as follows:
- Individual examples each have their own directory. Each directory contains:
    - ``ex*.py`` various example scripts showing the use of VisIt from python
    - ``ex*_shaheen_runScript.sbat`` Shaheen batch scripts showing how to run VisIt in ``batch``
    - ``ex*_ibex_runScript.sbat`` Ibex batch scripts showing how to run VisIt in ``batch``
    - ``createVisItMovie.sh`` is a script to generate a movie from images generated with VisIt
- ``MODULES.sh`` is a module file that the batch scripts use to load the correct versions of modules
- Information on VisIt and how to use it on KAUST computing resources is given below

### Example Details
1. ``ex00`` - This script shows how to load a data set and then query information about the mesh, variables, and more
2. ``ex01`` - This script shows how to create a screenshot and save it to disk
3. ``ex02`` - This script shows how to take a series of screenshots while moving the camera and createing a movie
4. ``ex03`` - This script shows how to animate the visualization of multiple iso surface values, showing different segments of a static data set
5. ``ex04`` - This script shows how to animate the progress of streamlines in a flow field
6. ``ex05`` - This script shows how to load and step through a multi time step file and take a screenshot per step
7. ``ex06`` - This script shows how to load and create a complex visualization for a large data file


## Overview of VisIt at KAUST
There are essentially two ways to use VisIt at KAUST:
1. Interactivelly
    1. Locally on your laptop or desktop. You can download a binary from the VisIt website: [VisIt](https://visit-dav.github.io/visit-website/releases-as-tables/#latest).
    2. Client/Server mode: a GUI client runs on your local machine and the data is processed on KAUST HPC resources. 
2. Batch mode: a python script is executed either locally or on KAUST HPC resources.


### Using VisIt Interactively on Ibex
It is possible to run a local VisIt client to display and interact with your data while the VisIt server runs in an Ibex batch job (``client/server mode``), allowing interactive analysis of very large data sets. You will obtain the best performance by running the VisIt client on your local computer and running the server on Ibex with the same version of VisIt. It is highly recommended to check the available VisIt versions using ``module avail visit`` on the system you plan to connect to with VisIt.

**WARNING**: Using a different version of VisIt than what is available on IBEX WILL fail. 

If this is your first time using VisIt on KAUST resources you will need to have VisIt load the KAUST host profile to be able to connect to KAUST systems. VisIt is distributed with the KAUST profiles, so they can be directly loaded from the VisIt GUI as follows:
1. Click "Options"
2. Click "Host profiles and configuration setup"
3. Select KAUST and click "Install"
4. Save the settings (Options/Save Settings).
Exit and re-launch VisIt.

After successfully completing the above steps, you should now be able to connect to Ibex.


#### Remote GUI Usage
Once you have VisIt installed and set up on your local computer:

-  Open VisIt on your local computer.
-  Go to: "File→Open file" or click the "Open" button on the GUI.
-  Click the "Host" dropdown menu on the "File open" window that popped up and choose "Ibex".
-  This will prompt you for your Ibex password, unless you have passwordless ssh setup.
-  Navigate to the appropriate file.
-  Once you choose a file, you will be prompted for the number of nodes and processors you would like to use.
-  Once specified, the server side of VisIt will be launched, and you can interact with your data (after the job launches and reaches to top of the Ibex queue).


### Using VisIt Interactively on Shaheen III
It is possible to run a local VisIt client to display and interact with your data while the VisIt server runs in an Shaheen batch job (``client/server mode``), allowing interactive analysis of very large data sets. You will obtain the best performance by running the VisIt client on your local computer and running the server on Shaheen with the same version of VisIt. It is highly recommended to check the available VisIt versions using ``module avail visit`` on the system you plan to connect to with VisIt.

**WARNING**: Using a different version of VisIt than what is available on Shaheen WILL fail. 

If this is your first time using VisIt on KAUST resources you will need to have VisIt load the KAUST host profile to be able to connect to KAUST systems. VisIt is distributed with the KAUST profiles, so they can be directly loaded from the VisIt GUI as follows:
1. Click "Options"
2. Click "Host profiles and configuration setup"
3. Select KAUST and click "Install"
4. Save the settings (Options/Save Settings).
Exit and re-launch VisIt.

After successfully completing the above steps, you should now be able to connect to Shaheen.

**Note:** The above process will not give you the ``Shaheen 3`` host profile in VisIt versions ``3.4.1`` or older. For thos instances you will need to manually create the host profile using the information for the VisIt repository, located here: [KAUST Shaheen 3 VisIt Host Profile](https://github.com/visit-dav/visit/blob/develop/src/resources/hosts/kaust/host_kaust_shaheen.xml).


### Using VisIt in Batch Processing Mode ###
See the examples in this repo for how to create a job script to run a VisIt batch jobs. 


### Creating a Python Trace for Batch Processing
One of the most convenient tools available in the GUI is the ability to convert (or "trace") interactive actions in VisIt to Python code. Users that repeat
a sequence of actions in VisIt to visualize their data may find the Trace tool useful. The Trace tool creates a Python script that reflects most actions
taken in VisIt, which then can be used in batch mode to accomplish the same actions on Ibex or Shaheen.

To start tracing from the GUI, click on ``Controls/Command``. An options window will pop up, at the top there will be a ``Record`` button. Hit ``Record`` to start the trace, any time you modify properties, create filters, open files, etc., your actions will be translated into Python syntax. Once you are finished tracing the actions you want to script, click ``Stop``. A Python script should then be displayed to you and can be saved.


### For more information on VisIt
[Documentation](https://visit-sphinx-github-user-manual.readthedocs.io/en/develop/index.html)


## How to Run Examples in This Repo

### ex*.py
1. Run scripts locally or log on to either Ibex (<username>@ilogin.ibex.kaust.edu.sa) or Shaheen (<username>@shaheen.hpc.kaust.edu.sa)
2. Clone this repo
    1. Locally wherever you like
        * ``git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git``
    2. Ibex scratch:
        * ``cd /ibex/scratch/<username>``
        * ``git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git``
    3. Shaheen scratch
        * ``cd /scratch/<username>``
        * ``git clone https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes.git``
3. If using a cluster load the VisIt module file
    1. Ibex
        * ``module load visit``
    2. Shaheen
        * ``module use /sw/vis/xc40.modules``
        * ``module load VisIt``
4. Run the example locally or on one of the clusters
    1. Locally: 
        1. We can run the *.py script directly on the command line, not using a batch script
            * ``./visit -nowin -cli -s <path to the python script to run>``
        2. We can run the script live in the VisIt interface
            * Open the VisIt "command" window
            * Paste the following: 
                ``import os
                  from os.path import join as pjoin
                  scripts_dir = "<path to>/KAUST_Visualization_Vignettes/VisIt_Vignettes"
                  Source(pjoin(scripts_dir,"<name of the python script>"))``
            * Click "Execute"
    2. Clusters: From the scratch directory run the appropriate batch script for either Ibex or Shaheen:
        1. Ibex: ``sbatch ex*_ibex_runScript.sbat``
        2. Shaheen: 
            * Edit each Shaheen batch script by adding your account: ``vim ex*_shaheen_runScribt.sbat`` , and replace ``--account=<##>`` with your account
            * ``sbatch ex*_shaheen_runScribt.sbat``
5. View the output messages from the tests: 
    1. Locally: the output will print live to the terminal while running
    2. Ibex: ``cat ex*.ibex.<job_number>.out``
    3. Shaheen: ``cat ex*.shaheen_<job_number>.out``
6. View images from tests that write images:
    1. Locally: use your preferred image viewer 
    2. Ibex: ``display*.png``
        a. To view videos copy them to your local machine
    3. Shaheen ``eog .``
        a. To view videos copy them to your local machine
