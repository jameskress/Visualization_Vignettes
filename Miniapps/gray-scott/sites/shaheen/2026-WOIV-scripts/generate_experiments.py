import os
import argparse
import json
import shutil

# =============================================================================
# CONFIGURATION: SYSTEM SPECIFICS (Shaheen III)
# =============================================================================
SYSTEM_CONFIG = {
    "account": "k01",      
    "partition": "workq",
    "constraints": "",
    "cores_per_node": 192,   
    "mpi_per_node": 64,      # 64 ranks: Power-of-two (2^6) for clean 3D decomposition
    "omp_threads": 3,        # 3 threads: Saturates 192 cores (64 * 3)
    "time_limit": "20:00:00" 
}

# =============================================================================
# GLOBAL SETTINGS
# =============================================================================
GLOBAL_SETTINGS = {
    "init_steps": 65000,      
    "init_burn_in": 0,        
    "run_steps": 501,         
    "plotgap": 20,            
    "output_type": "adhoc",
    "logging_level": "info"
}

INIT_NODE_MAP = {
    1024: 8,
    2048: 64,
    4096: 1024,  # Increased from 512 to 1024 nodes for 20hr time limit
    8192: 2048  
}

# =============================================================================
# DEFINITIONS (Strong/Weak Scaling)
# =============================================================================
STRONG_SCALING_NODES = [256, 1024, 4096]
STRONG_GRID = 4096

WEAK_SCALING_CONFIGS = [
    (8, 1024),
    (64, 2048),
    (512, 4096),
    (4096, 8192)
]

# Updated to exact 32:1 ratio from Paper 2 scaling tables
TRANSIT_CONFIGS = [
    ("small", 64, 2048, 2),        # Weak Scaling Start (32:1)
    ("compressed", 512, 8192, 16), # Strong Scaling Start (32:1)
    ("hero", 4096, 8192, 128)      # Weak/Strong Scaling End (32:1)
]

CATALYST_LIB_PATH = "/scratch/kressjm/Visualization_Vignettes/software/paraview-build/install/lib/catalyst"

PIPELINE_FILES = {
    "adios_xml":       "configs/adios2_configs/adios2.xml",
    "ascent_opts":     "configs/ascent_scripts/ascent_options.yaml",
    "ascent_render":   "configs/ascent_scripts/ascent-extract-png.yaml",
    "catalyst_render": "configs/catalyst_scripts/catalyst-extract-jpg.py",
    "kombyne_render":  "configs/kombyne_scripts/kombyne-extract-png.yaml",
    "ascent_data":     "configs/ascent_scripts/ascent-save-data.yaml",
    "catalyst_data":   "configs/catalyst_scripts/catalyst-save-data.py",
    "kombyne_data":    "configs/kombyne_scripts/kombyne-save-data.yaml"
}

# =============================================================================
# TEMPLATES
# =============================================================================
# EXASCALE FIX: DataTransport="RDMA" with ControlModule="epoll"
ADIOS_XML_TEMPLATE = """<?xml version="1.0"?>
<adios-config>
    <io name="SimulationOutput">
        <engine type="{engine_type}">
            <parameter key="verbose" value="0"/>
            <parameter key="RendezvousReaderCount" value="{rendezvous}"/>
            <parameter key="QueueLimit" value="1"/>
            <parameter key="QueueFullPolicy" value="Block"/>
            <parameter key="DataTransport" value="RDMA"/>
            <parameter key="ControlModule" value="epoll"/>
            <parameter key="OpenTimeoutSecs" value="600.0"/>
            <parameter key="AsyncWrite" value="false"/>
        </engine>
    </io>
    <io name="SimulationCheckpoint">
        <engine type="BP5">
            <parameter key="verbose" value="0"/>
            <parameter key="DataTransport" value="MPI"/>
            <parameter key="NumAggregators" value="1"/>
            <parameter key="AsyncWrite" value="false"/>
        </engine>
    </io>
    <io name="PDFAnalysisOutput">
        <engine type="BP5">
            <parameter key="verbose" value="0"/>
            <parameter key="DataTransport" value="MPI"/>
            <parameter key="NumAggregators" value="1"/>
            <parameter key="AsyncWrite" value="false"/>
        </engine>
    </io>
</adios-config>
"""

