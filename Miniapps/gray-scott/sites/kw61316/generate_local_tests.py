import os
import argparse
import json

# =============================================================================
# CONFIGURATION: LOCAL TEST SPECIFICS
# =============================================================================
LOCAL_CONFIG = {
    "sim_ranks": 16,          
    "stage_ranks": 8,        
    "omp_threads": 2,        
    "grid_size": 256
}

GLOBAL_SETTINGS = {
    "run_steps": 10,         
    "plotgap": 2,            
    "logging_level": "INFO"
}

CATALYST_LIB_PATH = "/home/kressjm/packages/paraview-src/build_6.0.0/install/lib/catalyst" 

# =============================================================================
# ADIOS TEMPLATES
# =============================================================================
ADIOS_XML_TEMPLATE = """<?xml version="1.0"?>
<adios-config>
    <io name="SimulationOutput">
        <engine type="{engine_type}">
            <parameter key="RendezvousReaderCount" value="{rendezvous}"/>
            <parameter key="QueueLimit" value="1"/>
            <parameter key="QueueFullPolicy" value="Block"/>
        </engine>
    </io>
</adios-config>
"""

# =============================================================================
# ASCENT TEMPLATES
# =============================================================================
ASCENT_OPTIONS_TEMPLATE = """runtime:
  type: "ascent" 
actions_file: "{actions_file}"
messages: "info" 
timings: "false"      
"""

ASCENT_DATA_TEMPLATE = """
- action: "add_extracts"
  extracts:
    e1:
      type: "relay"
      params:
        path: "data/ascent_data"
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
- action: "add_scenes"
  scenes:
    main_scene:
      plots:
        p1:
          type: "pseudocolor"
          field: "v"
          pipeline: "pl_x"
      renders:
        render1:
          image_width: 2048
          image_height: 2048
          image_prefix: "data/ascent_render_slices"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
"""

ASCENT_VOLUME_TEMPLATE = """
- action: "add_scenes"
  scenes:
    main_scene:
      plots:
        p1:
          type: "volume"
          field: "v"
      renders:
        render1:
          image_width: 2048
          image_height: 2048
          image_prefix: "data/ascent_render_volume"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
"""

ASCENT_ISOSURFACE_TEMPLATE = """
- action: "add_pipelines"
  pipelines:
    pl_iso:
      f1:
        type: "contour"
        params:
          field: "v"
          iso_values: [0.1]
- action: "add_scenes"
  scenes:
    main_scene:
      plots:
        p1:
          type: "pseudocolor"
          field: "v"
          pipeline: "pl_iso"
      renders:
        render1:
          image_width: 2048
          image_height: 2048
          image_prefix: "data/ascent_render_iso"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
"""

# =============================================================================
# CATALYST TEMPLATES
# =============================================================================
CATALYST_DATA_TEMPLATE = """
from paraview import catalyst
from paraview.simple import *

producer = TrivialProducer(registrationName="grid")
writer = CreateExtractor("VTPD", producer, registrationName="VTPD1")
writer.Trigger = "TimeStep"
writer.Writer.FileName = "catalyst_data_{{timestep:06d}}.vtpd"

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    FindSource("grid").UpdatePipeline()

if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions
    SaveExtractsUsingCatalystOptions(options)
"""

CATALYST_RENDER_TEMPLATE = """
from paraview import catalyst
from paraview.simple import *

renderView1 = CreateView("RenderView")
renderView1.Set(
    ViewSize=[2048, 2048], CenterOfRotation=[{center}, {center}, {center}], 
    CameraPosition=[{cam_x}, {cam_y}, {cam_z}], CameraFocalPoint=[{center}, {center}, {center}],
    CameraViewUp=[{cam_up_x}, {cam_up_y}, {cam_up_z}], CameraParallelScale={parallel_scale}
)

producer = TrivialProducer(registrationName="grid")
sliceX = Slice(registrationName='SliceX', Input=producer)
sliceX.SliceType.Origin = [{slice_offset}, {slice_offset}, {slice_offset}]
sliceX.SliceType.Normal = [1.0, 0.0, 0.0]
Show(sliceX, renderView1, 'GeometryRepresentation').Set(Representation='Surface', ColorArrayName=['POINTS', 'v'])

pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_render_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    FindSource("grid").UpdatePipeline()
"""

