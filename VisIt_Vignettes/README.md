# VisIt Vignettes

[VisIt_Vignettes Repository](https://github.com/jameskress/Visualization_Vignettes/tree/master/VisIt_Vignettes)

## What is VisIt
VisIt is an interactive, parallel analysis and visualization tool for scientific data. VisIt contains a rich set of visualization features so you can view your data in a variety of ways. It can be used to visualize scalar and vector fields defined on two- and three-dimensional (2D and 3D) structured and unstructured meshes.

VisIt was developed to analyze extremely large datasets using distributed memory computing resources. It can be run both in interactive GUI mode and headless batch processing mode, making it ideal for HPC environments. The examples in this repository demonstrate both interactive and batch processing workflows.

## Getting Started

This repository provides both generic setup instructions that work on any HPC system and detailed instructions for specific known HPC installations. Choose the appropriate section based on your needs:

- [Generic HPC Setup](#generic-hpc-setup): Instructions for setting up VisIt on any HPC system
- [KAUST HPC Systems](#kaust-hpc-systems): Specific instructions for KAUST's Ibex and Shaheen III clusters
- [Example Details](#example-details): Information about the included visualization examples
- [Advanced Topics](#advanced-topics): Advanced configuration and usage information


## Repository Organization

Each example is self-contained in its own directory with the following structure:

- `ex*.py`: Python script demonstrating VisIt functionality
- `ex*_template_runScript.sbat`: Template batch script that can be customized for your HPC system
- `README.md`: Detailed explanation of the example and how to run it
- Additional helper scripts like `createVisItMovie.sh` for post-processing

The `MODULES.sh` script provides a template for loading required modules on your HPC system. Modify this according to your system's module environment.

### Example Details

The examples progress from basic operations to more complex visualizations:

1. `ex00_visitQuery`: Data loading and introspection
    - Load datasets and query mesh information
    - Access variable metadata
    - Basic data inspection techniques

2. `ex01_visitScreenshot`: Basic visualization and output
    - Set up a basic visualization pipeline
    - Configure view and display properties
    - Save high-quality screenshots

3. `ex02_visitAnimation`: Camera animation
    - Create smooth camera movements
    - Configure animation settings
    - Generate image sequences for movies

4. `ex03_visitIsosurfaceAnimation`: Advanced visualization techniques
    - Create and animate isosurfaces
    - Work with multiple visualization objects
    - Time-varying visualization properties

5. `ex04_visitStreamlineAnimation`: Flow visualization
    - Generate and animate streamlines
    - Work with vector fields
    - Configure seed points and integration parameters

6. `ex05_visitMultiTimeStepFile`: Time-varying data
    - Load and process time-series data
    - Time-dependent visualization
    - Batch processing multiple timesteps

7. `ex06_visitLargeData`: Production visualization
    - Handle large-scale datasets
    - Optimize performance
    - Complex multi-stage visualization pipelines


## Generic HPC Setup

### Basic Setup Steps

1. **Install Local VisIt Client:**
   - Download from [VisIt website](https://visit-dav.github.io/visit-website/releases-as-tables/#latest)
   - Choose version matching your HPC system's version

2. **Configure Host Profile:**
   ```xml
   <?xml version="1.0"?>
   <Object name="VIEWER">
      <Field name="HOST_PROFILES" type="stringVector">
         "my_hpc_system", "SLURM_SBATCH", "localhost",
         "parallel", "SLURM", "", "/path/to/visit/install"
      </Field>
   </Object>
   ```

3. **Run Example Scripts:**
   ```bash
   # Load VisIt module (adjust name as needed)
   module load visit
   
   # Run example in batch mode
   visit -nowin -cli -s ex01_visitScreenshot.py
   ```

## KAUST HPC Systems

### Ibex Cluster

1. **Connect and Setup:**
   ```bash
   ssh <username>@ilogin.ibex.kaust.edu.sa
   cd /ibex/scratch/<username>
   git clone https://github.com/jameskress/Visualization_Vignettes.git
   module load visit
   ```

2. **Client Configuration:**
   - Click "Options → Host profiles and configuration setup"
   - Select KAUST and click "Install"
   - Save settings and restart VisIt

3. **Run Examples:**
   ```bash
   cd Visualization_Vignettes/VisIt_Vignettes
   sbatch ex01/ex01_ibex_runScript.sbat
   ```

### Shaheen III

1. **Connect and Setup:**
   ```bash
   ssh <username>@shaheen.hpc.kaust.edu.sa
   cd /scratch/<username>
   git clone https://github.com/jameskress/Visualization_Vignettes.git
   module load visit
   ```

2. **Client Configuration:**
   - Use steps above for Ibex
   - For VisIt < 3.4.1: Use [KAUST Shaheen 3 Profile](https://github.com/visit-dav/visit/blob/develop/src/resources/hosts/kaust/host_kaust_shaheen.xml)

3. **Run Examples:**
   ```bash
   cd Visualization_Vignettes/VisIt_Vignettes
   # Edit account information
   vim ex01/ex01_shaheen_runScript.sbat
   # Replace --account=<##> with your account
   sbatch ex01/ex01_shaheen_runScript.sbat
   ```

**WARNING**: Version matching between client and server is critical. Always check available versions with `module avail visit`.

### Client/Server Setup
1. Install the VisIt client on your local machine
2. Check available VisIt versions on your HPC system: `module avail visit`
3. Download and install the matching client version
4. Configure host profiles for your HPC systems (see template batch scripts)

The examples in this repository include batch scripts that can be adapted for your specific HPC environment.

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
        * ``module load visit``
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
    2. Ibex: ``display *.png``
        a. To view videos copy them to your local machine
    3. Shaheen ``display *.png``
        a. To view videos copy them to your local machine