ASCENT_OPTIONS_TEMPLATE = """runtime:
  type: "ascent" 
  vtkm:
    backend: "openmp"
actions_file: "{actions_file}"
messages: "verbose" 
timings: "true"      
"""

ASCENT_RENDER_TEMPLATE = """
- action: "add_pipelines"
  pipelines:
    pl_x:
      f1:
        type: "slice"
        params:
          point: {{ x: {slice_offset}, y: {slice_offset}, z: {slice_offset} }}
          normal: {{ x: 1.0, y: 0.0, z: 0.0 }}
    pl_y:
      f1:
        type: "slice"
        params:
          point: {{ x: {slice_offset}, y: {slice_offset}, z: {slice_offset} }}
          normal: {{ x: 0.0, y: 1.0, z: 0.0 }}
    pl_z:
      f1:
        type: "slice"
        params:
          point: {{ x: {slice_offset}, y: {slice_offset}, z: {slice_offset} }}
          normal: {{ x: 0.0, y: 0.0, z: 1.0 }}

- action: "add_scenes"
  scenes:
    main_scene:
      plots:
        p1:
          type: "pseudocolor"
          field: "v"
          pipeline: "pl_x"
        p2:
          type: "pseudocolor"
          field: "v"
          pipeline: "pl_y"
          color_table:
            annotation: "false"
        p3:
          type: "pseudocolor"
          field: "v"
          pipeline: "pl_z"
          color_table:
            annotation: "false"
      renders:
        render1:
          image_width: 2048
          image_height: 2048
          annotations: "on"
          world_annotations: "false"
          image_prefix: "data/ascent_render_slices"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
            zoom: 2.0
"""

CATALYST_RENDER_TEMPLATE = """
from paraview import catalyst
from paraview.simple import *

_DisableFirstRenderCameraReset()

renderView1 = CreateView("RenderView")
renderView1.Set(
    ViewSize=[2048, 2048],
    AxesGrid="GridAxes3DActor",
    CenterOfRotation=[{center}, {center}, {center}],
    CameraPosition=[{cam_x}, {cam_y}, {cam_z}],
    CameraFocalPoint=[{center}, {center}, {center}],
    CameraViewUp=[{cam_up_x}, {cam_up_y}, {cam_up_z}],
    CameraFocalDisk=1.0,
    CameraParallelScale={parallel_scale},
    StereoType="Crystal Eyes"
)
SetActiveView(None)
layout1 = CreateLayout(name="Layout #1")
layout1.AssignView(0, renderView1)
layout1.SetSize(2048, 2048)
SetActiveView(renderView1)

producer = TrivialProducer(registrationName="grid")

sliceX = Slice(registrationName='SliceX', Input=producer)
sliceX.SliceType.Origin = [{slice_offset}, {slice_offset}, {slice_offset}]
sliceX.SliceType.Normal = [1.0, 0.0, 0.0]
sliceX.SliceOffsetValues = [0.0]

sliceY = Slice(registrationName='SliceY', Input=producer)
sliceY.SliceType.Origin = [{slice_offset}, {slice_offset}, {slice_offset}]
sliceY.SliceType.Normal = [0.0, 1.0, 0.0]
sliceY.SliceOffsetValues = [0.0]

sliceZ = Slice(registrationName='SliceZ', Input=producer)
sliceZ.SliceType.Origin = [{slice_offset}, {slice_offset}, {slice_offset}]
sliceZ.SliceType.Normal = [0.0, 0.0, 1.0]
sliceZ.SliceOffsetValues = [0.0]

vLUT = GetColorTransferFunction("v")
vLUT.Set(RGBPoints=[0.0, 0.23, 0.29, 0.75, 0.5, 0.86, 0.86, 0.86, 1.0, 0.7, 0.01, 0.14])

vPWF = GetOpacityTransferFunction("v")
vPWF.Set(Points=[0.0, 0.0, 0.5, 0.0, 1.0, 1.0, 0.5, 0.0])

Show(sliceX, renderView1, 'GeometryRepresentation').Set(Representation='Surface', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT)
Show(sliceY, renderView1, 'GeometryRepresentation').Set(Representation='Surface', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT)
sliceZDisplay = Show(sliceZ, renderView1, 'GeometryRepresentation')
sliceZDisplay.Set(Representation='Surface', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT)
sliceZDisplay.SetScalarBarVisibility(renderView1, True)

# Note the double braces for {{timestep}} to escape .format() call in generator script
pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_render_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.EnableCatalystLive = 0
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    grid = FindSource("grid")
    grid.UpdatePipeline()
    data_info = grid.GetDataInformation()
    v_array_info = data_info.GetPointDataInformation().GetArrayInformation("v")
    if v_array_info:
        v_min, v_max = v_array_info.GetComponentRange(0)
        vLUT = GetColorTransferFunction("v")
        vLUT.RescaleTransferFunction(v_min, v_max)
        vPWF = GetOpacityTransferFunction("v")
        vPWF.RescaleTransferFunction(v_min, v_max)

if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions
    SaveExtractsUsingCatalystOptions(options)
"""