CATALYST_VOLUME_TEMPLATE = """
from paraview import catalyst
from paraview.simple import *

renderView1 = CreateView("RenderView")
renderView1.Set(
    ViewSize=[2048, 2048], CenterOfRotation=[{center}, {center}, {center}], 
    CameraPosition=[{cam_x}, {cam_y}, {cam_z}], CameraFocalPoint=[{center}, {center}, {center}],
    CameraViewUp=[{cam_up_x}, {cam_up_y}, {cam_up_z}], CameraParallelScale={parallel_scale}
)

producer = TrivialProducer(registrationName="grid")
volDisplay = Show(producer, renderView1)
ColorBy(volDisplay, ('POINTS', 'v'))

vLUT = GetColorTransferFunction("v")
vLUT.Set(RGBPoints=[0.0, 0.23, 0.29, 0.75, 0.5, 0.86, 0.86, 0.86, 1.0, 0.7, 0.01, 0.14], ScalarRangeInitialized=1)

vPWF = GetOpacityTransferFunction("v")
vPWF.Set(Points=[0.0, 0.0, 0.5, 0.0, 1.0, 1.0, 0.5, 0.0], ScalarRangeInitialized=1)

vTF2D = GetTransferFunction2D("v")
vTF2D.Set(Range=[0.0, 1.0, 0.0, 1.0], ScalarRangeInitialized=1)

volDisplay.Set(Representation='Volume', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT, ScalarOpacityFunction=vPWF, TransferFunction2D=vTF2D, ScalarOpacityUnitDistance={ray_step})

pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_volume_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    FindSource("grid").UpdatePipeline()
"""

CATALYST_ISOSURFACE_TEMPLATE = """
from paraview import catalyst
from paraview.simple import *

renderView1 = CreateView("RenderView")
renderView1.Set(
    ViewSize=[2048, 2048], CenterOfRotation=[{center}, {center}, {center}], 
    CameraPosition=[{cam_x}, {cam_y}, {cam_z}], CameraFocalPoint=[{center}, {center}, {center}],
    CameraViewUp=[{cam_up_x}, {cam_up_y}, {cam_up_z}], CameraParallelScale={parallel_scale}
)

producer = TrivialProducer(registrationName="grid")
contour = Contour(registrationName='Contour', Input=producer)
contour.ContourBy = ['POINTS', 'v']
contour.Isosurfaces = [0.1]

isoDisplay = Show(contour, renderView1, 'GeometryRepresentation')
isoDisplay.SetRepresentationType('Surface')
ColorBy(isoDisplay, ('POINTS', 'v'))

pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_iso_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    FindSource("grid").UpdatePipeline()
"""

