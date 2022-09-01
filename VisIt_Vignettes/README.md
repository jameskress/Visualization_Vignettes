# VisIt Vignettes

## What is VisIt
VisIt is an interactive, parallel analysis and visualization tool for scientific data. VisIt contains a rich set of visualization features so you can
view your data in a variety of ways. It can be used to visualize scalar and vector fields defined on two- and three-dimensional (2D and 3D) structured and
unstructured meshes. 

VisIt was developed to analyze extremely large datasets using distributed memory computing resources. KVL provides VisIt installs on Ibex and Shaheen to facilitate large scale distributed visualizations. The VisIt server running on Ibex and Shaheen may be used in a headless batch processing mode, however to use the GUI only Ibex is supported.


## Repo Organization
This subfolder is organized as follows:
- ``ex*.py`` various example scripts showing the use of VisIt from python
- ``ex*_shaheen_runScript.sbat`` Shaheen batch scripts showing how to run VisIt in ``batch``
- ``ex*_ibex_runScript.sbat`` Ibex batch scripts showing how to run VisIt in ``batch``
- ``createVisItMovie.sh`` is a script to generate a movie from images generated with VisIt
- ``MODULES.sh`` is a module file that the batch scripts use to load the correct versions of modules
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
Once you have VisIt installed and set up on your local computer:

-  Open VisIt on your local computer.
-  Go to: "File→Open file" or click the "Open" button on the GUI.
-  Click the "Host" dropdown menu on the "File open" window that popped up and choose "Ibex".
-  This will prompt you for your Ibex password, unless you have passwordless ssh setup.
-  Navigate to the appropriate file.
-  Once you choose a file, you will be prompted for the number of nodes and processors you would like to use.
-  Once specified, the server side of VisIt will be launched, and you can interact with your data (after the job launches and reaches to top of the Ibex queue).


### Using VisIt Interactively on Shaheen II
Shaheen II does not currently allow for ``client/server`` connections with VisIt. Therefore, you should just use ``batch`` mode with a python script on Shaheen. 

We expect to be able to use ``client/server`` mode on the upcoming Shaheen III system. 


### Creating a Python Trace for Batch Processing
One of the most convenient tools available in the GUI is the ability to convert (or "trace") interactive actions in VisIt to Python code. Users that repeat
a sequence of actions in VisIt to visualize their data may find the Trace tool useful. The Trace tool creates a Python script that reflects most actions
taken in VisIt, which then can be used in batch mode to accomplish the same actions on Ibex or Shaheen.

To start tracing from the GUI, click on ``Controls/Command``. An options window will pop up, at the top there will be a ``record`` button. Hit ``Record`` to start the trace, any time you modify properties, create filters, open files, etc., your actions will be translated into Python syntax. Once you are finished tracing the actions you want to script, click ``Stop``. A Python script should then be displayed to you and can be saved.


### For more information on VisIt
[Documentation](https://visit-sphinx-github-user-manual.readthedocs.io/en/develop/index.html)


## How to Run Examples in This Repo

### ex*.py
1. Log on to either Ibex (<username>@ilogin.ibex.kaust.edu.sa) or Shaheen (<username>@shaheen.hpc.kaust.edu.sa)
2. Clone this repo in your scratch directory
    1. Ibex:
        * ``cd /ibex/scratch/<username>``
        * ``git clone https://gitlab.kaust.edu.sa/kvl/KAUST_Visualization_Vignettes.git``
    2. Shaheen
        * ``cd /scratch/<username>``
        * ``git clone https://gitlab.kaust.edu.sa/kvl/KAUST_Visualization_Vignettes.git``
3. From the scratch directory run the appropriate batch script for either Ibex or Shaheen:
    1. Ibex: ``sbatch ex*_shaheen_runScribt.sbat``, and replace ``*`` with the number of the test you want to run
    2. Shaheen: 
        * Edit each Shaheen batch script by adding your account: ``vim ex*_shaheen_runScribt.sbat`` , and replace ``--account=<##>`` with your account
        * ``sbatch ex*_shaheen_runScribt.sbat``, and replace ``*`` with the number of the test you want to run
4. View the output messages from the tests: 
    1. Ibex: ``cat ex*.ibex.<job_number>.out``
    2. Shaheen: ``cat ex*.shaheen_<job_number>.out``
5. View images from tests that write images: 
    1. Ibex: ``xdg-open *.png``
    2. Shaheen ``eog .``


### createVisItMovie.sh
1. This script will in general work with any sequence of **png** files, but in this repo is only used for test ``ex02_visitAnimation.py``
2. After ``ex02_visitAnimation.py`` is run, you will have a sequence of png files, simply run ``bash createVisItMovie.sh`` and a movie will be saved
3. If desired you can change the framerate, encoding, etc. in the script to suit your needs