KOMBYNE_RENDER_TEMPLATE = """
pipelines:
  # -------------------------------------------------------------------------
  # Pipeline 1: X-Normal Slice (YZ Plane)
  # -------------------------------------------------------------------------
  - type: "slice"
    enabled: true
    attributes:
      origin: [{slice_offset}, {slice_offset}, {slice_offset}]
      normal: [1.0, 0.0, 0.0]
    outputs:
      - type: "render"
        enabled: true
        file_pattern: "data/kombyne_slice_x_ts_%ts.png"
        file_format: "png"
        attributes:
          width: 2048
          height: 2048
          scene:
            colors:
              background: [0.0, 0.0, 0.0]
            camera:
              # Looking straight down the X axis
              position: [{cam_dist}, {center}, {center}]
              focus: [{slice_offset}, {center}, {center}]
              up: [0.0, 0.0, 1.0]
              fov: 30.0
            pseudocolor:
              variable: "V"
              color_table: "hot_desaturated"

  # -------------------------------------------------------------------------
  # Pipeline 2: Y-Normal Slice (XZ Plane)
  # -------------------------------------------------------------------------
  - type: "slice"
    enabled: true
    attributes:
      origin: [{slice_offset}, {slice_offset}, {slice_offset}]
      normal: [0.0, 1.0, 0.0]
    outputs:
      - type: "render"
        enabled: true
        file_pattern: "data/kombyne_slice_y_ts_%ts.png"
        file_format: "png"
        attributes:
          width: 2048
          height: 2048
          scene:
            colors:
              background: [0.0, 0.0, 0.0]
            camera:
              # Looking straight down the Y axis
              position: [{center}, {cam_dist}, {center}]
              focus: [{center}, {slice_offset}, {center}]
              up: [0.0, 0.0, 1.0]
              fov: 30.0
            pseudocolor:
              variable: "V"
              color_table: "hot_desaturated"

  # -------------------------------------------------------------------------
  # Pipeline 3: Z-Normal Slice (XY Plane)
  # -------------------------------------------------------------------------
  - type: "slice"
    enabled: true
    attributes:
      origin: [{slice_offset}, {slice_offset}, {slice_offset}]
      normal: [0.0, 0.0, 1.0]
    outputs:
      - type: "render"
        enabled: true
        file_pattern: "data/kombyne_slice_z_ts_%ts.png"
        file_format: "png"
        attributes:
          width: 2048
          height: 2048
          scene:
            colors:
              background: [0.0, 0.0, 0.0]
            camera:
              # Looking straight down the Z axis
              position: [{center}, {center}, {cam_dist}]
              focus: [{center}, {center}, {slice_offset}]
              up: [0.0, 1.0, 0.0]
              fov: 30.0
            pseudocolor:
              variable: "V"
              color_table: "hot_desaturated"
"""