# =============================================================================
# LOCAL BASH TEMPLATE WITH REGRESSION VALIDATION
# =============================================================================
LOCAL_BASH_TEMPLATE = """#!/bin/bash
export OMP_NUM_THREADS={omp_threads}
export ADIOS2_LOG_LEVEL=OFF
export CATALYST_LIB_DIR="{catalyst_lib_path}"

EXE_SIM="{bin_path}/gray-scott"
EXE_STAGE="{bin_path}/analysis-reader"
OUTPUT_DIR="{output_dir}"

rm -f $OUTPUT_DIR/data/*.sst
mkdir -p $OUTPUT_DIR/data
cd $OUTPUT_DIR

{command}

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ FAILED: MPI execution crashed with exit code $EXIT_CODE"
    exit 1
fi

EXPECTED="{expected_files}"
if [ -n "$EXPECTED" ]; then
    MATCHES=$(ls -1d $EXPECTED 2>/dev/null)
    if [ -z "$MATCHES" ]; then
        echo "❌ FAILED: Expected outputs MISSING ($EXPECTED)"
        exit 1
    fi
    
    for f in $MATCHES; do
        if [ -d "$f" ]; then
            if [ -z "$(ls -A "$f")" ]; then
                echo "❌ FAILED: Directory $f is empty!"
                exit 1
            fi
        elif [ ! -s "$f" ]; then
            echo "❌ FAILED: File $f is empty (0 bytes)!"
            exit 1
        fi
    done
    
    echo "✅ PASSED: Expected outputs found and are non-empty ($EXPECTED)"
    exit 0
else
    echo "✅ PASSED: Execution successful (No files expected)"
    exit 0
fi
"""

CMD_INLINE = "mpiexec -n {sim_ranks} $EXE_SIM --logging-level={logging_level} --settings-file=$OUTPUT_DIR/settings.json\n"
CMD_INTRANSIT = "mpiexec -n {sim_ranks} $EXE_SIM --logging-level={logging_level} --settings-file=$OUTPUT_DIR/settings.json --mpi-split-color=1 : -n {stage_ranks} $EXE_STAGE --settings $OUTPUT_DIR/settings-stage.json --file $OUTPUT_DIR/data/grayScott --block-mode repartition --engine SST --mpi-split-color=2 --adios-verbose 0\n"

def get_expected_files(exp):
    if exp['backend'] == 'none':
        return ""
    elif exp['backend'] == 'baseline':
        return "data/*.pvti"
    elif exp['backend'] == 'adios':
        if exp['type'] == 'intransit':
            return "data/grayScott_staged*"
        else:
            return "data/grayScott*"
    elif exp['backend'] in ['ascent', 'catalyst']:
        if exp['workload'] == 'data':
            if exp['backend'] == 'ascent':
                return "data/ascent_data*"
            else:
                return "data/*.vtpd"
        else:
            return "data/*.png"
    return ""

def generate_settings_json(exp, output_dir, copied_files):
    config = {
        "L": LOCAL_CONFIG['grid_size'],        
        "Du": 0.2, "Dv": 0.1, "F": 0.03, "k": 0.0545, "dt": 2.0, 
        "noise": 0.1, 
        "steps": GLOBAL_SETTINGS['run_steps'],                  
        "burn_in_steps": 0, 
        "plotgap": GLOBAL_SETTINGS['plotgap'],            
        "output_file_name": "data/grayScott", 
        "output_type": "adhoc",                  
        "mesh_type": "image",                    
        "checkpoint": False, 
        "checkpoint_freq": 0, 
        "checkpoint_output": "",
        "restart": False, 
        "restart_input": "", 
        "catalyst_script_path": "", 
        "catalyst_lib_path": CATALYST_LIB_PATH,
        "kombynelite_script_path": "",
        "adios_config": f"{output_dir}/adios2.xml", 
        "adios_span": exp.get('span', False), 
        "adios_memory_selection": exp.get('mem', False)
    }

    if exp['type'] == 'intransit':
        config["output_type"] = "adios"
        config_stage = config.copy()
        config_stage["output_file_name"] = "data/grayScott_staged"
        
        stage_backend = exp['backend']
        if stage_backend == "catalyst":
            config_stage["output_type"] = "catalyst_insitu"
            config_stage["catalyst_script_path"] = f"{output_dir}/" + os.path.basename(copied_files.get('pipeline', ''))
        elif stage_backend == "ascent":
            config_stage["output_type"] = "ascent"
            config_stage["ascent_options"] = f"{output_dir}/ascent_options.yaml" 
        else:
            config_stage["output_type"] = "adios_writer"
            
        with open(f"{output_dir}/settings-stage.json", "w") as f:
            json.dump(config_stage, f, indent=4)
    else:
        if exp['backend'] == 'adios': config["output_type"] = "adios"
        elif exp['backend'] == 'ascent': 
            config["output_type"] = "ascent"
            config["ascent_options"] = f"{output_dir}/ascent_options.yaml"
        elif exp['backend'] == 'catalyst':
            config["output_type"] = "catalyst_insitu"
            config["catalyst_script_path"] = copied_files.get('pipeline', '')
        elif exp['backend'] == 'baseline':
            config["output_type"] = "pvti"
            config["output_file_name"] = "data/grayScott-%04ts.vti"
        elif exp['backend'] == 'none':
            config["output_type"] = "none"

    with open(f"{output_dir}/settings.json", "w") as f:
        json.dump(config, f, indent=4)

def copy_pipeline_files(exp, output_dir):
    files_to_copy = {}
    engine = "SST" if exp['type'] == 'intransit' else "BP5"
    rendezvous = 1 if exp['type'] == 'intransit' else 0
    with open(f"{output_dir}/adios2.xml", "w") as f:
        f.write(ADIOS_XML_TEMPLATE.format(engine_type=engine, rendezvous=rendezvous))

    if exp['backend'] in ['baseline', 'adios', 'none']: return files_to_copy

    mesh_spacing = 0.1
    physical_L = float(LOCAL_CONFIG['grid_size']) * mesh_spacing
    center_val = physical_L / 2.0
    slice_offset_val = center_val + (mesh_spacing * 6.5)
    cam_up_x, cam_up_y, cam_up_z = 0.206668, 0.933382, -0.293403
    ray_step = float(mesh_spacing) * 1.73205

    if exp['backend'] == 'ascent':
        cam_x, cam_y, cam_z = center_val - (physical_L * 1.85), center_val + (physical_L * 1.10), center_val + (physical_L * 1.85)
        parallel_scale = physical_L * 1.60
    else:
        cam_x, cam_y, cam_z = center_val - (physical_L * 2.22), center_val + (physical_L * 1.32), center_val + (physical_L * 2.22)
        parallel_scale = physical_L * 2.21

    fmt_args = {
        'cam_x': cam_x, 'cam_y': cam_y, 'cam_z': cam_z, 
        'center': center_val, 'cam_up_x': cam_up_x, 'cam_up_y': cam_up_y, 'cam_up_z': cam_up_z, 
        'slice_offset': slice_offset_val, 'parallel_scale': parallel_scale, 'ray_step': ray_step
    }

    dst_action = os.path.join(output_dir, "pipeline_script." + ("yaml" if exp['backend'] == 'ascent' else "py"))
    
    if exp['backend'] == 'ascent':
        if exp['workload'] == 'data': template = ASCENT_DATA_TEMPLATE
        elif exp['workload'] == 'render': template = ASCENT_RENDER_TEMPLATE
        elif exp['workload'] == 'volume': template = ASCENT_VOLUME_TEMPLATE
        elif exp['workload'] == 'isosurface': template = ASCENT_ISOSURFACE_TEMPLATE
        
        with open(dst_action, "w") as f: f.write(template.format(**fmt_args))
        with open(f"{output_dir}/ascent_options.yaml", "w") as f: f.write(ASCENT_OPTIONS_TEMPLATE.format(actions_file="pipeline_script.yaml"))
        
    elif exp['backend'] == 'catalyst':
        if exp['workload'] == 'data': template = CATALYST_DATA_TEMPLATE
        elif exp['workload'] == 'render': template = CATALYST_RENDER_TEMPLATE
        elif exp['workload'] == 'volume': template = CATALYST_VOLUME_TEMPLATE
        elif exp['workload'] == 'isosurface': template = CATALYST_ISOSURFACE_TEMPLATE
        
        with open(dst_action, "w") as f: f.write(template.format(**fmt_args))
        
    files_to_copy['pipeline'] = dst_action
    return files_to_copy