KOMBYNE_DATA_TEMPLATE = """
pipelines:
  - type: "null"
    enabled: "true"
    frequency: 1 # Process every step the simulation sends
    outputs:
      - type: "export"
        file_pattern: "data/full_grid.%ts"
        file_format: "vtk"
        attributes:
          binary: "true"
"""

# EXASCALE FIX: Included full Libfabric tuning for Slingshot 11 + MPMD + Silence logs
SBATCH_TEMPLATE = """#!/bin/bash
#SBATCH --job-name={id}
#SBATCH --account={account}
#SBATCH --partition={partition}
#SBATCH --nodes={total_nodes}
#SBATCH --ntasks={total_ranks}
#SBATCH --cpus-per-task={omp_threads}
#SBATCH --time={time_limit}
#SBATCH --hint=nomultithread
#SBATCH --output={output_dir}/slurm-%j.out
#SBATCH --error={output_dir}/slurm-%j.err

source {repo_path}/Miniapps/gray-scott/sites/shaheen/MODULES.sh

export CATALYST_LIB_DIR="{catalyst_lib_path}"
unset DISPLAY
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
export GS_CATALYST_BACKEND=osmesa
export GALLIUM_DRIVER=softpipe
export LP_NUM_THREADS=1

# --- Exascale Slingshot-11 OFI Tuning ---
export FI_CXI_RX_MATCH_MODE=software
export FI_CXI_DEFAULT_CQ_SIZE=131072
export FI_CXI_OFLOW_BUF_SIZE=8388608
export FI_CXI_CQ_FILL_PERCENT=20
export FI_TCP_IFACE=hsn0
export CM_DISABLE_SHM=1
ulimit -n 131072

# --- Silencing ADIOS2 Logs ---
export SST_VERBOSE=0
export ADIOS2_LOG_LEVEL=1

export MPICH_MAX_THREAD_SAFETY=multiple
export OMP_NUM_THREADS={omp_threads}
export OMP_PLACES=threads
export OMP_PROC_BIND=spread
export PYTHONDONTWRITEBYTECODE=1

EXE_SIM="{bin_path}/gray-scott"
EXE_STAGE="{bin_path}/analysis-reader"
OUTPUT_DIR="{output_dir}"

# Ensure a clean slate for SST contact files
rm -f $OUTPUT_DIR/data/*.sst

mkdir -p $OUTPUT_DIR/data
lfs setstripe -c -1 $OUTPUT_DIR
cd $OUTPUT_DIR

echo "Starting Run: {id}"
{command}
"""

CMD_INLINE = """
srun --propagate=NOFILE --hint=nomultithread --ntasks={sim_ranks} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json
"""

CMD_INTRANSIT = """
srun --propagate=NOFILE --hint=nomultithread --kill-on-bad-exit=1 --wait=0 \\
    --nodes={sim_nodes} --ntasks={sim_ranks} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json \\
    : \\
    --nodes={stage_nodes} --ntasks={stage_ranks} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_STAGE \\
    --settings $OUTPUT_DIR/settings-stage.json \\
    --file $OUTPUT_DIR/data/grayScott \\
    --block-mode repartition \\
    --engine SST \\
    --mpi-split-color=1 \\
    --adios-verbose 0
"""

def generate_settings_json(exp, output_dir, copied_files, args):
    is_init = (exp['workload'] == 'initialization')
    init_noise_level = 0.01
    run_noise_level = 0.00001
    steps = exp['total_steps']
    
    config = {
        "L": exp['grid_size'],        
        "Du": 0.2, "Dv": 0.1, "F": 0.03, "k": 0.0545, "dt": 2.0, 
        "noise": init_noise_level if is_init else run_noise_level,
        "steps": steps,                  
        "burn_in_steps": GLOBAL_SETTINGS['init_burn_in'] if is_init else 0, 
        "plotgap": steps + 1 if is_init else GLOBAL_SETTINGS['plotgap'],            
        "output_file_name": f"{output_dir}/data/grayScott", 
        "output_type": "adhoc",                  
        "mesh_type": "image",                    
        "checkpoint": True if is_init else False, 
        "checkpoint_freq": steps if is_init else 0, 
        "checkpoint_output": f"{output_dir}/data/checkpoint.bp" if is_init else "",
        "restart": False if is_init else True, 
        "restart_input": f"{os.path.join(args.results_dir, exp['parent_id'])}/data/checkpoint.bp" if not is_init else "", 
        "overwrite_last_step": True if exp.get('workload') == 'data_save' else False,
        "catalyst_script_path": "", 
        "catalyst_lib_path": CATALYST_LIB_PATH,
        "kombynelite_script_path": "",
        "adios_config": f"{output_dir}/adios2.xml", 
        "adios_span": False, 
        "adios_memory_selection": True,
        "ascent_options": "" 
    }

    if is_init:
        config["output_type"] = "none"
    elif exp['type'] == 'intransit':
        config["output_type"] = "adios"
        config_stage = config.copy()
        parts = exp.get('stage_pipeline', "adios_data").split('_')
        stage_backend = parts[0]
        
        if stage_backend == "catalyst":
            config_stage["output_type"] = "catalyst_io" if exp['workload'] == 'data_save' else "catalyst_insitu"
        else:
            config_stage["output_type"] = stage_backend
        
        if stage_backend == 'ascent':
            config_stage["ascent_options"] = f"{output_dir}/ascent_options.yaml"
        elif stage_backend == 'catalyst' and config_stage["output_type"] == "catalyst_insitu":
            config_stage["catalyst_script_path"] = f"{output_dir}/" + os.path.basename(copied_files['pipeline'])
        elif stage_backend == 'kombyne':
            config_stage["kombynelite_script_path"] = f"{output_dir}/" + os.path.basename(copied_files['pipeline'])
            
        with open(f"{output_dir}/settings-stage.json", "w") as f:
            json.dump(config_stage, f, indent=4)
    else:
        if exp['backend'] == 'adios':
            config["output_type"] = "adios"
        elif exp['backend'] == 'ascent':
            config["output_type"] = "ascent"
            config["ascent_options"] = f"{output_dir}/ascent_options.yaml"
        elif exp['backend'] == 'catalyst':
            if exp['workload'] == 'data_save':
                config["output_type"] = "catalyst_io"
                config["output_file_name"] = f"{output_dir}/data/grayScott-%04ts.vtpd"
            else:
                config["output_type"] = "catalyst_insitu" 
                config["catalyst_script_path"] = copied_files['pipeline']
        elif exp['backend'] == 'kombyne':
            config["output_type"] = "kombyne"
            config["kombynelite_script_path"] = copied_files['pipeline']
        elif exp['backend'] == 'baseline':
            config["output_type"] = "pvti"
            config["output_file_name"] = f"{output_dir}/data/grayScott-%04ts.vti"
            config["plotgap"] = steps + 2000

    with open(f"{output_dir}/settings.json", "w") as f:
        json.dump(config, f, indent=4)

def generate_adios_xml(exp, output_dir):
    engine = "SST" if exp['type'] == 'intransit' else "BP5"
    rendezvous = 1 if exp['type'] == 'intransit' else 0
    xml_content = ADIOS_XML_TEMPLATE.format(engine_type=engine, rendezvous=rendezvous)
    with open(f"{output_dir}/adios2.xml", "w") as f:
        f.write(xml_content)