def generate_scripts(args):
    os.makedirs(args.test_dir, exist_ok=True)
    EXPERIMENTS = []
    
    WORKLOADS = ["data", "render", "volume", "isosurface"]

    # 1. Base Inline Tests
    EXPERIMENTS.append({"id": "inline_none", "type": "inline", "backend": "none", "workload": "none"})
    EXPERIMENTS.append({"id": "inline_baseline", "type": "inline", "backend": "baseline", "workload": "data"})
    
    # 2. ADIOS Data Sweeps (Inline: span T/F, mem T/F)
    for span in [False, True]:
        for mem in [False, True]:
            span_str = "spanT" if span else "spanF"
            mem_str = "memT" if mem else "memF"
            EXPERIMENTS.append({
                "id": f"inline_adios_data_{span_str}_{mem_str}", 
                "type": "inline", "backend": "adios", "workload": "data",
                "span": span, "mem": mem
            })

    # 3. ADIOS Data Sweeps (Intransit: span MUST be False for SST, mem T/F)
    for mem in [False, True]:
        mem_str = "memT" if mem else "memF"
        EXPERIMENTS.append({
            "id": f"intransit_adios_data_spanF_{mem_str}", 
            "type": "intransit", "backend": "adios", "workload": "data",
            "span": False, "mem": mem
        })

    # 4. Ascent & Catalyst Pipeline Sweeps
    for backend in ["ascent", "catalyst"]:
        for wl in WORKLOADS:
            # Inline Sweep (No ADIOS flags needed)
            EXPERIMENTS.append({
                "id": f"inline_{backend}_{wl}", 
                "type": "inline", "backend": backend, "workload": wl
            })
            # Intransit Sweep (span MUST be False for SST, mem T/F)
            for mem in [False, True]:
                mem_str = "memT" if mem else "memF"
                EXPERIMENTS.append({
                    "id": f"intransit_{backend}_{wl}_spanF_{mem_str}", 
                    "type": "intransit", "backend": backend, "workload": wl,
                    "span": False, "mem": mem
                })

    generated_ids = []

    for exp in EXPERIMENTS:
        run_output_dir = os.path.abspath(f"{args.test_dir}/{exp['id']}")
        os.makedirs(run_output_dir, exist_ok=True)
        
        copied_files = copy_pipeline_files(exp, run_output_dir)
        generate_settings_json(exp, run_output_dir, copied_files)
        
        command = (CMD_INTRANSIT if exp['type'] == 'intransit' else CMD_INLINE).format(
            sim_ranks=LOCAL_CONFIG['sim_ranks'], 
            stage_ranks=LOCAL_CONFIG['stage_ranks'],
            logging_level=GLOBAL_SETTINGS['logging_level']
        )
        
        script_content = LOCAL_BASH_TEMPLATE.format(
            id=exp['id'], 
            omp_threads=LOCAL_CONFIG['omp_threads'], 
            output_dir=run_output_dir, 
            bin_path=os.path.abspath(args.bin_path), 
            command=command, 
            catalyst_lib_path=CATALYST_LIB_PATH,
            expected_files=get_expected_files(exp)
        )

        script_path = os.path.join(run_output_dir, "run.sh")
        with open(script_path, "w") as f: 
            f.write(script_content)
        os.chmod(script_path, 0o755) 
        generated_ids.append(exp['id'])
            
   # --- Generate Performance Plotter Script ---
    plot_script_path = os.path.join(args.test_dir, "plot_performance.sh")
    with open(plot_script_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write('echo "==========================================\"\n')
        f.write('echo "Generating Performance Visualizations...\"\n')
        f.write('echo "==========================================\"\n\n')
        
        f.write("UNIVERSAL_PARSER=\"python3 ../scripts/analyze_timers.py\"\n")
        f.write("AGGREGATOR=\"python3 ../scripts/aggregate_timers.py\"\n")
        f.write("PLOT_DIR=\"performance_summary_plots\"\n")
        f.write("mkdir -p $PLOT_DIR\n\n")
        
        f.write("for test_dir in */ ; do\n")
        f.write("    if [ \"$test_dir\" == \"$PLOT_DIR/\" ]; then continue; fi\n\n")
        f.write("    TEST_NAME=$(basename \"$test_dir\")\n")
        f.write("    if [ -d \"${test_dir}writer_timers\" ]; then\n")
        f.write("        $UNIVERSAL_PARSER --input-dir \"${test_dir}writer_timers\" --output-prefix \"$PLOT_DIR/${TEST_NAME}_sim\" --title \"$TEST_NAME Sim\" > /dev/null\n")
        f.write("    fi\n")
        f.write("    if [ -d \"${test_dir}reader_timers\" ]; then\n")
        f.write("        $UNIVERSAL_PARSER --input-dir \"${test_dir}reader_timers\" --output-prefix \"$PLOT_DIR/${TEST_NAME}_analysis\" --title \"$TEST_NAME Analysis\" > /dev/null\n")
        f.write("    fi\n")
        f.write("done\n")
        
        f.write('echo "--> Generating Master Aggregation Plots..."\n')
        f.write("$AGGREGATOR --test-dir . --output-prefix \"$PLOT_DIR/00_MASTER\"\n\n")
        
        f.write('echo -e "\\n✅ All plots (Stacked, Heartbeat, Memory, and Master) saved to local_tests/$PLOT_DIR/"\n')
    os.chmod(plot_script_path, 0o755)

    # --- Generate Master Regression Run Script ---
    master_script_path = os.path.join(args.test_dir, "run_all.sh")
    with open(master_script_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write('echo "==========================================\"\n')
        f.write('echo "Running FULL sweep of local functionality tests...\"\n')
        f.write('echo "==========================================\"\n\n')
        f.write("BASE_DIR=$(pwd)\n")
        f.write("PASSED=0\n")
        f.write("FAILED=0\n")
        f.write("FAILED_TESTS=\"\"\n\n")
        
        for exp_id in generated_ids:
            f.write("echo \"\"\n")
            f.write(f"echo \"---> Starting test: {exp_id}\"\n")
            f.write(f"cd {exp_id}\n")
            f.write("./run.sh\n")
            f.write("if [ $? -eq 0 ]; then\n")
            f.write("    PASSED=$((PASSED+1))\n")
            f.write("else\n")
            f.write("    FAILED=$((FAILED+1))\n")
            f.write(f"    FAILED_TESTS=\"$FAILED_TESTS \\n  - {exp_id}\"\n")
            f.write("fi\n")
            f.write("cd $BASE_DIR\n")
            
        f.write("\necho \"\"\n")
        f.write("echo \"==========================================\"\n")
        f.write("echo \"              TEST SUMMARY                \"\n")
        f.write("echo \"==========================================\"\n")
        f.write("echo \"Passed: $PASSED\"\n")
        f.write("echo \"Failed: $FAILED\"\n\n")

        f.write("echo \"Triggering performance visualization for available data...\"\n")
        f.write("./plot_performance.sh\n")

        f.write("if [ $FAILED -gt 0 ]; then\n")
        f.write("    echo -e \"\\n❌ FAILED TESTS:$FAILED_TESTS\"\n")
        f.write("    exit 1\n")
        f.write("else\n")
        f.write(f"    echo -e \"\\n✅ All {len(EXPERIMENTS)} tests completed successfully! 🎉\"\n")
        f.write("fi\n")
    
    os.chmod(master_script_path, 0o755)
    print(f"Generated {len(EXPERIMENTS)} standalone regression tests, 'plot_performance.sh', and 'run_all.sh' in {args.test_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin-path", required=True)
    parser.add_argument("--test-dir", default="local_tests")
    args = parser.parse_args()
    generate_scripts(args)