def copy_pipeline_files(exp, output_dir, repo_root):
    files_to_copy = {}
    mesh_spacing = 0.1
    physical_L = float(exp['grid_size']) * mesh_spacing
    center_val = physical_L / 2.0
    cam_x, cam_y, cam_z = center_val - (physical_L * 1.85), center_val + (physical_L * 1.10), center_val + (physical_L * 1.85)
    cam_up_x, cam_up_y, cam_up_z = 0.206668, 0.933382, -0.293403
    parallel_scale, slice_offset_val = physical_L * 1.60, center_val + (mesh_spacing * 6.5)
    cam_dist_val = center_val * 4.88 # Dynamically maps to the ~500.0 distance for Kombyne camera
    
    generate_adios_xml(exp, output_dir)

    effective_backend = exp['backend']
    if exp['backend'] == 'baseline': return files_to_copy

    if exp['type'] == 'intransit' and exp['backend'] == 'adios':
        if 'stage_pipeline' in exp:
            pipeline_key = exp['stage_pipeline']
            effective_backend = pipeline_key.split('_')[0]
    else:
        pipeline_key = f"{effective_backend}_{'render' if exp['workload'] == 'rendering' else 'data'}"

    if pipeline_key in PIPELINE_FILES:
        actions_filename = os.path.basename(PIPELINE_FILES[pipeline_key])
        dst_action = os.path.join(output_dir, actions_filename)
        
        if effective_backend == 'ascent':
            if exp['workload'] == 'rendering' or 'render' in pipeline_key:
                with open(dst_action, "w") as f:
                    f.write(ASCENT_RENDER_TEMPLATE.format(cam_x=cam_x, cam_y=cam_y, cam_z=cam_z, center=center_val, cam_up_x=cam_up_x, cam_up_y=cam_up_y, cam_up_z=cam_up_z, slice_offset=slice_offset_val))
            else:
                shutil.copy2(os.path.join(repo_root, "Miniapps/gray-scott", PIPELINE_FILES[pipeline_key]), dst_action)
            
            opts_path = os.path.join(output_dir, "ascent_options.yaml")
            with open(opts_path, "w") as f:
                f.write(ASCENT_OPTIONS_TEMPLATE.format(actions_file=actions_filename))
            files_to_copy['ascent_opts'] = opts_path
            
        elif effective_backend == 'catalyst':
            if exp['workload'] == 'rendering' or 'render' in pipeline_key:
                with open(dst_action, "w") as f:
                    f.write(CATALYST_RENDER_TEMPLATE.format(cam_x=cam_x, cam_y=cam_y, cam_z=cam_z, center=center_val, parallel_scale=parallel_scale, cam_up_x=cam_up_x, cam_up_y=cam_up_y, cam_up_z=cam_up_z, slice_offset=slice_offset_val))
                files_to_copy['pipeline'] = dst_action
            
        elif effective_backend == 'kombyne':
            if exp['workload'] == 'rendering' or 'render' in pipeline_key:
                with open(dst_action, "w") as f:
                    f.write(KOMBYNE_RENDER_TEMPLATE.format(cam_dist=cam_dist_val, center=center_val, slice_offset=slice_offset_val))
                files_to_copy['pipeline'] = dst_action
            elif 'data' in pipeline_key:
                with open(dst_action, "w") as f:
                    f.write(KOMBYNE_DATA_TEMPLATE)
                files_to_copy['pipeline'] = dst_action
        else:
            shutil.copy2(os.path.join(repo_root, "Miniapps/gray-scott", PIPELINE_FILES[pipeline_key]), dst_action)
            files_to_copy['pipeline'] = dst_action
        
    return files_to_copy

def generate_scripts(args):
    os.makedirs(args.output_dir, exist_ok=True)
    EXPERIMENTS = []
    init_info = {}

    def ensure_init(grid_size):
        if grid_size not in init_info:
            init_nodes = INIT_NODE_MAP.get(grid_size, 512)
            init_id = f"init_N{init_nodes:04d}_L{grid_size}"
            EXPERIMENTS.append({ "id": init_id, "paper": "init", "type": "inline", "backend": "adios", "workload": "initialization", "sim_nodes": init_nodes, "grid_size": grid_size, "total_steps": GLOBAL_SETTINGS['init_steps'] })
            init_info[grid_size] = (init_id, GLOBAL_SETTINGS['init_steps'])
        return init_info[grid_size]

    # --- Paper 1 Generation ---
    p1_nodes, p1_grid, p1_stage = 64, 2048, 4
    pid, p1_init_steps = ensure_init(p1_grid)
    p1_target = p1_init_steps + GLOBAL_SETTINGS['run_steps']

    EXPERIMENTS.append({ "id": f"paper1_func_N{p1_nodes:04d}_baseline", "paper": "paper1", "type": "inline", "backend": "baseline", "workload": "none", "sim_nodes": p1_nodes, "grid_size": p1_grid, "parent_id": pid, "total_steps": p1_target })
    EXPERIMENTS.append({ "id": f"paper1_func_N{p1_nodes:04d}_inline_adios_data", "paper": "paper1", "type": "inline", "backend": "adios", "workload": "data_save", "sim_nodes": p1_nodes, "grid_size": p1_grid, "parent_id": pid, "total_steps": p1_target })

    for backend in ["ascent", "catalyst", "kombyne"]:
        EXPERIMENTS.append({ "id": f"paper1_func_N{p1_nodes:04d}_inline_{backend}_data", "paper": "paper1", "type": "inline", "backend": backend, "workload": "data_save", "sim_nodes": p1_nodes, "grid_size": p1_grid, "parent_id": pid, "total_steps": p1_target })
        EXPERIMENTS.append({ "id": f"paper1_func_N{p1_nodes:04d}_inline_{backend}_render", "paper": "paper1", "type": "inline", "backend": backend, "workload": "rendering", "sim_nodes": p1_nodes, "grid_size": p1_grid, "parent_id": pid, "total_steps": p1_target })
        EXPERIMENTS.append({ "id": f"paper1_func_N{p1_nodes:04d}_transit_{backend}_render", "paper": "paper1", "type": "intransit", "backend": "adios", "workload": "rendering", "sim_nodes": p1_nodes, "stage_nodes": p1_stage, "grid_size": p1_grid, "stage_pipeline": f"{backend}_render", "parent_id": pid, "total_steps": p1_target })

    # --- Paper 2 Generation ---
    # Strong Scaling Inline
    for nodes in STRONG_SCALING_NODES:
        grid = STRONG_GRID
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS['run_steps']
        base_id = f"paper2_strong_N{nodes:04d}"
        EXPERIMENTS.append({ "id": f"{base_id}_baseline", "paper": "paper2", "type": "inline", "backend": "baseline", "workload": "none", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })
        EXPERIMENTS.append({ "id": f"{base_id}_adios_data", "paper": "paper2", "type": "inline", "backend": "adios", "workload": "data_save", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })
        for backend in ["ascent", "catalyst"]: # Kombyne explicitly removed for Paper 2
            EXPERIMENTS.append({ "id": f"{base_id}_{backend}_data", "paper": "paper2", "type": "inline", "backend": backend, "workload": "data_save", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })
            EXPERIMENTS.append({ "id": f"{base_id}_{backend}_render", "paper": "paper2", "type": "inline", "backend": backend, "workload": "rendering", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })

    # Weak Scaling Inline
    for nodes, grid in WEAK_SCALING_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS['run_steps']
        base_id = f"paper2_weak_N{nodes:04d}"
        EXPERIMENTS.append({ "id": f"{base_id}_baseline", "paper": "paper2", "type": "inline", "backend": "baseline", "workload": "none", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })
        EXPERIMENTS.append({ "id": f"{base_id}_adios_data", "paper": "paper2", "type": "inline", "backend": "adios", "workload": "data_save", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })
        for backend in ["ascent", "catalyst"]: # Kombyne explicitly removed for Paper 2
            EXPERIMENTS.append({ "id": f"{base_id}_{backend}_data", "paper": "paper2", "type": "inline", "backend": backend, "workload": "data_save", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })
            EXPERIMENTS.append({ "id": f"{base_id}_{backend}_render", "paper": "paper2", "type": "inline", "backend": backend, "workload": "rendering", "sim_nodes": nodes, "grid_size": grid, "parent_id": pid, "total_steps": target_steps })

    # Transit Runs (Weak and Strong Combined)
    for name, nodes, grid, stage_nodes in TRANSIT_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS['run_steps']
        base_id = f"paper2_transit_{name}_N{nodes:04d}"
        
        # ADIOS Data Save Transit (Baseline Transport)
        EXPERIMENTS.append({ "id": f"{base_id}_adios_data", "paper": "paper2", "type": "intransit", "backend": "adios", "workload": "data_save", "sim_nodes": nodes, "stage_nodes": stage_nodes, "grid_size": grid, "stage_pipeline": "adios_data", "parent_id": pid, "total_steps": target_steps })

        # Rendering Transit (Ascent & Catalyst, Kombyne explicitly removed)
        for backend in ["ascent", "catalyst"]: 
            EXPERIMENTS.append({ "id": f"{base_id}_{backend}_render", "paper": "paper2", "type": "intransit", "backend": "adios", "workload": "rendering", "sim_nodes": nodes, "stage_nodes": stage_nodes, "grid_size": grid, "stage_pipeline": f"{backend}_render", "parent_id": pid, "total_steps": target_steps })

    for exp in EXPERIMENTS:
        sim_ranks = exp['sim_nodes'] * SYSTEM_CONFIG['mpi_per_node']
        total_stage_ranks = exp.get('stage_nodes', 0) * SYSTEM_CONFIG['mpi_per_node']
        
        run_output_dir = f"{args.results_dir}/{exp['id']}"
        os.makedirs(run_output_dir, exist_ok=True)
        copied_files = copy_pipeline_files(exp, run_output_dir, args.repo_path)
        generate_settings_json(exp, run_output_dir, copied_files, args)
        total_nodes = exp['sim_nodes'] + exp.get('stage_nodes', 0)
        combined_total_ranks = sim_ranks + total_stage_ranks
        
        # Build command based on type
        command = (CMD_INTRANSIT if exp['type'] == 'intransit' else CMD_INLINE).format(
            sim_nodes=exp['sim_nodes'], 
            sim_ranks=sim_ranks, 
            stage_nodes=exp.get('stage_nodes', 0), 
            stage_ranks=total_stage_ranks,
            total_ranks=combined_total_ranks if exp['type'] == 'intransit' else sim_ranks, 
            grid_size=exp['grid_size'], 
            logging_level=GLOBAL_SETTINGS['logging_level']
        )
        
        # Format the SBATCH template with current configuration
        script_content = SBATCH_TEMPLATE.format(
            id=exp['id'], 
            account=args.account, 
            partition=SYSTEM_CONFIG['partition'], 
            total_nodes=total_nodes,
            total_ranks=combined_total_ranks if exp['type'] == 'intransit' else sim_ranks, 
            mpi_per_node=SYSTEM_CONFIG['mpi_per_node'], 
            omp_threads=SYSTEM_CONFIG['omp_threads'], 
            time_limit=SYSTEM_CONFIG['time_limit'], 
            output_dir=run_output_dir, 
            repo_path=args.repo_path, 
            bin_path=args.bin_path, 
            command=command, 
            catalyst_lib_path=CATALYST_LIB_PATH
        )
        
        with open(f"{args.output_dir}/{exp['id']}.sbat", "w") as f: 
            f.write(script_content)
            
    print(f"Generated {len(EXPERIMENTS)} scripts in {args.output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--bin-path", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-dir", default="generated_scripts")
    parser.add_argument("--account", default=SYSTEM_CONFIG['account'])
    args = parser.parse_args()
    generate_scripts(args)
