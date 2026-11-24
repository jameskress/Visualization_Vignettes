import math
import os
import re
import xml.etree.ElementTree as ET
import argparse
import hashlib
import json
import shutil
import subprocess

# =============================================================================
# CONFIGURATION: SYSTEM SPECIFICS (Shaheen III)
# =============================================================================
SYSTEM_CONFIG = {
    "account": "k01",
    "partition": "workq",
    "constraints": "",
    "cores_per_node": 192,
    "mpi_per_node": 64,  # 64 ranks for Simulation
    "omp_threads": 3,  # 3 threads for Simulation
    "time_limit": "2:00:00",
}

# =============================================================================
# GLOBAL SETTINGS
# =============================================================================
GLOBAL_SETTINGS = {
    "init_steps": 65000,
    "init_burn_in": 0,
    "run_steps": 41,  # Paper 2 runs
    "paper1_run_steps": 501,  # Paper 1 (WOIV 2026), unchanged (#71)
    "plotgap": 20,
    "output_type": "adhoc",
    "logging_level": "INFO",
}

INIT_NODE_MAP = {1024: 8, 2048: 64, 4096: 1024, 8192: 2048}

# Repeats: every measured run (not Paper 1, not the initialisations) is
# generated REPEATS times as <id>_r01 ... so one abnormal run (a noisy node,
# a busy file system) shows up against the others; corpus_index.py reports
# each configuration's median and flags outliers. --repeats overrides it.
REPEATS = 3
# Shaheen's workq caps a job at 2048 nodes; larger jobs ask for QoS ex
# (up to 4608 nodes). James's standing OK covers about 3500 nodes, and the
# 3536-node 3328 + 208 layout (tested 21 Nov 2026); above that every run
# needs his approval, which orchestrate.py enforces.
WORKQ_MAX_NODES = 2048
LARGE_RUN_QOS = "ex"
# Start-up (MPI wire-up, SST connection, Catalyst/Python import) grows with
# the node count; runs above the workq cap get at least this long.
LARGE_RUN_MIN_TIME = "1:00:00"

# =============================================================================
# DEFINITIONS (Strong/Weak Scaling & New Sweeps)
# =============================================================================
# 2048 and 3072 need --qos=ex (workq caps a job at 2048 nodes); 3072 is
# exactly 12 of Shaheen's 256-node dragonfly groups. Node counts that are not
# a power of two split L unevenly by at most one cell per rank (#12).
STRONG_SCALING_NODES = [256, 1024, 2048, 3072, 3328, 4096]
STRONG_GRID = 4096

WEAK_SCALING_CONFIGS = [(8, 1024), (64, 2048), (512, 4096), (4096, 8192)]

TRANSIT_CONFIGS = [
    ("small", 64, 2048, 4),  # Weak Scaling Start (16:1)
    ("compressed", 512, 4096, 32),  # Strong Scaling Start (16:1)
    ("hero", 4096, 8192, 256),  # Weak/Strong Scaling End (16:1)
    # 8192^3 strong scaling below the hero run, within the ~3500-node limit
    # James allows without asking (21 Nov 2026): 12 dragonfly groups + 192.
    ("hero3072", 3072, 8192, 192),  # 16:1
]

TRANSIT_SWEEP_CONFIGS = [
    ("sweep_64", 4096, 8192, 64),  # 64:1
    ("sweep_128", 4096, 8192, 128),  # 32:1
    # 256 staging nodes is the "hero" run above; the sweep reuses it.
    ("sweep_384", 4096, 8192, 384),  # ~10:1
]

# Ascent volume samples per cell crossed by a ray (a cost/quality knob;
# --volume-samples-per-cell overrides it).
VOLUME_SAMPLES_PER_CELL = 9.0
# How the in transit reader splits the domain among its ranks: "brick" (a 3D
# grid aligned with the simulation's blocks, so each reader reads whole
# writer blocks from far fewer writers; the default since 16 Nov 2026) or
# "slab" (even slabs along the slowest axis, the original layout of every
# earlier run). With the shared planes exchanged, brick was faster at every
# size and pipeline measured, for both backends, and fits the Catalyst
# isosurface at 512 + 32 that runs out of memory with slabs (sites/shaheen/
# README.md, "Reader decomposition"). --reader-decomposition overrides it.
READ_DECOMPOSITION = "brick"
# How each reader piece gets the plane it shares with the next piece:
# "exchange" (read only the owned box, take the plane from the neighbouring
# reader over MPI) or "read" (read it from the writers, as before; on a brick
# ADIOS2 then sends a whole writer block for each strided plane).
# --reader-shared-planes overrides it.
READER_SHARED_PLANES = "exchange"
# Diagnostics for the SST write path (ADIOS2 #5272), both off by default:
# --adios-endstep-barrier puts an MPI_Barrier before each EndStep, timed as
# the writer's endstep_barrier, so its io timer is the engine's own time;
# --adios-queue-full-policy Discard lets the writer drop steps instead of
# blocking on a full queue, to take the readers out of its EndStep.
ADIOS_ENDSTEP_BARRIER = False
QUEUE_FULL_POLICY = "Block"

# #72 step 1: SST transport x reader x launch x fan-in, small and short.
# Fan-in is in tasks (64 simulation and 8 reader ranks per node):
# 8 + 4 nodes is 512:32 = 16:1, 64 + 4 nodes is 4096:32 = 128:1.
XPORT_CONFIGS = [("f016", 8, 1024, 4), ("f128", 64, 2048, 4)]
XPORT_TRANSPORTS = ["RDMA", "MPI"]
XPORT_LAUNCHES = ["mpmd", "steps"]  # one MPMD srun, or two srun steps sharing a job VNI
XPORT_RUN_STEPS = 101  # 6 outputs at plotgap 20
XPORT_TIME_LIMIT = "0:30:00"  # a hang must not hold the nodes for hours

# #72 step 2: scale the step 1 survivor (RDMA) at 4096^3 from the existing
# checkpoint. Fan-in 128:1 in tasks (16 simulation nodes per staging node),
# which ran cleanly in step 1. 1024 + 64 is the largest power-of-two
# simulation that fits the per-user node cap (about 2048) with its readers.
# Extended past the 2048-node per-job cap with --qos=ex (21 Nov 2026).
SCALE_CONFIGS = [
    (256, 16),
    (512, 32),
    (1024, 64),
    (2048, 128),
    (3072, 192),
    # 13 dragonfly groups + 208 readers = 3536 nodes, just over the ~3500
    # James allows; it ran cleanly on 21 Nov 2026 (job 16126972), so he
    # accepts it.
    (3328, 208),
]  # (simulation, staging) nodes
SCALE_GRID = 4096
SCALE_LAUNCHES = ["mpmd", "steps"]
SCALE_RUN_STEPS = 101
SCALE_TIME_LIMIT = "0:45:00"

# ADIOS2 transport at scale (Paper 2, ADIOS2 #5272 follow-up): the readonly
# reader backend, which reads each step and does nothing else, so the times
# are SST's alone. (simulation nodes, staging nodes, SST QueueLimit).
# 1920 + 128 (122880 writers) is the largest real layout within the 2048-node
# per-job cap; the whole machine waits for a maintenance window.
ADIOS_SWEEP_GRID = 4096
ADIOS_SWEEP_CONFIGS = [
    (256, 16, 1),  # scaling at 128 writers per reader
    (512, 32, 1),
    (1024, 64, 1),
    (1920, 128, 1),
    (2048, 128, 1),  # --qos=ex from here (21 Nov 2026)
    (3072, 192, 1),
    (3328, 208, 1),  # 3536 nodes, tested 21 Nov 2026 (job 16126972)
    (1024, 16, 1),  # reader count at 1024 simulation nodes
    (1024, 32, 1),
    (1024, 128, 1),
    (512, 32, 2),  # QueueLimit 2 against 1
    (1920, 128, 2),
]
ADIOS_SWEEP_RUN_STEPS = 101
ADIOS_SWEEP_TIME_LIMIT = "0:45:00"

# Reader cost study: each in transit pipeline (slices, volume, isosurface)
# for Ascent and Catalyst, RDMA, one MPMD srun, at the f128 size and along
# the step 2 scaling ladder (sites/shaheen/README.md, "In transit reader
# costs"). (name, simulation nodes, grid, staging nodes).
PIPE_CONFIGS = [
    ("f128", 64, 2048, 4),
    ("s256", 256, 4096, 16),
    ("s512", 512, 4096, 32),
    ("s1024", 1024, 4096, 64),
    ("s2048", 2048, 4096, 128),  # --qos=ex (21 Nov 2026)
    ("s3072", 3072, 4096, 192),
    ("s3328", 3328, 4096, 208),  # 3536 nodes
]
PIPE_RUN_STEPS = 101  # 6 outputs at plotgap 20
PIPE_TIME_LIMIT = "0:45:00"
# Ascent's per-filter timings (ascent_options.yaml `timings`); off by default
# because Ascent writes one file per rank. --ascent-timings turns it on.
ASCENT_TIMINGS = False

# Run the in transit reader on both hardware threads of its 24 cores (48
# OpenMP threads) instead of one. At f128, Ascent: isosurface -0.54 s/step,
# volume -0.12, slices -0.05; Catalyst: isosurface -0.52, slices -0.05,
# volume -0.03, frames bit-identical (sites/shaheen/README.md, "In transit
# reader costs"). On by default for testing (James, 16 Nov 2026);
# --no-reader-smt turns it off. Paper 1 jobs never get it (reader_smt).
READER_SMT = True

# Ascent 0.9.6 renders in 1024 x 1024 tiles by default. At our 2048^2 images
# that only adds cost: with brick, plane exchange and SMT, the isosurface
# took 10.08 -> 5.59 s/step untiled at 512 + 32 nodes and 5.14 -> 2.90 at
# 1024 + 64, slices 5 to 7% less, volume unchanged; compositing is the same
# and only silhouette-edge pixels differ (sites/shaheen/README.md, "In
# transit reader costs"). So every Paper 2 Ascent render turns it off and the
# run's settings record it (ascent_tiled_rendering); Paper 1's templates stay
# as they ran (#71). --ascent-tiled-rendering turns tiling back on.
ASCENT_TILED_RENDERING = False

# The in transit reader's allocator: never mmap, never trim. The job-wide
# MALLOC_MMAP_THRESHOLD_ (32 MiB) makes every larger block an mmap that is
# unmapped when freed, so each step the reader faulted the same memory in
# again: the Ascent isosurface took 7.8 M minor faults (about 30 GB) and
# 41 s of system CPU per rank per step, the slices about 2 GB. With these the
# heap keeps freed blocks for the next step: isosurface 8.7 -> 6.5 s/step and
# slices 3.8 -> 3.0 s/step at f128, at the cost of a higher RSS
# (sites/shaheen/README.md, "In transit reader costs"). Every backend's
# reader gets it (reader_env), so comparisons stay fair; the simulation does
# not, and neither do Paper 1's jobs, which keep the setup they ran with (#71).
READER_MALLOC_ENV = "MALLOC_MMAP_MAX_=0 MALLOC_TRIM_THRESHOLD_=137438953472"

# Catalyst implementation loaded by every job (catalyst_lib_path, and its
# lib/ on LD_LIBRARY_PATH). --bin-path must be a Gray-Scott build against the
# same ParaView: the jobs load both into one process. Runs written before
# 17 Nov 2026 used the 6.0.1 superbuild (LEGACY_CATALYST_LIB_PATH).
LEGACY_CATALYST_LIB_PATH = "/scratch/kressjm/Visualization_Vignettes/software/paraview-build/install/lib/catalyst"
CATALYST_LIB_PATH = "/scratch/kressjm/Visualization_Vignettes/software/paraview-6.2.1-gcc13-build/install/lib/catalyst"

# --catalyst-stage: copy ParaView's lib/ to node-local disk on the reader
# nodes before the run, and load Catalyst from there. The first Catalyst
# step is mostly Python and VTK paging their .so files in from Lustre: at
# 512 + 32 nodes the slices' step 0 took 23.4 to 26.4 s from Lustre and 2.8
# to 2.9 s staged, the isosurface's 44.7 to 51.7 s and 22.1 to 23.7 s, with
# identical frames (sites/shaheen/README.md, "Catalyst node-local staging").
# catalyst_lib_path stays the Lustre install, which names the build the run
# used; the stage is recorded beside it (catalyst_stage). The reader must be
# built with GS_READER_RUNPATH=ON, or its DT_RPATH keeps loading part of
# ParaView from Lustre. The tarball is made once per ParaView install by
# sites/shaheen/build-catalyst-stage.sh. Methods: "tar" (each reader node
# reads the tarball from Lustre), "sbcast" (Slurm fans it out to the reader
# nodes), "auto" (tar below CATALYST_STAGE_SBCAST_MIN_NODES reader nodes,
# sbcast from there), "off". At 32 reader nodes tar took 1.2 to 3.9 s and
# sbcast 8.3 to 8.8 s; tar reads the tarball once per node from Lustre and
# sbcast fans it out in a tree, so sbcast should win at some larger count.
# The threshold is an estimate until it is timed at 64 to 208 reader nodes.
CATALYST_STAGE = "off"
CATALYST_STAGE_SBCAST_MIN_NODES = 128
# One directory per job, so a copy left behind by a job that was killed is
# never taken for this job's.
CATALYST_STAGE_DIR = "/tmp/gs-catalyst-$SLURM_JOB_ID"
# Darshan (I/O characterization) for --telemetry; --darshan-prefix overrides,
# --no-darshan leaves it out. Built by software/build-darshan-3.4.7.sh.
DARSHAN_PREFIX = (
    "/scratch/kressjm/Visualization_Vignettes/software/darshan-3.4.7-install"
)

PIPELINE_FILES = {
    "adios_xml": "configs/adios2_configs/adios2.xml",
    "ascent_opts": "configs/ascent_scripts/ascent_options.yaml",
    "ascent_data": "configs/ascent_scripts/ascent-save-data.yaml",
    "catalyst_data": "configs/catalyst_scripts/catalyst-save-data.py",
    "kombyne_data": "configs/kombyne_scripts/kombyne-save-data.yaml",
}

# =============================================================================
# TEMPLATES (Data, Slices, Volume, Isosurface)
# =============================================================================
ADIOS_XML_TEMPLATE = """<?xml version="1.0"?>
<adios-config>
    <io name="SimulationOutput">
        <engine type="{engine_type}">
            <parameter key="verbose" value="0"/>
            <parameter key="RendezvousReaderCount" value="{rendezvous}"/>
            <parameter key="QueueLimit" value="{queue_limit}"/>
            <parameter key="QueueFullPolicy" value="{queue_full_policy}"/>
            <parameter key="DataTransport" value="{data_transport}"/>
            <parameter key="ControlModule" value="epoll"/>
            <parameter key="OpenTimeoutSecs" value="600.0"/>
            <parameter key="AsyncWrite" value="false"/>
            <parameter key="NumAggregators" value="{sim_aggregators}"/>
        </engine>
    </io>
    <io name="AnalysisInput">
        <!-- The in transit reader's side of SimulationOutput. ControlModule
             must be epoll here too: with select() a reader connected to more
             than 1023 writers hangs (ADIOS2 #5272). -->
        <engine type="{engine_type}">
            <parameter key="verbose" value="0"/>
            <parameter key="ControlModule" value="epoll"/>
            <parameter key="DataTransport" value="{data_transport}"/>
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
    <io name="AnalysisOutput">
        <engine type="BP5">
            <parameter key="verbose" value="0"/>
            <parameter key="NumAggregators" value="{stage_aggregators}"/>
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
messages: "info"
timings: "{timings}"
"""

# --- ASCENT TEMPLATES ---
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
          tiled_rendering: "{tiled_rendering}"
          annotations: "on"
          image_prefix: "data/ascent_render_slices"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
            zoom: 1.7
"""

ASCENT_VOLUME_TEMPLATE = """
- action: "add_scenes"
  scenes:
    main_scene:
      plots:
        p1:
          type: "volume"
          field: "v"
          samples: {volume_samples}
          # Same colours, opacity ramp and range as CATALYST_VOLUME_TEMPLATE.
          min_value: 0.0
          max_value: 1.0
          color_table:
            control_points:
              - {{type: "rgb", position: 0.0, color: [0.231, 0.298, 0.753]}}
              - {{type: "rgb", position: 0.5, color: [0.865, 0.865, 0.865]}}
              - {{type: "rgb", position: 1.0, color: [0.706, 0.016, 0.150]}}
              - {{type: "alpha", position: 0.0, alpha: 0.0}}
              - {{type: "alpha", position: 1.0, alpha: 1.0}}
      renders:
        render1:
          image_width: 2048
          image_height: 2048
          tiled_rendering: "{tiled_rendering}"
          image_prefix: "data/ascent_render_volume"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
            zoom: 1.7
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
          tiled_rendering: "{tiled_rendering}"
          image_prefix: "data/ascent_render_iso"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
            zoom: 1.7
"""

# --- CATALYST TEMPLATES ---
# Stage timers for the Paper 2 Catalyst scripts. The reader's Vis_Time is one
# number for all of catalyst_execute; ParaView logs each stage of it (the
# Blueprint check, the filters, the render, IceT's local render and
# composite, the PNG write) as timed scopes. With GS_CATALYST_TIMERS=1 and
# the PARAVIEW_LOG_*_VERBOSITY categories on (CATALYST_READER_ENV and
# CATALYST_TIMER_ENV), each reader rank writes that log to
# catalyst_timers/rank_<r>.log, and catalyst_timers.py reduces it.
# Prepended to each template, so its braces are doubled for str.format.
CATALYST_TIMERS_PROLOGUE = """
import os as _gs_os
if _gs_os.environ.get("GS_CATALYST_TIMERS") == "1":
    from vtkmodules.vtkCommonCore import vtkLogger as _gs_vtkLogger
    from vtkmodules.vtkParallelCore import vtkMultiProcessController as _gs_mpc
    _gs_rank = _gs_mpc.GetGlobalController().GetLocalProcessId()
    _gs_os.makedirs("catalyst_timers", exist_ok=True)
    _gs_vtkLogger.LogToFile(
        f"catalyst_timers/rank_{{_gs_rank:05d}}.log",
        _gs_vtkLogger.TRUNCATE,
        _gs_vtkLogger.VERBOSITY_INFO,
    )
"""

CATALYST_RENDER_TEMPLATE = (
    CATALYST_TIMERS_PROLOGUE
    + """
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
    StereoType="Crystal Eyes",
    EnableRayTracing=1,
    BackEnd="OSPRay raycaster"
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

# Pinned colour range (v runs from 0 to about 0.5). Rescaling to the data
# range each step made each rank colour its own piece with its own range:
# in transit the reader's ranks hold different slabs, so the colours, and
# the image, changed with the rank count (#42; docs/in-situ-backends.md).
vLUT.AutomaticRescaleRangeMode = "Never"
vLUT.RescaleTransferFunction(0.0, 0.5)
vPWF.RescaleTransferFunction(0.0, 0.5)

Show(sliceX, renderView1, 'GeometryRepresentation').Set(Representation='Surface', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT)
Show(sliceY, renderView1, 'GeometryRepresentation').Set(Representation='Surface', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT)
sliceZDisplay = Show(sliceZ, renderView1, 'GeometryRepresentation')
sliceZDisplay.Set(Representation='Surface', ColorArrayName=['POINTS', 'v'], LookupTable=vLUT)
sliceZDisplay.SetScalarBarVisibility(renderView1, True)

pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_render_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.EnableCatalystLive = 0
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    pass

if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions
    SaveExtractsUsingCatalystOptions(options)
"""
)

CATALYST_VOLUME_TEMPLATE = (
    CATALYST_TIMERS_PROLOGUE
    + """
# Volume of v over the full grid, comparable with ASCENT_VOLUME_TEMPLATE: the
# same data (no resampling), image size and colour range (pinned to 0..1).
# Rendered by VTK's volume ray caster, on the CPU through Mesa, not by OSPRay
# as the slice and isosurface templates are: ParaView 6.2's OSPRay path does
# not draw a volume of the partitioned image data Catalyst hands it, so with
# OSPRay every frame showed only the background, axes and scalar bar
# (sites/shaheen/README.md, "Catalyst volume images"). Drawing it with OSPRay
# would need the data resampled to one image.
# The producer is rendered directly: a GhostCells layer under a volume shows
# as cracks (docs/in-situ-backends.md, Catalyst).
from paraview import catalyst
from paraview.simple import *

_DisableFirstRenderCameraReset()

renderView1 = CreateView("RenderView")
renderView1.Set(
    ViewSize=[2048, 2048],
    CenterOfRotation=[{center}, {center}, {center}],
    CameraPosition=[{cam_x}, {cam_y}, {cam_z}],
    CameraFocalPoint=[{center}, {center}, {center}],
    CameraViewUp=[{cam_up_x}, {cam_up_y}, {cam_up_z}],
    CameraParallelScale={parallel_scale},
    EnableRayTracing=0,
)
SetActiveView(None)
layout1 = CreateLayout(name="Layout #1")
layout1.AssignView(0, renderView1)
layout1.SetSize(2048, 2048)
SetActiveView(renderView1)

producer = TrivialProducer(registrationName="grid")
volDisplay = Show(producer, renderView1)
volDisplay.SetRepresentationType('Volume')
ColorBy(volDisplay, ('POINTS', 'v'))

vLUT = GetColorTransferFunction("v")
vLUT.ApplyPreset("Cool to Warm", True)
vLUT.AutomaticRescaleRangeMode = "Never"
vLUT.RescaleTransferFunction(0.0, 1.0)
vPWF = GetOpacityTransferFunction("v")
vPWF.Points = [0.0, 0.0, 0.5, 0.0, 1.0, 1.0, 0.5, 0.0]
vPWF.RescaleTransferFunction(0.0, 1.0)
volDisplay.Set(ColorArrayName=['POINTS', 'v'], LookupTable=vLUT, ScalarOpacityFunction=vPWF)
volDisplay.SetScalarBarVisibility(renderView1, True)

pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_volume_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.EnableCatalystLive = 0
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    pass

if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions
    SaveExtractsUsingCatalystOptions(options)
"""
)

CATALYST_ISOSURFACE_TEMPLATE = (
    CATALYST_TIMERS_PROLOGUE
    + """
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
    StereoType="Crystal Eyes",
    EnableRayTracing=1,
    BackEnd="OSPRay raycaster"
)
SetActiveView(None)
layout1 = CreateLayout(name="Layout #1")
layout1.AssignView(0, renderView1)
layout1.SetSize(2048, 2048)
SetActiveView(renderView1)

producer = TrivialProducer(registrationName="grid")

# Only v (and the reader's ghost flags) goes on: GhostCells copies every array
# it is given, and u is not drawn. The image is unchanged, bit for bit, and
# the step 6 s faster at 64 + 4 nodes (sites/shaheen/README.md, "Catalyst
# reader performance").
vOnly = PassArrays(registrationName='VOnly', Input=producer)
vOnly.PointDataArrays = ['v', 'vtkGhostType']
vOnly.CellDataArrays = []
# Contour needs ghost cells on every side of a block, or each block's high
# face gets one-sided normals (docs/in-situ-backends.md, Catalyst).
ghostCells = GhostCells(registrationName='GhostCells', Input=vOnly)
# Flying edges, the multithreaded contour that VTK-m (Ascent) also uses.
# ParaView's Contour runs serial synchronized templates on image data: its
# FastMode switch, which would pick flying edges, is not passed on in
# ParaView 6.0 (vtkPVContourFilter::ContourUsingSuperclass). Same normals and
# scalars as Contour; the triangulation of ambiguous cells differs, so about
# 2% of pixels change by a few levels.
# Load the plugin by its path when it is in the install the job's
# CATALYST_LIB_DIR (<install>/lib/catalyst) points at, for this ParaView's
# version. With ParaView 6.2.1, Catalyst does not find the install's plugin
# list, so loading it by name fails (sites/shaheen/README.md, "Catalyst
# reader performance"). PV_PLUGIN_CONFIG_FILE would also fix that, but
# ParaView force-loads every plugin in that list, on every rank. Resolved
# here, at run time, so the script works whichever host generated it.
from paraview import servermanager as _gs_sm
_gs_pv = "paraview-%d.%d" % (
    _gs_sm.vtkSMProxyManager.GetVersionMajor(),
    _gs_sm.vtkSMProxyManager.GetVersionMinor(),
)
_gs_lib = _gs_os.environ.get("CATALYST_LIB_DIR", "").rstrip("/")
_gs_aa_plugin = _gs_os.path.join(
    _gs_os.path.dirname(_gs_lib), _gs_pv, "plugins",
    "AcceleratedAlgorithms", "AcceleratedAlgorithms.so",
) if _gs_lib else ""
if _gs_aa_plugin and _gs_os.path.exists(_gs_aa_plugin):
    LoadPlugin(_gs_aa_plugin, remote=False, ns=globals())
else:
    LoadDistributedPlugin('AcceleratedAlgorithms', remote=False, ns=globals())
contour = FlyingEdges3D(registrationName='Contour', Input=ghostCells)
contour.ContourBy = ['POINTS', 'v']
contour.Isosurfaces = [0.1]
contour.ComputeNormals = 1
contour.ComputeScalars = 1

isoDisplay = Show(contour, renderView1, 'GeometryRepresentation')
isoDisplay.SetRepresentationType('Surface')

# Color by 'u' instead of 'v'
ColorBy(isoDisplay, ('POINTS', 'v'))

uLUT = GetColorTransferFunction("v")
uLUT.Set(RGBPoints=[0.0, 0.23, 0.29, 0.75, 0.5, 0.86, 0.86, 0.86, 1.0, 0.7, 0.01, 0.14])
# Pinned: rescaling to each run's range draws the same data differently per
# rank count (docs/in-situ-backends.md, Catalyst).
uLUT.AutomaticRescaleRangeMode = "Never"
uLUT.RescaleTransferFunction(0.0, 1.0)

isoDisplay.SetScalarBarVisibility(renderView1, True)

pNG1 = CreateExtractor("PNG", renderView1, registrationName="PNG1")
pNG1.Trigger = "TimeStep"
pNG1.Writer.Set(FileName="catalyst_iso_{{timestep:06d}}.png", ImageResolution=[2048, 2048], Format="PNG")

options = catalyst.Options()
options.GlobalTrigger = "TimeStep"
options.EnableCatalystLive = 0
options.ExtractsOutputDirectory = 'data'

def catalyst_execute(info):
    pass

if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions
    SaveExtractsUsingCatalystOptions(options)
"""
)

# --- PAPER 1 KOMBYNE TEMPLATES ---
KOMBYNE_RENDER_TEMPLATE = """
pipelines:
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
"""

KOMBYNE_DATA_TEMPLATE = """
pipelines:
  - type: "null"
    enabled: "true"
    frequency: 1
    outputs:
      - type: "export"
        file_pattern: "data/full_grid.%ts"
        file_format: "vtk"
        attributes:
          binary: "true"
"""

# =============================================================================
# PAPER 1 TEMPLATES: exactly as verified for WOIV 2026 on current master (#71).
# Paper 1 jobs use these, so changes for Paper 2 do not alter its images.
# =============================================================================
PAPER1_ASCENT_OPTIONS_TEMPLATE = """runtime:
  type: "ascent"
  vtkm:
    backend: "openmp"
actions_file: "{actions_file}"
messages: "verbose"
timings: "true"
"""

PAPER1_ASCENT_RENDER_TEMPLATE = """
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

PAPER1_CATALYST_RENDER_TEMPLATE = """
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

PAPER1_KOMBYNE_RENDER_TEMPLATE = """
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

PAPER1_KOMBYNE_DATA_TEMPLATE = """
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

# =============================================================================
# EXCLUSIVE / DEDICATED TEMPLATES
# =============================================================================
SBATCH_TEMPLATE = """#!/bin/bash
#SBATCH --job-name={id}
#SBATCH --account={account}
#SBATCH --partition={partition}
{qos_line}
#SBATCH --nodes={total_nodes}
#SBATCH --ntasks={total_ranks}
{cpus_per_task_line}
{network_line}
#SBATCH --time={time_limit}
{hint_line}
#SBATCH --exclusive
#SBATCH --output={output_dir}/slurm-%j.out
#SBATCH --error={output_dir}/slurm-%j.err

source {repo_path}/Miniapps/gray-scott/sites/shaheen/MODULES.sh


# =============================================================================
# PRE-FLIGHT CHECK: Lustre Inode & Disk Space Quota
# =============================================================================
echo "Checking Lustre quota (Inodes and Disk Space)..."

# Run lfs quota (without -h for raw numbers in KB and counts)
# Columns: $2=Used_KB, $4=Limit_KB, $6=Used_Inodes, $8=Limit_Inodes
QUOTA_INFO=$(lfs quota -u $USER /scratch | awk '/\\/scratch/ {{print $2, $4, $6, $8}}')

# lfs marks an exceeded quota with '*' (e.g. 123456*): keep digits only.
USED_KB=$(echo $QUOTA_INFO | awk '{{print $1}}' | tr -cd '0-9')
LIMIT_KB=$(echo $QUOTA_INFO | awk '{{print $2}}' | tr -cd '0-9')
USED_INODES=$(echo $QUOTA_INFO | awk '{{print $3}}' | tr -cd '0-9')
LIMIT_INODES=$(echo $QUOTA_INFO | awk '{{print $4}}' | tr -cd '0-9')
if [ -z "$USED_KB" ] || [ -z "$LIMIT_KB" ] || [ -z "$USED_INODES" ] || [ -z "$LIMIT_INODES" ]; then
    echo "JOB ABORTED: could not read the Lustre quota ('$QUOTA_INFO')."
    exit 1
fi

# --- Thresholds ---
# A limit of 0 means no quota: skip that check.
REQUIRED_INODES=150000

# Require at least 500 GB of free space (500 * 1024 * 1024 KB)
REQUIRED_KB=524288000

AVAILABLE_INODES=$((LIMIT_INODES - USED_INODES))
AVAILABLE_KB=$((LIMIT_KB - USED_KB))

# Convert KB to GB for human-readable console output
AVAILABLE_GB=$((AVAILABLE_KB / 1024 / 1024))
REQUIRED_GB=$((REQUIRED_KB / 1024 / 1024))

FAIL=0

if [ "$LIMIT_INODES" -gt 0 ] && [ "$AVAILABLE_INODES" -lt "$REQUIRED_INODES" ]; then
    echo " -> CRITICAL: Insufficient inodes! Available: $AVAILABLE_INODES (Requires $REQUIRED_INODES)"
    FAIL=1
fi

if [ "$LIMIT_KB" -gt 0 ] && [ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]; then
    echo " -> CRITICAL: Insufficient disk space! Available: ${{AVAILABLE_GB}}GB (Requires ${{REQUIRED_GB}}GB)"
    FAIL=1
fi

if [ "$FAIL" -eq 1 ]; then
    echo "====================================================================="
    echo "JOB ABORTED: Storage quotas exceeded."
    echo "Action: Clean up your /scratch directory before submitting."
    echo "This prevents silent I/O failures, 0-byte files, and MPI deadlocks."
    echo "====================================================================="
    exit 1
else
    echo "Pre-flight checks passed."
    echo " -> Available Inodes: $AVAILABLE_INODES"
    echo " -> Available Space:  ${{AVAILABLE_GB}}GB"
fi
# =============================================================================


# --- Rendering: offscreen OSMesa (sites/shaheen/README.md, top) ---
export CATALYST_LIB_DIR="{catalyst_lib_path}"
# ParaView's lib must be on the library path: OSPRay loads its modules
# (Embree, OpenVKL) from there at run time, and without them every reader
# rank segfaults in OpenGL setup (#72).
export LD_LIBRARY_PATH="{paraview_lib_path}:$LD_LIBRARY_PATH"

unset DISPLAY
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
export GS_CATALYST_BACKEND=osmesa
# Mesa's rasteriser for everything OpenGL still draws around OSPRay: the
# image blit, IceT's buffers, the scalar bar and orientation axes. llvmpipe
# is Mesa's JIT rasteriser; softpipe, its reference rasteriser, took 6 s per
# 2048x2048 frame on top of OSPRay (sites/shaheen/README.md, "Catalyst reader
# performance"). Paper 1 jobs keep softpipe, as they were run. One thread
# here, where 64 simulation ranks share a node; the reader sets its own.
export GALLIUM_DRIVER={gallium_driver}
export LP_NUM_THREADS=1
{mesa_cache_line}

# --- Exascale Slingshot-11 OFI Tuning ---
export FI_CXI_RX_MATCH_MODE=software
export FI_CXI_DEFAULT_CQ_SIZE=1310720
export FI_CXI_OFLOW_BUF_SIZE=8388608
export FI_CXI_CQ_FILL_PERCENT=20
export FI_TCP_IFACE=hsn0
export CM_NETWORK_INTERFACE=hsn0
export CM_DISABLE_SHM=1
# Fix glibc's mmap threshold at its 32 MiB maximum instead of letting it move
# with the allocation pattern. With ADIOS2 2.13.0-rc1 the reader's SST RDMA
# step took 9.0 s instead of 7.2 s until this was set; 2.12.0, and rc1
# without the commit that caused it, run the same with or without it
# (sites/shaheen/README.md, "glibc mmap threshold").
export MALLOC_MMAP_THRESHOLD_=33554432
ulimit -n $(ulimit -Hn)
ulimit -l unlimited

# --- Silencing ADIOS2 Logs ---
export Sst_Verbose=0
export ADIOS2_LOG_LEVEL=OFF

export MPICH_MAX_THREAD_SAFETY=multiple
export OMP_NUM_THREADS={omp_threads}
# No OSPRAY_THREADS: OSPRay 2 does not read it (OSPRAY_NUM_THREADS is its
# name), and its TBB pool sizes itself from the thread's CPU mask anyway.
export OMP_PLACES=threads
export OMP_PROC_BIND=spread
export PYTHONDONTWRITEBYTECODE=1

EXE_SIM="{bin_path}/gray-scott"
EXE_STAGE="{bin_path}/analysis-reader"
OUTPUT_DIR="{output_dir}"

# Ensure a clean slate for SST contact files
rm -f $OUTPUT_DIR/data/*.sst

mkdir -p $OUTPUT_DIR/data
lfs setstripe -c -1 $OUTPUT_DIR/data
cd $OUTPUT_DIR
# Timer directories an earlier job left unreduced (its reduction failed or
# never ran) are set aside, so this job's reduction never takes them for this
# job's: the Catalyst timers carry no run record to check.
for d in reader_timers catalyst_timers; do
    if [ -d $OUTPUT_DIR/$d ]; then
        # Unique, so a requeued job (same ID) never moves it inside an
        # earlier set-aside directory.
        aside=$OUTPUT_DIR/$d.before$SLURM_JOB_ID.$(date +%s)
        mv $OUTPUT_DIR/$d $aside && echo "Set aside an earlier job's $d/ as $(basename $aside)"
    fi
done

# A stuck shutdown no longer needs a watchdog: both programs write their
# results and timings first, then give teardown teardown_timeout_s seconds
# (default 300) before exiting with status 0 (#75).

echo "Starting Run: {id}"
# Phase timestamps (seconds since the epoch) for #72: job start to run start
# is setup, run start to run end is launch, startup, steps and shutdown.
echo "PHASE job_start $SLURM_JOB_START_TIME"
# Keep this job's script and the job-wide settings it exported beside the
# results, so runs made with different settings (MALLOC_MMAP_THRESHOLD_, the
# OFI tuning) can be told apart afterwards. Thread settings are left out:
# each srun command sets its own (the reader's differ from the shell's), and
# the saved script shows them.
# A results directory that cannot be written would lose the run's numbers
# too, so stop here rather than after the run.
mkdir -p "{results_dir}" || exit 1
cp "$0" "{results_dir}/{id}_job.sbat" || exit 1
# pipefail in a subshell, so a failure anywhere in the pipeline stops the job.
(set -o pipefail; env | grep -E '^(MALLOC_|FI_|CM_|MPICH_|Sst_|ADIOS2_|GALLIUM_|LP_)' | sort) > "{results_dir}/{id}_env.txt" || exit 1
{stage_setup}{telemetry_start}echo "PHASE run_start $(date +%s.%N)"

{command}
RUN_RC=$?
echo "PHASE run_end $(date +%s.%N)"
{stage_cleanup}{telemetry_stop}echo "Run exit status: $RUN_RC"

# =============================================================================
# POST-PROCESSING in its own one-node job (#72)
# =============================================================================
# Reducing tens of thousands of per-rank timing files took minutes (once over
# half an hour) while every node of this job sat idle. Submit the reduction
# as a one-node job and end this one, so its nodes are released now.
echo "Run complete. Submitting the reduction job ({output_dir}/reduce.sbat)..."
# Retry a transient controller error or submit limit; if it still fails,
# print a marker that can be grepped for, since the job's state stays the run's.
for attempt in 1 2 3; do
    if sbatch --export=ALL,RUN_JOB_ID=$SLURM_JOB_ID {output_dir}/reduce.sbat; then
        break
    fi
    echo "sbatch of the reduction job failed (attempt $attempt of 3)"
    if [ "$attempt" -eq 3 ]; then
        echo "REDUCE_SUBMIT_FAILED: run it later with: sbatch --export=ALL,RUN_JOB_ID=$SLURM_JOB_ID {output_dir}/reduce.sbat"
    else
        sleep 10
    fi
done
echo "PHASE post_end $(date +%s.%N)"
# The job's status is the run's.
exit $RUN_RC
"""

# Backends that write one file per simulation rank (Catalyst's .vtpd, Ascent's
# Blueprint domains, the baseline's .pvti) leave about 64 files per node: a
# 3328-node Catalyst data run left 213,025, and the sweep's data runs would
# fill the 2M-inode /scratch quota on their own (22 Nov 2026). The timings
# are in the timers; the output is not read afterwards. The reduction job
# records how many files and bytes the run wrote in <id>_data_output.json,
# then deletes data/. ADIOS2 data runs too: few files but full fields, 12 TB
# for one 3072 + 192 in transit run, which nearly filled the 31 TiB quota
# (23 Nov 2026). Render images and the initialisations' checkpoints are kept.
DATA_CLEANUP = """
# 1a. Record and delete the run's per-rank output (DATA_CLEANUP). The record is
#     written to a temporary file and renamed before anything is deleted; a
#     retry for the same job keeps the first, complete record.
DATA_RECORD="{results_dir}/{id}_data_output.json"
# data/, and Ascent's data output: its relay extract writes
# ascent_data.cycle_* and their .root files in the run directory itself,
# outside data/.
DATA_TARGETS=()
[ -d $OUTPUT_DIR/data ] && DATA_TARGETS+=("$OUTPUT_DIR/data")
for f in $OUTPUT_DIR/ascent_data.cycle_*; do
    [ -e "$f" ] && DATA_TARGETS+=("$f")
done
if [ ${{#DATA_TARGETS[@]}} -gt 0 ]; then
    if [ -n "${{RUN_JOB_ID:-}}" ] && grep -q "\\"job\\": \\"${{RUN_JOB_ID}}\\"" "$DATA_RECORD" 2>/dev/null; then
        echo "Output of job $RUN_JOB_ID already recorded; finishing its deletion."
        RECORDED=1
    else
        echo "Counting the run's output: ${{DATA_TARGETS[*]}}..."
        RECORDED=0
        if find "${{DATA_TARGETS[@]}}" -type f -printf '%s\\n' > $OUTPUT_DIR/data_sizes.txt \\
            && awk -v job="${{RUN_JOB_ID:-}}" -v when="$(date +%FT%T)" \\
                '{{n++; b+=$1}} END {{printf "{{\\"job\\": \\"%s\\", \\"files\\": %d, \\"bytes\\": %.0f, \\"deleted\\": \\"%s\\"}}\\n", job, n, b, when}}' \\
                $OUTPUT_DIR/data_sizes.txt > "$DATA_RECORD.tmp" \\
            && mv "$DATA_RECORD.tmp" "$DATA_RECORD"; then
            RECORDED=1
            cat "$DATA_RECORD"
        else
            echo "Could not record the run's output; keeping it."
            rm -f "$DATA_RECORD.tmp"
        fi
        rm -f $OUTPUT_DIR/data_sizes.txt
    fi
    if [ "$RECORDED" = 1 ]; then
        echo "Deleting ${{DATA_TARGETS[*]}}..."
        find "${{DATA_TARGETS[@]}}" -type f -print0 | xargs -0 -r -n 2000 -P 16 rm -f
        rm -rf "${{DATA_TARGETS[@]}}"
    fi
fi
"""


def drops_data_output(exp):
    """True for runs whose data/ output is deleted after the reduction (see
    DATA_CLEANUP): every data run, any backend, inline or in transit, and the
    baselines. Never the initialisations, whose data/ holds the checkpoint."""
    if exp["workload"] == "initialization":
        return False
    return exp["backend"] == "baseline" or exp["workload"] == "data_save"


# One-node job that reduces a run's per-rank timings (#72). Written next to
# each run as reduce.sbat and submitted by the run's job when it ends.
REDUCE_TEMPLATE = """#!/bin/bash
#SBATCH --job-name=reduce_{id}
#SBATCH --account={account}
#SBATCH --partition={partition}
#SBATCH --nodes=1
# One node, so a long limit costs little: reducing 65536 per-rank timer
# files took over 54 minutes (1024 + 32 node sweep run, 15 Nov 2026).
#SBATCH --time=4:00:00
#SBATCH --output={output_dir}/reduce-%j.out
#SBATCH --error={output_dir}/reduce-%j.err

OUTPUT_DIR="{output_dir}"
echo "PHASE reduce_start $(date +%s.%N)"

# 1. Activate the Python environment only now: inside the run it breaks
#    Catalyst (sites/shaheen/README.md).
echo "Activating Python virtual environment..."
module load python
source {perf_env}/bin/activate

REDUCE={repo_path}/Miniapps/gray-scott/sites/shaheen/2026-WOIV-scripts/reduce_timers.py

# One reduction per run at a time. mkdir is atomic on Lustre, where flock may
# not be. A job killed outright (time limit) leaves the lock behind; remove
# $OUTPUT_DIR/reduce.lock by hand once no reduction of this run is running.
LOCK=$OUTPUT_DIR/reduce.lock
if ! mkdir $LOCK 2>/dev/null; then
    echo "Another reduction holds $LOCK ($(cat $LOCK/job 2>/dev/null)); not reducing."
    exit 1
fi
echo "$SLURM_JOB_ID" > $LOCK/job
trap 'rm -rf $LOCK' EXIT
{data_cleanup}
# Archive a directory atomically: write the archive under a temporary name,
# rename it, then remove the directory.
archive() {{
    tar -czf $OUTPUT_DIR/$1.tar.gz.tmp -C $OUTPUT_DIR $1/ \
        && mv $OUTPUT_DIR/$1.tar.gz.tmp $OUTPUT_DIR/$1.tar.gz \
        && rm -rf $OUTPUT_DIR/$1/
}}

# Whose exports are these? <id>_reduced_job.txt names the job whose
# measurements were last reduced here (written just below, for every run;
# older results fall back to the telemetry's <id>_tel_job.txt). If it is
# not this reduction's job, clear every measurement export first, before
# anything can fail or exit, so this job never ends up beside an earlier
# job's summary or CSVs. Without RUN_JOB_ID (a reduction run by hand) the
# exports are taken as this job's.
OWN_EXPORTS=1
if [ -n "${{RUN_JOB_ID:-}}" ]; then
    OWNER=$(cat "{results_dir}/{id}_reduced_job.txt" 2>/dev/null \\
        || cat "{results_dir}/{id}_tel_job.txt" 2>/dev/null)
    if [ "$OWNER" != "$RUN_JOB_ID" ]; then
        OWN_EXPORTS=0
        rm -f "{results_dir}/{id}_summary.json" "{results_dir}/{id}_writer.csv" \\
            "{results_dir}/{id}_reader.csv" "{results_dir}/{id}_catalyst.csv"
        # The earlier job's archives are set aside (kept, under its job ID),
        # so no later reduction of this job can restore them as its own.
        # Nothing reads them afterwards: delete them by hand when no longer
        # wanted (sites/shaheen/README.md, Telemetry).
        for d in perf reader_timers catalyst_timers; do
            if [ -f $OUTPUT_DIR/$d.tar.gz ]; then
                # Stop before the owner marker below moves to this job if the
                # archive cannot be set aside: a retry then tries again
                # instead of taking the earlier job's archive as this job's.
                if ! mv $OUTPUT_DIR/$d.tar.gz $OUTPUT_DIR/$d.job${{OWNER:-unknown}}.tar.gz; then
                    echo "Could not set $d.tar.gz (job ${{OWNER:-unknown}}) aside; not reducing."
                    exit 1
                fi
                echo "$d.tar.gz is job ${{OWNER:-unknown}}'s: kept as $d.job${{OWNER:-unknown}}.tar.gz"
            fi
        done
    fi
    echo "$RUN_JOB_ID" > "{results_dir}/{id}_reduced_job.txt"
fi

# A rerun after a successful reduction finds only the archives: restore them.
# Only for a rerun of the same job (OWN_EXPORTS): another job's archives
# would be reduced as this job's, and the Catalyst timers carry no run record
# to check. Extract into a temporary directory and move it into place only if
# tar succeeds, so a failed extraction never looks like a complete one. The
# archive is kept until the new one replaces it.
for d in perf reader_timers catalyst_timers; do
    if [ "$OWN_EXPORTS" = 1 ] && [ ! -d $OUTPUT_DIR/$d ] && [ -f $OUTPUT_DIR/$d.tar.gz ]; then
        echo "Restoring $d/ from $d.tar.gz..."
        rm -rf $OUTPUT_DIR/$d.restore && mkdir $OUTPUT_DIR/$d.restore
        if tar -xzf $OUTPUT_DIR/$d.tar.gz -C $OUTPUT_DIR/$d.restore \
            && mv $OUTPUT_DIR/$d.restore/$d $OUTPUT_DIR/$d; then
            rm -rf $OUTPUT_DIR/$d.restore
        else
            echo "Could not restore $d/ from $d.tar.gz; not reducing."
            rm -rf $OUTPUT_DIR/$d.restore
            exit 1
        fi
    fi
done

# A rerun of this reduction restores archives (above), so a directory here
# may be an earlier job's when this job wrote none. other_job is true when a
# run record names a job other than this reduction's: that directory is then
# neither reduced nor exported, and the earlier job's exports are removed, so
# this job's results never carry another job's measurements. Without
# RUN_JOB_ID (a reduction run by hand), and for records from before
# slurm_job_id, everything is taken as before.
other_job() {{
    [ -n "${{RUN_JOB_ID:-}}" ] && [ -f "$1" ] && grep -q slurm_job_id "$1" \\
        && ! grep -Eq "slurm_job_id.: ?.${{RUN_JOB_ID}}[^0-9]" "$1"
}}

# 2. Simulation timings: the newest run directory under perf/ (README.md,
#    Performance). Keep its metadata.json and summary.json beside the CSV.
SIM_PERF=$(ls -dt $OUTPUT_DIR/perf/*/ 2>/dev/null | head -1)
# An earlier job's run record must not stay beside this job's results (its
# hostnames would be taken for this job's simulation nodes).
rm -f "{results_dir}/{id}_metadata.json"
if [ -n "$SIM_PERF" ] && other_job "$SIM_PERF/metadata.json"; then
    echo "$SIM_PERF is another job's, not $RUN_JOB_ID's: not reduced; its exports removed."
    rm -f "{results_dir}/{id}_summary.json" "{results_dir}/{id}_writer.csv"
elif [ -n "$SIM_PERF" ]; then
    echo "Reducing $SIM_PERF..."
    cp "$SIM_PERF/metadata.json" "{results_dir}/{id}_metadata.json" 2>/dev/null
    cp "$SIM_PERF/summary.json" "{results_dir}/{id}_summary.json" 2>/dev/null
    # Compress only after a successful reduction, so a failure keeps the raw logs.
    if python "$REDUCE" "$SIM_PERF" "{results_dir}/{id}_writer.csv"; then
        echo "Compressing perf/..."
        archive perf
    else
        echo "Reduction of $SIM_PERF failed; perf/ kept."
    fi
fi

# 3. Reader timings (in transit runs).
# A reader record from an earlier job of this experiment must not stay
# beside this job's results, whether or not this job wrote one.
rm -f "{results_dir}/{id}_reader_metadata.json"
if [ -d "$OUTPUT_DIR/reader_timers" ] && other_job "$OUTPUT_DIR/reader_timers/metadata.json"; then
    echo "reader_timers/ is another job's, not $RUN_JOB_ID's: not reduced; its export removed."
    rm -f "{results_dir}/{id}_reader.csv"
elif [ -d "$OUTPUT_DIR/reader_timers" ]; then
    # The reader's own run record (build, commit, platform, libraries), beside
    # the simulation's {id}_metadata.json, before the directory is archived.
    cp "$OUTPUT_DIR/reader_timers/metadata.json" "{results_dir}/{id}_reader_metadata.json" 2>/dev/null
    echo "Reducing reader_timers..."
    if python "$REDUCE" "$OUTPUT_DIR/reader_timers" "{results_dir}/{id}_reader.csv"; then
        echo "Compressing reader_timers..."
        archive reader_timers
    else
        echo "Reduction of reader_timers failed; reader_timers/ kept."
    fi
fi

# 4. Catalyst stage timers (in transit Catalyst runs; catalyst_timers.py).
if [ -d "$OUTPUT_DIR/catalyst_timers" ]; then
    echo "Reducing catalyst_timers..."
    if python "$(dirname "$REDUCE")/catalyst_timers.py" "$OUTPUT_DIR/catalyst_timers" "{results_dir}/{id}_catalyst.csv"; then
        echo "Compressing catalyst_timers..."
        archive catalyst_timers
    else
        echo "Reduction of catalyst_timers failed; catalyst_timers/ kept."
    fi
fi

{telemetry_reduce}echo "PHASE reduce_end $(date +%s.%N)"
"""

# --telemetry: per-node power, CPU, memory and NIC counters at 1 Hz, Slurm
# step accounting with energy, and an environment snapshot, for the Paper 2
# telemetry corpus (sites/shaheen/README.md, "Telemetry"). Off by default.
# The sampler is one task per node with --overlap; on 2 nodes beside a step
# using every core it neither delayed that step nor changed its time beyond
# run-to-run noise (15 Nov 2026).
TELEMETRY_START = """# --- Telemetry (--telemetry) ---
# One directory per job, so a resubmitted run never mixes its samples with
# an earlier job's, and each job's reduction reads only its own.
TEL=$OUTPUT_DIR/telemetry/$SLURM_JOB_ID
mkdir -p $TEL/nodes
echo "$SLURM_JOB_ID" > $TEL/job_id
# Slurm samples tasks and energy every 600 s by default on Shaheen, which
# leaves short steps with no memory or energy figures.
export SLURM_ACCTG_FREQ=task=30,energy=30
module list > $TEL/modules.txt 2>&1
env | grep -E '^(SLURM_|OMP_|OSPRAY_|GALLIUM_|VTK_|TBB_|MALLOC_|FI_|CM_|MPICH_|Sst_|ADIOS2_|LD_LIBRARY_PATH=)' | sort > $TEL/env.txt
for b in "$EXE_SIM" "$EXE_STAGE"; do echo "== $b"; ldd "$b" 2>&1; done > $TEL/ldd.txt
(cat "{repo_path}/SOURCE.txt" 2>/dev/null; git -C "{repo_path}" describe --always --dirty 2>/dev/null) > $TEL/source.txt
scontrol show job $SLURM_JOB_ID > $TEL/job.txt 2>&1
# Where the nodes sit on the network (Slurm's tree: leaf switch of 16
# nodes, then the 256-node dragonfly group); corpus_index.py turns it and
# the node lists into placement columns.
scontrol show topology > $TEL/topology.txt 2>&1
# The platform before the run: one line per node (kernel, CPU frequency
# driver, governor and boost, memory, NUMA nodes, NIC firmware and link),
# so a node that differs is visible, and the full detail of one node. Each
# probe is limited to 120 s, so a hung tool on a bad node cannot hold the
# allocation; these steps shift Slurm's step numbers (the run is step 3, or
# later when --catalyst-stage adds its copy steps before them).
PLATFORM={repo_path}/Miniapps/gray-scott/sites/shaheen/2026-WOIV-scripts/node_platform.sh
srun --overlap --network=no_vni --mpi=none \\
    --nodes=$SLURM_NNODES --ntasks=$SLURM_NNODES --ntasks-per-node=1 --cpus-per-task=1 --mem=1G \\
    --output=$TEL/platform_nodes.txt --error=$TEL/platform_nodes.err timeout 120 $PLATFORM line \\
    || echo "platform capture failed (rc $?); the run goes on"
srun --overlap --network=no_vni --mpi=none --nodes=1 --ntasks=1 --cpus-per-task=1 --mem=1G \\
    --output=$TEL/platform.txt --error=$TEL/platform.txt timeout 120 $PLATFORM full \\
    || echo "platform capture failed (rc $?); the run goes on"
# No Slingshot VNI and no MPI wire-up for the sampler: it uses neither, and
# with the defaults the step took network resources that MPI_Init in the
# run's step then could not get (fi_getinfo "No data available") on some
# nodes: both 1920 + 128 sweep runs and one 64 + 4 run failed that way.
srun --overlap --network=no_vni --mpi=none \\
    --nodes=$SLURM_NNODES --ntasks=$SLURM_NNODES --ntasks-per-node=1 --cpus-per-task=1 --mem=1G \\
    --output=$TEL/sampler.log --error=$TEL/sampler.log \\
    {repo_path}/Miniapps/gray-scott/sites/shaheen/2026-WOIV-scripts/node_sampler.sh $TEL/nodes 1 &
TEL_PID=$!
# Out of the job table, so the launch's `wait -n` (bash 4.4 cannot name
# PIDs) never takes the sampler for an application step.
disown $TEL_PID
# Cray MPICH's NIC counters for MPI traffic (the simulation's halos and
# collectives): a summary over the job's NICs (min, mean, max) printed to
# the job's output when MPI finalizes; the reduction saves it.
export MPICH_OFI_CXI_COUNTER_REPORT=2
{darshan_start}"""

# Darshan for --telemetry: every file read and write of the run (POSIX,
# MPI-IO, STDIO, Lustre striping), one log per MPI job. Preloaded only for
# the run's own srun commands: set after the sampler starts, unset after.
DARSHAN_START = """mkdir -p $TEL/darshan
export DARSHAN_LOG_DIR_PATH=$TEL/darshan
export LD_PRELOAD={darshan_prefix}/lib/libdarshan.so${{LD_PRELOAD:+:$LD_PRELOAD}}
"""

TELEMETRY_STOP = """unset LD_PRELOAD
kill $TEL_PID 2>/dev/null
for i in $(seq 1 10); do kill -0 $TEL_PID 2>/dev/null || break; sleep 1; done
"""

TELEMETRY_REDUCE = """# 5. Telemetry (--telemetry): Slurm's step accounting, once the run's steps
#    are final (the database lags about a minute), then a summary and an
#    archive of the per-node samples.
# The run's job passes its ID (RUN_JOB_ID); to rerun by hand, use
# sbatch --export=ALL,RUN_JOB_ID=<run job> reduce.sbat.
TEL=$OUTPUT_DIR/telemetry/${{RUN_JOB_ID:-none}}
if [ -z "$RUN_JOB_ID" ] && [ -d $OUTPUT_DIR/telemetry ]; then
    echo "RUN_JOB_ID not set; telemetry not reduced (see reduce.sbat)."
fi
if [ -f $TEL/job_id ]; then
    RUN_JOB=$(cat $TEL/job_id)
    # The experiment-level exports below hold one job's telemetry. If they
    # belong to another job of this experiment (or to an older reduction
    # that recorded no job), remove them all first, so nothing of that job
    # is ever left beside this one's results, whatever fails below.
    TJ="{results_dir}/{id}_tel_job.txt"
    if [ "$(cat "$TJ" 2>/dev/null)" != "$RUN_JOB" ]; then
        rm -rf "{results_dir}/{id}_sacct.txt" "{results_dir}/{id}_telemetry.json" \\
            "{results_dir}/{id}_darshan" "{results_dir}/{id}_mpich_cxi_summary.txt" \\
            "{results_dir}/{id}_tel_env.txt" "{results_dir}/{id}_tel_modules.txt" \\
            "{results_dir}/{id}_tel_ldd.txt" "{results_dir}/{id}_tel_source.txt" \\
            "{results_dir}/{id}_tel_topology.txt" "{results_dir}/{id}_tel_platform.txt" \\
            "{results_dir}/{id}_tel_platform_nodes.txt"
        echo "$RUN_JOB" > "$TJ"
    fi
    # Accounting counts only once sacct answers, lists the run's numbered
    # steps, and none of them is still active. A failed or empty answer is
    # asked again; if none is final within 3 minutes there is no sacct.txt
    # and the summary has no Slurm steps, rather than a partial list.
    FIELDS=JobIDRaw,JobName,Start,End,Elapsed,NNodes,NTasks,NodeList,State,ExitCode,TotalCPU,UserCPU,SystemCPU,MaxRSS,MaxRSSNode,AveRSS,TRESUsageInTot,TRESUsageOutTot,ConsumedEnergyRaw,AveCPUFreq
    # A refresh replaces sacct.txt only with an answer that passes; an
    # earlier final answer for this job is kept otherwise.
    for i in $(seq 1 18); do
        if sacct -j $RUN_JOB -P -o $FIELDS > $TEL/sacct.tmp 2>/dev/null \\
            && grep -q -E "^$RUN_JOB\\.[0-9]" $TEL/sacct.tmp \\
            && ! cut -d'|' -f9 $TEL/sacct.tmp | grep -q -E 'RUNNING|PENDING|COMPLETING|REQUEUED'; then
            mv $TEL/sacct.tmp $TEL/sacct.txt
            break
        fi
        sleep 10
    done
    if [ -f $TEL/sacct.tmp ] && [ -f $TEL/sacct.txt ]; then
        echo "sacct gave no final answer this time; the earlier one is kept."
    fi
    rm -f $TEL/sacct.tmp
    if [ -f $TEL/sacct.txt ]; then
        cp $TEL/sacct.txt "{results_dir}/{id}_sacct.txt"
    else
        echo "sacct gave no final answer for job $RUN_JOB; no Slurm step accounting."
    fi
    # Darshan: a text total of every log, then the logs themselves beside
    # the other results (one log per MPI job).
    if [ -d $TEL/darshan ] && [ -x "{darshan_prefix}/bin/darshan-parser" ]; then
        # A log counts as parsed only if darshan-parser succeeds and prints no
        # "Error:" (3.4.7 reports a truncated module record that way and still
        # exits 0); otherwise its output is kept as <log>.parse-failed.txt and
        # the corpus index leaves the run's Darshan totals empty.
        for log in $(find $TEL/darshan -name '*.darshan' 2>/dev/null); do
            out="${{log%.darshan}}"
            rm -f "$out.total.txt" "$out.parse-failed.txt"
            if "{darshan_prefix}/bin/darshan-parser" --total --perf "$log" > "$out.total.tmp" 2>&1 \\
                && ! grep -q '^Error:' "$out.total.tmp"; then
                mv "$out.total.tmp" "$out.total.txt"
            else
                mv "$out.total.tmp" "$out.parse-failed.txt"
                echo "darshan-parser could not read $log; see $out.parse-failed.txt"
            fi
        done
        # This job's logs replace an earlier job's of the same experiment,
        # through a fresh directory, so the index never sums two runs. With
        # -exec ... + find fails if cp does, and the old export stays.
        DX="{results_dir}/{id}_darshan"
        rm -rf "$DX.tmp" && mkdir -p "$DX.tmp" \\
            && find $TEL/darshan \\( -name '*.darshan' -o -name '*.total.txt' -o -name '*.parse-failed.txt' \\) -exec cp -t "$DX.tmp/" {{}} + \\
            && rm -rf "$DX" && mv "$DX.tmp" "$DX"
    fi
    # Cray MPICH's NIC counter summary, from the run's job output.
    if [ -f $OUTPUT_DIR/slurm-$RUN_JOB.out ]; then
        sed -n '/MPICH Slingshot CXI Counter Summary/,/^PHASE run_end/p' $OUTPUT_DIR/slurm-$RUN_JOB.out \\
            | grep -v '^PHASE' > $TEL/mpich_cxi_summary.txt
        [ -s $TEL/mpich_cxi_summary.txt ] && cp $TEL/mpich_cxi_summary.txt "{results_dir}/{id}_mpich_cxi_summary.txt"
    fi
    # A rerun after a successful reduction finds only the archive: restore it.
    if [ ! -d $TEL/nodes ] && [ -f $TEL/nodes.tar.gz ]; then
        tar -xzf $TEL/nodes.tar.gz -C $TEL || {{ echo "Could not restore telemetry/nodes; summary kept."; rm -rf $TEL/nodes; }}
    fi
    # The captures from before the run, whatever the summary below does.
    # Straight to this experiment's names: reductions of other runs share
    # the results directory.
    for f in env modules ldd source topology platform platform_nodes; do
        [ -f $TEL/$f.txt ] && cp $TEL/$f.txt "{results_dir}/{id}_tel_$f.txt"
    done
    SUMMARY="{results_dir}/{id}_telemetry.json"
    if [ -d $TEL/nodes ] && python {repo_path}/Miniapps/gray-scott/sites/shaheen/2026-WOIV-scripts/summarize_telemetry.py $TEL "$SUMMARY.tmp"; then
        mv "$SUMMARY.tmp" "$SUMMARY"
        (cd $TEL && tar -czf nodes.tar.gz.tmp nodes/ && mv nodes.tar.gz.tmp nodes.tar.gz && rm -rf nodes/)
    else
        rm -f "$SUMMARY.tmp"
        echo "Telemetry summary failed; telemetry/nodes and any earlier summary kept."
    fi
fi

"""

CMD_INLINE = """srun --exclusive --propagate=NOFILE --hint=nomultithread \\
    --nodes={sim_nodes} --ntasks={sim_ranks} --ntasks-per-node={mpi_per_node} --cpus-per-task={omp_threads} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json
"""

CMD_INTRANSIT = """srun --exclusive --propagate=NOFILE --hint=nomultithread --kill-on-bad-exit=1 \\
    --nodes={sim_nodes}{sim_nodelist} --ntasks={sim_ranks} --ntasks-per-node={mpi_per_node} --cpus-per-task={omp_threads} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json \\
    : \\
    --exclusive --nodes={stage_nodes}{stage_nodelist} --ntasks={stage_ranks} --ntasks-per-node=8 {reader_cpus} --mem-bind=v,local --cpu-bind=threads \\
    env {reader_env} \\
    $EXE_STAGE \\
    --settings $OUTPUT_DIR/settings-stage.json \\
    --file $OUTPUT_DIR/data/grayScott \\
    --block-mode repartition \\
    --engine SST \\
    --mpi-split-color=1 \\
    --adios-verbose 0
"""

# Two srun steps, one per program, sharing the job's VNI so SST can connect
# across steps (--network=job_vni; #72). Each step gets its own nodes. The
# run's status is the first non-zero of the two.
CMD_INTRANSIT_STEPS = """srun --network=job_vni --exclusive --propagate=NOFILE --hint=nomultithread \\
    --nodes={sim_nodes} --ntasks={sim_ranks} --ntasks-per-node={mpi_per_node} --cpus-per-task={omp_threads} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json &
SIM_PID=$!
srun --network=job_vni --exclusive --propagate=NOFILE {reader_hint} \\
    --nodes={stage_nodes} --ntasks={stage_ranks} --ntasks-per-node=8 {reader_cpus} --mem-bind=v,local --cpu-bind=threads \\
    env {reader_env} \\
    $EXE_STAGE \\
    --settings $OUTPUT_DIR/settings-stage.json \\
    --file $OUTPUT_DIR/data/grayScott \\
    --block-mode repartition \\
    --engine SST \\
    --mpi-split-color=1 \\
    --adios-verbose 0 &
STAGE_PID=$!
# Like --kill-on-bad-exit for MPMD: if the first step to end failed, stop the
# other, which would otherwise wait for its peer until the time limit.
wait -n; FIRST_RC=$?
if [ $FIRST_RC -ne 0 ]; then
    echo "A step failed with status $FIRST_RC; stopping the other step."
    kill $SIM_PID $STAGE_PID 2>/dev/null
fi
wait $SIM_PID; SIM_RC=$?
wait $STAGE_PID; STAGE_RC=$?
echo "Simulation exit status: $SIM_RC, reader exit status: $STAGE_RC"
( exit $(( SIM_RC != 0 ? SIM_RC : STAGE_RC )) )
"""


def _minutes(limit):
    """Slurm time "[D-]H:MM:SS" (or "MM:SS") in minutes."""
    days, _, rest = limit.rpartition("-")
    parts = [int(x) for x in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts
    return (int(days) if days else 0) * 1440 + h * 60 + m + sec / 60


def check_settings_unchanged(output_dir, exp):
    """Refuse to regenerate a run with different recorded settings.

    The experiment ID includes neither the reader decomposition and
    shared-plane setting (in transit runs), the SST EndStep barrier and
    queue policy (every run), the ParaView build (catalyst_lib_path) nor
    Ascent's tiled rendering, so generations with other values into the same
    --results-dir share directories, and new settings would sit beside the
    old run's numbers. Files written before an option existed hold its old
    behaviour: slab, planes read, no barrier, Block, the 6.0.1 Catalyst,
    Ascent's default tiling. The initialisation runs, often shared between
    results directories, are not checked.
    """
    decomposition, planes = reader_decomposition(exp)
    checks = [
        ("adios_endstep_barrier", False, ADIOS_ENDSTEP_BARRIER),
        ("catalyst_lib_path", LEGACY_CATALYST_LIB_PATH, CATALYST_LIB_PATH),
        ("catalyst_stage", {"enabled": False}, catalyst_stage(exp)),
    ]
    if exp["type"] == "intransit":
        checks += [
            ("read_decomposition", "slab", decomposition),
            ("reader_shared_planes", "read", planes),
        ]
    # Ascent's tiled rendering is recorded in the file that holds the Ascent
    # options; a file without it was written for Ascent's default (tiled in
    # 0.9.6).
    tiled_file = (
        "settings-stage.json" if exp["type"] == "intransit" else "settings.json"
    )
    for name in ("settings.json", "settings-stage.json"):
        path = os.path.join(output_dir, name)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            settings = json.load(f)
        file_checks = list(checks)
        if name == tiled_file and ascent_renders(exp):
            file_checks.append(
                ("ascent_tiled_rendering", "Ascent default", ASCENT_TILED_RENDERING)
            )
        for key, legacy, current in file_checks:
            old = settings.get(key, legacy)
            if old != current:
                raise SystemExit(
                    f"{path} has {key} {old}; generating {current} would put its "
                    f"settings beside that run's results. Use another --results-dir."
                )
    # The SST queue policy lives in the run's adios2.xml; a file without it
    # (or written before the option) counts as Block.
    xml_path = os.path.join(output_dir, "adios2.xml")
    if os.path.exists(xml_path):
        old = "Block"
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError as err:
            raise SystemExit(
                f"{xml_path} cannot be parsed ({err}); not overwriting it."
            )
        io = root.find("./io[@name='SimulationOutput']")
        for param in io.iter("parameter") if io is not None else []:
            if param.get("key") == "QueueFullPolicy":
                old = param.get("value", "Block")
        if old != QUEUE_FULL_POLICY:
            raise SystemExit(
                f"{xml_path} has QueueFullPolicy {old}; generating {QUEUE_FULL_POLICY} would put it "
                f"beside that run's results. Use another --results-dir."
            )


# Threads for the in transit reader: 8 ranks per staging node, 24 cores each.
# Ascent's VTK-m runs on OpenMP and wants its 24 threads bound one per core:
# unbound, its slice render took 0.4 s more per step at 64 + 4 nodes. Paper 1
# jobs keep this binding for every backend, as they were run (#71).
ASCENT_READER_ENV = "OMP_NUM_THREADS=24 OMP_PLACES=cores OMP_PROC_BIND=close"
# Catalyst has no OpenMP threads to bind, and the binding hurts it:
# OMP_PROC_BIND pins the process's main thread to its first place, one core,
# and every thread that is not OpenMP's inherits that mask. OSPRay's and VTK's
# TBB pools and llvmpipe's threads all ran on one core of the rank's 24, and
# the render was single-threaded (sites/shaheen/README.md, "Catalyst reader
# performance"). Unbound, they spread over the rank's 24 cores, which srun's
# --cpu-bind gives the whole process. LP_NUM_THREADS sizes llvmpipe's pool.
CATALYST_READER_ENV = "OMP_NUM_THREADS=24 OMP_PROC_BIND=false LP_NUM_THREADS=24"
# Catalyst stage timers: each reader rank writes ParaView's scoped log of
# these categories to catalyst_timers/ (CATALYST_TIMERS_PROLOGUE), and the
# reduction job turns it into named timers (catalyst_timers.py).
CATALYST_TIMER_ENV = (
    "GS_CATALYST_TIMERS=1 PARAVIEW_LOG_CATALYST_VERBOSITY=INFO "
    "PARAVIEW_LOG_PIPELINE_VERBOSITY=INFO PARAVIEW_LOG_RENDERING_VERBOSITY=INFO"
)


def reader_decomposition(exp):
    """The reader's decomposition and shared-plane setting for a run.

    Paper 1 jobs keep the slab layout with planes read from the writers,
    as they were run (#71); every other run gets READ_DECOMPOSITION and
    READER_SHARED_PLANES.
    """
    if exp.get("paper") == "paper1":
        return "slab", "read"
    return READ_DECOMPOSITION, READER_SHARED_PLANES


def reader_smt(exp):
    """--reader-smt applies to every in transit run but Paper 1's (as run, #71)."""
    return READER_SMT and exp.get("paper") != "paper1"


def ascent_renders(exp):
    """Whether a run renders with a Paper 2 Ascent template (tiled_rendering set)."""
    if exp.get("paper") == "paper1" or exp["workload"] == "initialization":
        return False
    if exp["type"] == "intransit":
        backend = exp.get("stage_pipeline", "adios_data").split("_")[0]
    else:
        backend = exp["backend"]
    return backend == "ascent" and any(
        w in exp["workload"] for w in ("rendering", "volume", "isosurface")
    )


def reader_env(exp):
    """Environment for an in transit run's reader srun (see above).

    Paper 1 jobs keep the environment they were run with (#71). Every other
    reader gets READER_MALLOC_ENV, and with --reader-smt 48 threads on the
    rank's 24 cores instead of 24.
    """
    if exp.get("paper") == "paper1":
        return ASCENT_READER_ENV
    if exp.get("stage_pipeline", "").startswith("catalyst_"):
        env = CATALYST_READER_ENV + " " + CATALYST_TIMER_ENV
        if reader_smt(exp):
            env = env.replace("OMP_NUM_THREADS=24", "OMP_NUM_THREADS=48")
            env = env.replace("LP_NUM_THREADS=24", "LP_NUM_THREADS=48")
    else:
        env = ASCENT_READER_ENV
        if reader_smt(exp):
            env = env.replace(
                "OMP_NUM_THREADS=24 OMP_PLACES=cores",
                "OMP_NUM_THREADS=48 OMP_PLACES=threads",
            )
    env = env + " " + READER_MALLOC_ENV
    if catalyst_stage(exp)["enabled"]:
        # PREFER_ENV puts CATALYST_IMPLEMENTATION_PATHS before the reader's
        # catalyst_load/search_paths (catalyst_lib_path, the Lustre install);
        # CATALYST_LIB_DIR is where the Catalyst scripts find ParaView's
        # plugins; LD_LIBRARY_PATH (with GS_READER_RUNPATH) the libraries.
        lib = CATALYST_STAGE_DIR + "/lib"
        env += (
            f" CATALYST_IMPLEMENTATION_PREFER_ENV=1 CATALYST_IMPLEMENTATION_PATHS={lib}/catalyst"
            f" CATALYST_LIB_DIR={lib}/catalyst LD_LIBRARY_PATH={lib}:$LD_LIBRARY_PATH"
        )
    return env


def catalyst_stage_tarball():
    """The staging tarball for CATALYST_LIB_PATH's install and its sha256.

    build-catalyst-stage.sh writes <build dir>-lib.tar and .sha256 beside the
    build directory holding <install>/lib/catalyst. The checksum is checked
    against the tarball once per generation, so a tarball changed after it
    was recorded is never staged under the old checksum.
    """
    if "tarball" not in _STAGE_CACHE:
        install = os.path.dirname(os.path.dirname(CATALYST_LIB_PATH.rstrip("/")))
        tarball = os.path.dirname(install) + "-lib.tar"
        try:
            with open(tarball + ".sha256") as f:
                recorded = f.read().split()[0]
        except (OSError, IndexError):
            raise SystemExit(
                f"--catalyst-stage needs {tarball} and its .sha256: run "
                f"sites/shaheen/build-catalyst-stage.sh {install}"
            )
        digest = hashlib.sha256()
        with open(tarball, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 24), b""):
                digest.update(chunk)
        if digest.hexdigest() != recorded:
            raise SystemExit(
                f"{tarball} does not match its .sha256 ({recorded}); rebuild it "
                "with build-catalyst-stage.sh rather than reuse it"
            )
        _STAGE_CACHE["tarball"] = (tarball, recorded)
    return _STAGE_CACHE["tarball"]


_STAGE_CACHE = {}

# The reader that staged runs use (--bin-path), set in __main__.
READER_BIN_PATH = None


def check_reader_runpath():
    """Refuse to stage for a reader whose library path is a DT_RPATH.

    Its DT_RPATH names the Lustre install and is searched before
    LD_LIBRARY_PATH, so part of ParaView would still load from Lustre while
    the settings say the run was staged. Build it with GS_READER_RUNPATH=ON.
    """
    if "runpath" in _STAGE_CACHE:
        return
    reader = os.path.join(READER_BIN_PATH or "", "analysis-reader")
    try:
        dynamic = subprocess.run(
            ["readelf", "-d", reader],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as err:
        raise SystemExit(
            f"--catalyst-stage: cannot read {reader}'s dynamic section ({err})"
        )
    if "(RUNPATH)" not in dynamic:
        raise SystemExit(
            f"--catalyst-stage: {reader} has no DT_RUNPATH; rebuild it with "
            "-DGS_READER_RUNPATH=ON, or its DT_RPATH loads ParaView from Lustre"
        )
    _STAGE_CACHE["runpath"] = True


def catalyst_stage(exp):
    """The run's catalyst_stage record: {"enabled": False}, or the stage.

    Only in transit Catalyst readers are staged, and never Paper 1's jobs
    (as run, #71). The copy goes to the reader nodes alone, which the MPMD
    launch places last. The two-step launch does not fix the reader's nodes,
    so its runs are not staged, and their settings say so.
    """
    if (
        CATALYST_STAGE == "off"
        or exp["type"] != "intransit"
        or exp.get("paper") == "paper1"
        or not exp.get("stage_pipeline", "").startswith("catalyst_")
        or exp.get("launch") == "steps"
    ):
        return {"enabled": False}
    # By name, ParaView finds the AcceleratedAlgorithms plugin only in the
    # install it was built in; a staged isosurface needs the script to load
    # it by path from CATALYST_LIB_DIR (#126).
    if (
        exp["stage_pipeline"] == "catalyst_isosurface"
        and "CATALYST_LIB_DIR" not in CATALYST_ISOSURFACE_TEMPLATE
    ):
        raise SystemExit(
            f"{exp['id']}: a staged isosurface needs the plugin loaded by path "
            "from CATALYST_LIB_DIR (#126); merge it first"
        )
    method = CATALYST_STAGE
    if method == "auto":
        method = (
            "sbcast" if exp["stage_nodes"] >= CATALYST_STAGE_SBCAST_MIN_NODES else "tar"
        )
    check_reader_runpath()
    tarball, sha256 = catalyst_stage_tarball()
    return {
        "enabled": True,
        "method": method,
        "dir": CATALYST_STAGE_DIR,
        "tarball": tarball,
        "sha256": sha256,
    }


# llvmpipe's shader cache off. Mesa keeps it in ~/.cache, which in a Shaheen
# job is /scratch/$USER/.cache on Lustre, and every rank on every node maps
# its index file to write it. When the shaders a pipeline needs were not
# cached yet, the ranks stopped in their first render, asleep on Lustre locks,
# until the time limit: 20 of 21 Paper 2 inline Catalyst render, volume and
# isosurface runs did (sites/shaheen/README.md, "Inline Catalyst hang"). The
# cache only saves the next process its compile; each rank keeps its shaders
# in memory anyway. Paper 1 jobs use softpipe, which compiles nothing, and
# keep their environment as they were run.
MESA_CACHE_LINE = """# llvmpipe's shader cache is on Lustre, where uncached ranks hung (README).
export MESA_SHADER_CACHE_DISABLE=true
"""

# Runs before the run's PHASE run_start, so the copy is timed on its own
# (PHASE stage_start / stage_end) and not as the run's start-up. One task per
# reader node, on the nodes the MPMD launch then names for the readers.
STAGE_SRUN = (
    "srun --overlap --network=no_vni --mpi=none --nodes={stage_nodes} "
    "--nodelist={nodelist} --ntasks={stage_nodes} --ntasks-per-node=1 "
    "--cpus-per-task=1 --mem=4G"
)

# The staged job names each program's nodes: the job's first nodes for the
# simulation, its last for the readers. Without names, Slurm does not put an
# MPMD launch's second program on the job's last nodes: in job 16139690 the
# copy went to nid02813-02816 and the readers ran on nid02811-02812 and
# nid02815-02816, so half of them loaded ParaView from Lustre and could not
# find the staged AcceleratedAlgorithms plugin.
STAGE_NODELISTS = """# --- Catalyst staging: the simulation's and the readers' nodes ---
JOB_HOSTS=$(scontrol show hostnames "$SLURM_JOB_NODELIST")
SIM_NODELIST=$(scontrol show hostlist "$(echo "$JOB_HOSTS" | head -n {sim_nodes} | paste -sd, -)")
STAGE_NODELIST=$(scontrol show hostlist "$(echo "$JOB_HOSTS" | tail -n {stage_nodes} | paste -sd, -)")
STAGE_NODE1=$(echo "$JOB_HOSTS" | tail -n {stage_nodes} | head -n 1)
unset JOB_HOSTS
if [ -z "$SIM_NODELIST" ] || [ -z "$STAGE_NODELIST" ] || [ -z "$STAGE_NODE1" ]; then
    echo "JOB ABORTED: could not split the job's nodes ($SLURM_JOB_NODELIST)."
    exit 1
fi
"""

# Run on each reader node once the tarball is in the stage directory: check
# its bytes against the recorded sha256 (the tarball could have changed since
# generation), unpack it, and check the copy holds Catalyst's libraries (a
# copy without them would not fail the run: the loader would quietly take
# them from the Lustre install). The directory is created here with mode 700
# and must not exist yet, so nothing another user left in /tmp is loaded.
STAGE_MKDIR = "mkdir -m 700 $CATALYST_STAGE_DIR"
STAGE_UNPACK = (
    'echo \\"{sha256}  $CATALYST_STAGE_DIR/stage.tar\\" | sha256sum -c --quiet '
    "&& tar -C $CATALYST_STAGE_DIR -xf $CATALYST_STAGE_DIR/stage.tar "
    "&& rm -f $CATALYST_STAGE_DIR/stage.tar "
    "&& test -f $CATALYST_STAGE_DIR/lib/catalyst/libcatalyst-paraview.so "
    "&& test -f $CATALYST_STAGE_DIR/lib/libcatalyst.so.3"
)

STAGE_SETUP_TAR = """# --- Catalyst node-local staging (--catalyst-stage tar) ---
CATALYST_STAGE_DIR={dir}
ST0=$(date +%s.%N); echo "PHASE stage_start $ST0"
# Each reader node copies the tarball from Lustre and unpacks it.
if ! {srun} bash -c "{mkdir} && cp {tarball} $CATALYST_STAGE_DIR/stage.tar && {unpack}"; then
    echo "JOB ABORTED: staging {tarball} to $CATALYST_STAGE_DIR failed."
    {srun} rm -rf -- $CATALYST_STAGE_DIR
    exit 1
fi
"""

STAGE_SETUP_SBCAST = """# --- Catalyst node-local staging (--catalyst-stage sbcast) ---
CATALYST_STAGE_DIR={dir}
ST0=$(date +%s.%N); echo "PHASE stage_start $ST0"
# sbcast copies to a job step's nodes. A step that only sleeps holds the
# reader nodes and writes its step ID, so the tarball reaches those nodes
# alone; then each unpacks its copy.
# sbcast does not create the directory it writes to, so every reader node
# makes it first, in a step of its own that must finish before the copy.
STEP_FILE=$OUTPUT_DIR/stage_step.$SLURM_JOB_ID
rm -f $STEP_FILE
STAGE_OK=0
HOLD_PID=
if {srun} bash -c "{mkdir}"; then
    {srun} bash -c "[ \\$SLURM_PROCID = 0 ] && echo \\$SLURM_STEP_ID > $STEP_FILE; exec sleep 3600" &
    HOLD_PID=$!
    for i in $(seq 1 600); do [ -s $STEP_FILE ] && break; sleep 0.1; done
fi
if [ -s $STEP_FILE ] \\
    && sbcast --jobid=$SLURM_JOB_ID.$(cat $STEP_FILE) -f {tarball} $CATALYST_STAGE_DIR/stage.tar \\
    && {srun} bash -c "{unpack}"; then
    STAGE_OK=1
fi
if [ -n "$HOLD_PID" ]; then kill $HOLD_PID 2>/dev/null; wait $HOLD_PID 2>/dev/null; fi
rm -f $STEP_FILE
if [ $STAGE_OK != 1 ]; then
    echo "JOB ABORTED: staging {tarball} to $CATALYST_STAGE_DIR failed."
    {srun} rm -rf -- $CATALYST_STAGE_DIR
    exit 1
fi
"""

# After either method: the copy's time and what the reader resolves from the
# stage, beside the results (the telemetry's ldd.txt and env.txt show the
# job-wide environment, which names the Lustre install).
STAGE_RECORD = """ST1=$(date +%s.%N); echo "PHASE stage_end $ST1"
{{
    echo "catalyst_stage {method}: $CATALYST_STAGE_DIR from {tarball} (sha256 {sha256})"
    echo "stage_start $ST0"
    echo "stage_end $ST1"
    echo "reader nodes $STAGE_NODELIST"
    echo "== ldd of the reader on a reader node, the stage first on LD_LIBRARY_PATH"
    {srun1} env LD_LIBRARY_PATH=$CATALYST_STAGE_DIR/lib:$LD_LIBRARY_PATH ldd $EXE_STAGE
}} > "{results_dir}/{id}_stage.txt" 2>&1
"""

STAGE_CLEANUP = """# Remove the node-local copy, so the next job on these nodes starts clean.
{srun} rm -rf -- $CATALYST_STAGE_DIR || echo "Could not remove $CATALYST_STAGE_DIR on every reader node"
"""


def stage_scripts(exp, results_dir):
    """The job's staging and clean-up blocks ("" when not staged)."""
    stage = catalyst_stage(exp)
    if not stage["enabled"]:
        return "", ""
    srun = STAGE_SRUN.format(stage_nodes=exp["stage_nodes"], nodelist="$STAGE_NODELIST")
    srun1 = STAGE_SRUN.format(stage_nodes=1, nodelist="$STAGE_NODE1")
    template = STAGE_SETUP_SBCAST if stage["method"] == "sbcast" else STAGE_SETUP_TAR
    setup = (
        STAGE_NODELISTS.format(
            sim_nodes=exp["sim_nodes"], stage_nodes=exp["stage_nodes"]
        )
        + template.format(
            dir=stage["dir"],
            tarball=stage["tarball"],
            srun=srun,
            mkdir=STAGE_MKDIR,
            unpack=STAGE_UNPACK.format(sha256=stage["sha256"]),
        )
        + STAGE_RECORD.format(
            method=stage["method"],
            tarball=stage["tarball"],
            sha256=stage["sha256"],
            srun1=srun1,
            results_dir=results_dir,
            id=exp["id"],
        )
    )
    return setup, STAGE_CLEANUP.format(srun=srun)


def generate_settings_json(exp, output_dir, copied_files, args):
    is_init = exp["workload"] == "initialization"
    init_noise_level = 0.01
    run_noise_level = 0.00001
    steps = exp["total_steps"]

    # SST must not reopen per step, so in transit never overwrites. Paper 2 also
    # writes every inline ADIOS2 step; Paper 1 keeps its overwrite (#71).
    uses_adios = exp["type"] == "intransit" or (
        exp["backend"] == "adios" and exp.get("paper") != "paper1"
    )
    overwrite = (
        False if uses_adios else (True if exp.get("workload") == "data_save" else False)
    )

    config = {
        "L": exp["grid_size"],
        "Du": 0.2,
        "Dv": 0.1,
        "F": 0.03,
        "k": 0.0545,
        "dt": 2.0,
        "noise": init_noise_level if is_init else run_noise_level,
        "steps": steps,
        "burn_in_steps": GLOBAL_SETTINGS["init_burn_in"] if is_init else 0,
        "plotgap": steps + 1 if is_init else GLOBAL_SETTINGS["plotgap"],
        "output_file_name": f"{output_dir}/data/grayScott",
        "output_type": "adhoc",
        "mesh_type": "image",
        "checkpoint": True if is_init else False,
        "checkpoint_freq": steps if is_init else 0,
        "checkpoint_output": f"{output_dir}/data/checkpoint.bp" if is_init else "",
        "restart": False if is_init else True,
        "restart_input": f"{os.path.join(args.results_dir, exp.get('parent_id', ''))}/data/checkpoint.bp"
        if not is_init
        else "",
        "overwrite_last_step": overwrite,
        "catalyst_script_path": "",
        "catalyst_lib_path": CATALYST_LIB_PATH,
        # Where the reader loaded ParaView from, when staged (--catalyst-stage).
        "catalyst_stage": catalyst_stage(exp),
        "kombynelite_script_path": "",
        "adios_config": f"{output_dir}/adios2.xml",
        "adios_span": False,
        "adios_memory_selection": True,
        "adios_endstep_barrier": ADIOS_ENDSTEP_BARRIER,
        "read_decomposition": reader_decomposition(exp)[0],
        "reader_shared_planes": reader_decomposition(exp)[1],
        "ascent_options": "",
    }
    # Which configuration this run repeats (REPEATS), for corpus_index.py.
    if "repeat_of" in exp:
        config["repeat_of"] = exp["repeat_of"]
        config["repeat"] = exp["repeat"]
        config["repeats"] = exp["repeats"]

    if is_init:
        config["output_type"] = "none"
    elif exp["type"] == "intransit":
        config["output_type"] = "adios"
        config_stage = config.copy()
        config_stage["output_file_name"] = f"{output_dir}/data/grayScott_staged"
        parts = exp.get("stage_pipeline", "adios_data").split("_")
        stage_backend = parts[0]

        if stage_backend == "catalyst":
            if exp["workload"] == "data_save":
                config_stage["output_type"] = "catalyst_io"
                config_stage[
                    "output_file_name"
                ] = f"{output_dir}/data/grayScott_staged-%04ts.vtpd"
            else:
                config_stage["output_type"] = "catalyst_insitu"
        elif stage_backend == "adios":
            config_stage[
                "output_type"
            ] = "adios_writer"  # Map "adios" to "adios_writer" for the C++ factory
        else:
            config_stage["output_type"] = stage_backend

        if stage_backend == "ascent":
            config_stage["ascent_options"] = f"{output_dir}/ascent_options.yaml"
            if ascent_renders(exp):
                config_stage["ascent_tiled_rendering"] = ASCENT_TILED_RENDERING
        elif (
            stage_backend == "catalyst"
            and config_stage["output_type"] == "catalyst_insitu"
        ):
            config_stage["catalyst_script_path"] = f"{output_dir}/" + os.path.basename(
                copied_files["pipeline"]
            )

        with open(f"{output_dir}/settings-stage.json", "w") as f:
            json.dump(config_stage, f, indent=4)
    else:
        if exp["backend"] == "adios":
            config["output_type"] = "adios"
        elif exp["backend"] == "ascent":
            config["output_type"] = "ascent"
            config["ascent_options"] = f"{output_dir}/ascent_options.yaml"
            if ascent_renders(exp):
                config["ascent_tiled_rendering"] = ASCENT_TILED_RENDERING
        elif exp["backend"] == "catalyst":
            if exp["workload"] == "data_save":
                config["output_type"] = "catalyst_io"
                config["output_file_name"] = f"{output_dir}/data/grayScott-%04ts.vtpd"
            else:
                config["output_type"] = "catalyst_insitu"
                config["catalyst_script_path"] = copied_files["pipeline"]
        elif exp["backend"] == "kombyne":
            config["output_type"] = "kombyne"
            config["kombynelite_script_path"] = copied_files["pipeline"]
        elif exp["backend"] == "baseline":
            config["output_type"] = "pvti"
            config["output_file_name"] = f"{output_dir}/data/grayScott-%04ts.vti"
            config["plotgap"] = steps + 2000

    with open(f"{output_dir}/settings.json", "w") as f:
        json.dump(config, f, indent=4)


def generate_adios_xml(exp, output_dir):
    engine = "SST" if exp["type"] == "intransit" else "BP5"
    rendezvous = 1 if exp["type"] == "intransit" else 0

    # Automatically use RDMA for in-transit to bypass OFI socket limits, MPI for inline
    data_transport = (
        exp.get("transport", "RDMA") if exp["type"] == "intransit" else "MPI"
    )

    # Simulation aggregators (1 per simulation node)
    sim_aggregators = exp["sim_nodes"]

    # Staging aggregators (1 per staging node). Default to 1 for inline runs (unused)
    stage_aggregators = exp.get("stage_nodes", 1)

    xml_content = ADIOS_XML_TEMPLATE.format(
        engine_type=engine,
        rendezvous=rendezvous,
        data_transport=data_transport,
        sim_aggregators=sim_aggregators,
        stage_aggregators=stage_aggregators,
        queue_limit=exp.get("queue_limit", 1),
        queue_full_policy=QUEUE_FULL_POLICY,
    )
    with open(f"{output_dir}/adios2.xml", "w") as f:
        f.write(xml_content)


def copy_pipeline_files(exp, output_dir, repo_root):
    files_to_copy = {}
    mesh_spacing = 0.1
    physical_L = float(exp["grid_size"]) * mesh_spacing
    center_val = physical_L / 2.0
    slice_offset_val = center_val + (mesh_spacing * 6.5)
    cam_up_x, cam_up_y, cam_up_z = 0.206668, 0.933382, -0.293403

    generate_adios_xml(exp, output_dir)

    effective_backend = exp["backend"]
    if exp["backend"] == "baseline":
        return files_to_copy

    if exp["type"] == "intransit" and exp["backend"] == "adios":
        if "stage_pipeline" in exp:
            pipeline_key = exp["stage_pipeline"]
            effective_backend = pipeline_key.split("_")[0]
    else:
        wl_suffix = (
            "data"
            if exp["workload"] == "data_save"
            else ("render" if exp["workload"] == "rendering" else exp["workload"])
        )
        pipeline_key = f"{effective_backend}_{wl_suffix}"

    actions_filename = (
        f"{pipeline_key}.yaml"
        if effective_backend in ["ascent", "kombyne"]
        else f"{pipeline_key}.py"
    )
    dst_action = os.path.join(output_dir, actions_filename)

    # CRITICAL FIX: Separate the camera math so Catalyst zoom doesn't break Ascent
    if effective_backend == "ascent":
        # Original working Ascent camera
        cam_x, cam_y, cam_z = (
            center_val - (physical_L * 1.85),
            center_val + (physical_L * 1.10),
            center_val + (physical_L * 1.85),
        )
        parallel_scale = physical_L * 1.60
    else:
        # Catalyst zoomed out 20%
        cam_x, cam_y, cam_z = (
            center_val - (physical_L * 2.22),
            center_val + (physical_L * 1.32),
            center_val + (physical_L * 2.22),
        )
        parallel_scale = physical_L * 2.21

    # Calculate the voxel diagonal for the raycaster
    ray_step = float(mesh_spacing) * 1.73205

    # Common format dictionary to pass to all templates
    fmt_args = {
        "cam_x": cam_x,
        "cam_y": cam_y,
        "cam_z": cam_z,
        "center": center_val,
        "cam_up_x": cam_up_x,
        "cam_up_y": cam_up_y,
        "cam_up_z": cam_up_z,
        "slice_offset": slice_offset_val,
        "parallel_scale": parallel_scale,
        "ray_step": ray_step,
        # Ascent volume plots take `samples` per ray across the whole grid.
        # About 9 per cell crossed keeps the image free of banding that
        # changes with the rank count (docs/in-situ-backends.md, Ascent);
        # fewer is cheaper. --volume-samples-per-cell sets it.
        "volume_samples": int(
            math.ceil(VOLUME_SAMPLES_PER_CELL * math.sqrt(3) * exp["grid_size"])
        ),
        "tiled_rendering": "true" if ASCENT_TILED_RENDERING else "false",
    }

    if exp["paper"] == "paper1":
        return write_paper1_pipeline(
            exp,
            effective_backend,
            output_dir,
            repo_root,
            files_to_copy,
            physical_L,
            center_val,
            slice_offset_val,
            cam_up_x,
            cam_up_y,
            cam_up_z,
        )

    if effective_backend == "ascent":
        if "rendering" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(ASCENT_RENDER_TEMPLATE.format(**fmt_args))
        elif "volume" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(ASCENT_VOLUME_TEMPLATE.format(**fmt_args))
        elif "isosurface" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(ASCENT_ISOSURFACE_TEMPLATE.format(**fmt_args))
        else:
            shutil.copy2(
                os.path.join(
                    repo_root, "Miniapps/gray-scott", PIPELINE_FILES["ascent_data"]
                ),
                dst_action,
            )

        opts_path = os.path.join(output_dir, "ascent_options.yaml")
        with open(opts_path, "w") as f:
            f.write(
                ASCENT_OPTIONS_TEMPLATE.format(
                    actions_file=actions_filename,
                    timings="true" if ASCENT_TIMINGS else "false",
                )
            )
        files_to_copy["ascent_opts"] = opts_path

    elif effective_backend == "catalyst":
        if "rendering" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(CATALYST_RENDER_TEMPLATE.format(**fmt_args))
        elif "volume" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(CATALYST_VOLUME_TEMPLATE.format(**fmt_args))
        elif "isosurface" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(CATALYST_ISOSURFACE_TEMPLATE.format(**fmt_args))
        else:
            shutil.copy2(
                os.path.join(
                    repo_root, "Miniapps/gray-scott", PIPELINE_FILES["catalyst_data"]
                ),
                dst_action,
            )
        files_to_copy["pipeline"] = dst_action

    elif effective_backend == "kombyne":
        if "rendering" in exp["workload"]:
            with open(dst_action, "w") as f:
                f.write(KOMBYNE_RENDER_TEMPLATE.format(**fmt_args))
        else:
            with open(dst_action, "w") as f:
                f.write(KOMBYNE_DATA_TEMPLATE)
        files_to_copy["pipeline"] = dst_action

    return files_to_copy


def write_paper1_pipeline(
    exp,
    backend,
    output_dir,
    repo_root,
    files_to_copy,
    physical_L,
    center_val,
    slice_offset_val,
    cam_up_x,
    cam_up_y,
    cam_up_z,
):
    """Paper 1's pipeline files, written as on master when Paper 1 was verified (#71)."""
    cam_x, cam_y, cam_z = (
        center_val - (physical_L * 1.85),
        center_val + (physical_L * 1.10),
        center_val + (physical_L * 1.85),
    )
    parallel_scale = physical_L * 1.60
    cam_dist_val = center_val * 4.88
    if backend not in ("ascent", "catalyst", "kombyne"):
        return files_to_copy  # ADIOS2 data: nothing beyond adios2.xml
    render = exp["workload"] == "rendering"
    names = {
        "ascent": ("ascent-extract-png.yaml", PIPELINE_FILES["ascent_data"]),
        "catalyst": ("catalyst-extract-jpg.py", PIPELINE_FILES["catalyst_data"]),
        "kombyne": ("kombyne-extract-png.yaml", PIPELINE_FILES["kombyne_data"]),
    }
    actions_filename = (
        names[backend][0] if render else os.path.basename(names[backend][1])
    )
    dst_action = os.path.join(output_dir, actions_filename)
    if backend == "ascent":
        if render:
            with open(dst_action, "w") as f:
                f.write(
                    PAPER1_ASCENT_RENDER_TEMPLATE.format(
                        cam_x=cam_x,
                        cam_y=cam_y,
                        cam_z=cam_z,
                        center=center_val,
                        cam_up_x=cam_up_x,
                        cam_up_y=cam_up_y,
                        cam_up_z=cam_up_z,
                        slice_offset=slice_offset_val,
                    )
                )
        else:
            shutil.copy2(
                os.path.join(
                    repo_root, "Miniapps/gray-scott", PIPELINE_FILES["ascent_data"]
                ),
                dst_action,
            )
        opts_path = os.path.join(output_dir, "ascent_options.yaml")
        with open(opts_path, "w") as f:
            f.write(
                PAPER1_ASCENT_OPTIONS_TEMPLATE.format(actions_file=actions_filename)
            )
        files_to_copy["ascent_opts"] = opts_path
    elif backend == "catalyst":
        if render:
            with open(dst_action, "w") as f:
                f.write(
                    PAPER1_CATALYST_RENDER_TEMPLATE.format(
                        cam_x=cam_x,
                        cam_y=cam_y,
                        cam_z=cam_z,
                        center=center_val,
                        parallel_scale=parallel_scale,
                        cam_up_x=cam_up_x,
                        cam_up_y=cam_up_y,
                        cam_up_z=cam_up_z,
                        slice_offset=slice_offset_val,
                    )
                )
        else:
            shutil.copy2(
                os.path.join(
                    repo_root, "Miniapps/gray-scott", PIPELINE_FILES["catalyst_data"]
                ),
                dst_action,
            )
        files_to_copy["pipeline"] = dst_action
    elif backend == "kombyne":
        with open(dst_action, "w") as f:
            if render:
                f.write(
                    PAPER1_KOMBYNE_RENDER_TEMPLATE.format(
                        cam_dist=cam_dist_val,
                        center=center_val,
                        slice_offset=slice_offset_val,
                    )
                )
            else:
                f.write(PAPER1_KOMBYNE_DATA_TEMPLATE)
        files_to_copy["pipeline"] = dst_action
    return files_to_copy


def generate_scripts(args):
    os.makedirs(args.output_dir, exist_ok=True)
    EXPERIMENTS = []
    init_info = {}

    def ensure_init(grid_size):
        if grid_size not in init_info:
            init_nodes = INIT_NODE_MAP.get(grid_size, 512)
            init_id = f"init_N{init_nodes:04d}_L{grid_size}"

            # Explicit restart steps based on grid size
            if grid_size == 8192:
                base_steps = 200000
            elif grid_size == 4096:
                base_steps = 130000
            else:
                base_steps = GLOBAL_SETTINGS["init_steps"]  # 65000

            EXPERIMENTS.append(
                {
                    "id": init_id,
                    "paper": "init",
                    "type": "inline",
                    "backend": "adios",
                    "workload": "initialization",
                    "sim_nodes": init_nodes,
                    "grid_size": grid_size,
                    "total_steps": base_steps,
                }
            )
            init_info[grid_size] = (init_id, base_steps)
        return init_info[grid_size]

    # Map the suffix for the directory ID back to the workload logic
    WORKLOAD_MAPPING = [
        ("data", "data_save"),
        ("render", "rendering"),
        ("volume", "volume"),
        ("isosurface", "isosurface"),
    ]

    # --- Paper 1 Generation (Keeping Kombyne) ---
    p1_nodes, p1_grid, p1_stage = 64, 2048, 4
    pid, p1_init_steps = ensure_init(p1_grid)
    p1_target = p1_init_steps + GLOBAL_SETTINGS["paper1_run_steps"]

    EXPERIMENTS.append(
        {
            "id": f"paper1_func_N{p1_nodes:04d}_baseline",
            "paper": "paper1",
            "type": "inline",
            "backend": "baseline",
            "workload": "none",
            "sim_nodes": p1_nodes,
            "grid_size": p1_grid,
            "parent_id": pid,
            "total_steps": p1_target,
        }
    )
    EXPERIMENTS.append(
        {
            "id": f"paper1_func_N{p1_nodes:04d}_inline_adios_data",
            "paper": "paper1",
            "type": "inline",
            "backend": "adios",
            "workload": "data_save",
            "sim_nodes": p1_nodes,
            "grid_size": p1_grid,
            "parent_id": pid,
            "total_steps": p1_target,
        }
    )

    for backend in ["ascent", "catalyst", "kombyne"]:
        EXPERIMENTS.append(
            {
                "id": f"paper1_func_N{p1_nodes:04d}_inline_{backend}_data",
                "paper": "paper1",
                "type": "inline",
                "backend": backend,
                "workload": "data_save",
                "sim_nodes": p1_nodes,
                "grid_size": p1_grid,
                "parent_id": pid,
                "total_steps": p1_target,
            }
        )
        EXPERIMENTS.append(
            {
                "id": f"paper1_func_N{p1_nodes:04d}_inline_{backend}_render",
                "paper": "paper1",
                "type": "inline",
                "backend": backend,
                "workload": "rendering",
                "sim_nodes": p1_nodes,
                "grid_size": p1_grid,
                "parent_id": pid,
                "total_steps": p1_target,
            }
        )
        # The analysis reader has no Kombyne backend (only Ascent and Catalyst),
        # so there is no Kombyne in transit run; Paper 1 never had one (#71).
        if backend == "kombyne":
            continue
        EXPERIMENTS.append(
            {
                "id": f"paper1_func_N{p1_nodes:04d}_transit_{backend}_render",
                "paper": "paper1",
                "type": "intransit",
                "backend": "adios",
                "workload": "rendering",
                "sim_nodes": p1_nodes,
                "stage_nodes": p1_stage,
                "grid_size": p1_grid,
                "stage_pipeline": f"{backend}_render",
                "parent_id": pid,
                "total_steps": p1_target,
            }
        )

    # --- Paper 2 Generation (Carte Blanche Matrix + Comm/Compute Bound Stockpiling) ---

    # 1. Strong Scaling Inline
    for nodes in STRONG_SCALING_NODES:
        grid = STRONG_GRID
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS["run_steps"]
        base_id = f"paper2_strong_N{nodes:04d}"

        EXPERIMENTS.append(
            {
                "id": f"{base_id}_baseline",
                "paper": "paper2",
                "type": "inline",
                "backend": "baseline",
                "workload": "none",
                "sim_nodes": nodes,
                "grid_size": grid,
                "parent_id": pid,
                "total_steps": target_steps,
            }
        )
        EXPERIMENTS.append(
            {
                "id": f"{base_id}_adios_data",
                "paper": "paper2",
                "type": "inline",
                "backend": "adios",
                "workload": "data_save",
                "sim_nodes": nodes,
                "grid_size": grid,
                "parent_id": pid,
                "total_steps": target_steps,
            }
        )

        for backend in ["ascent", "catalyst"]:
            for wl_suffix, wl_type in WORKLOAD_MAPPING:
                EXPERIMENTS.append(
                    {
                        "id": f"{base_id}_{backend}_{wl_suffix}",
                        "paper": "paper2",
                        "type": "inline",
                        "backend": backend,
                        "workload": wl_type,
                        "sim_nodes": nodes,
                        "grid_size": grid,
                        "parent_id": pid,
                        "total_steps": target_steps,
                    }
                )

    # 2. Weak Scaling Inline
    for nodes, grid in WEAK_SCALING_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS["run_steps"]
        base_id = f"paper2_weak_N{nodes:04d}"

        EXPERIMENTS.append(
            {
                "id": f"{base_id}_baseline",
                "paper": "paper2",
                "type": "inline",
                "backend": "baseline",
                "workload": "none",
                "sim_nodes": nodes,
                "grid_size": grid,
                "parent_id": pid,
                "total_steps": target_steps,
            }
        )
        EXPERIMENTS.append(
            {
                "id": f"{base_id}_adios_data",
                "paper": "paper2",
                "type": "inline",
                "backend": "adios",
                "workload": "data_save",
                "sim_nodes": nodes,
                "grid_size": grid,
                "parent_id": pid,
                "total_steps": target_steps,
            }
        )

        for backend in ["ascent", "catalyst"]:
            for wl_suffix, wl_type in WORKLOAD_MAPPING:
                EXPERIMENTS.append(
                    {
                        "id": f"{base_id}_{backend}_{wl_suffix}",
                        "paper": "paper2",
                        "type": "inline",
                        "backend": backend,
                        "workload": wl_type,
                        "sim_nodes": nodes,
                        "grid_size": grid,
                        "parent_id": pid,
                        "total_steps": target_steps,
                    }
                )

    # 3. Standard Transit Runs (Small, Compressed, Hero)
    for name, nodes, grid, stage_nodes in TRANSIT_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS["run_steps"]
        base_id = f"paper2_transit_{name}_N{nodes:04d}"

        # ADIOS Data Save
        EXPERIMENTS.append(
            {
                "id": f"{base_id}_adios_data",
                "paper": "paper2",
                "type": "intransit",
                "backend": "adios",
                "workload": "data_save",
                "sim_nodes": nodes,
                "stage_nodes": stage_nodes,
                "grid_size": grid,
                "stage_pipeline": "adios_data",
                "parent_id": pid,
                "total_steps": target_steps,
            }
        )

        for backend in ["ascent", "catalyst"]:
            for wl_suffix, wl_type in WORKLOAD_MAPPING:
                EXPERIMENTS.append(
                    {
                        "id": f"{base_id}_{backend}_{wl_suffix}",
                        "paper": "paper2",
                        "type": "intransit",
                        "backend": "adios",
                        "workload": wl_type,
                        "sim_nodes": nodes,
                        "stage_nodes": stage_nodes,
                        "grid_size": grid,
                        "stage_pipeline": f"{backend}_{wl_suffix}",
                        "parent_id": pid,
                        "total_steps": target_steps,
                    }
                )

    # 4. Hero Scale Transit Sweep
    for name, nodes, grid, stage_nodes in TRANSIT_SWEEP_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        target_steps = p_init_steps + GLOBAL_SETTINGS["run_steps"]
        base_id = f"paper2_transit_{name}_N{nodes:04d}_S{stage_nodes:03d}"

        # ADIOS Data Save Transit
        EXPERIMENTS.append(
            {
                "id": f"{base_id}_adios_data",
                "paper": "paper2",
                "type": "intransit",
                "backend": "adios",
                "workload": "data_save",
                "sim_nodes": nodes,
                "stage_nodes": stage_nodes,
                "grid_size": grid,
                "stage_pipeline": "adios_data",
                "parent_id": pid,
                "total_steps": target_steps,
            }
        )

        for backend in ["ascent", "catalyst"]:
            for wl_suffix, wl_type in WORKLOAD_MAPPING:
                EXPERIMENTS.append(
                    {
                        "id": f"{base_id}_{backend}_{wl_suffix}",
                        "paper": "paper2",
                        "type": "intransit",
                        "backend": "adios",
                        "workload": wl_type,
                        "sim_nodes": nodes,
                        "stage_nodes": stage_nodes,
                        "grid_size": grid,
                        "stage_pipeline": f"{backend}_{wl_suffix}",
                        "parent_id": pid,
                        "total_steps": target_steps,
                    }
                )

    # 5. #72 step 1: transport matrix (Catalyst and Ascent slices).
    for name, nodes, grid, stage_nodes in XPORT_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        for transport in XPORT_TRANSPORTS:
            for launch in XPORT_LAUNCHES:
                for backend in ["ascent", "catalyst"]:
                    EXPERIMENTS.append(
                        {
                            "id": f"xport_transit_{transport.lower()}_{launch}_{name}_N{nodes:04d}_S{stage_nodes:03d}_{backend}_render",
                            "paper": "xport",
                            "type": "intransit",
                            "backend": "adios",
                            "workload": "rendering",
                            "sim_nodes": nodes,
                            "stage_nodes": stage_nodes,
                            "grid_size": grid,
                            "stage_pipeline": f"{backend}_render",
                            "parent_id": pid,
                            "total_steps": p_init_steps + XPORT_RUN_STEPS,
                            "transport": transport,
                            "launch": launch,
                            "time_limit": XPORT_TIME_LIMIT,
                        }
                    )

    # 6. #72 step 2: RDMA scaling at 4096^3 (Ascent and Catalyst slices).
    pid, p_init_steps = ensure_init(SCALE_GRID)
    for nodes, stage_nodes in SCALE_CONFIGS:
        for launch in SCALE_LAUNCHES:
            for backend in ["ascent", "catalyst"]:
                EXPERIMENTS.append(
                    {
                        "id": f"scale_transit_rdma_{launch}_N{nodes:04d}_S{stage_nodes:03d}_{backend}_render",
                        "paper": "scale",
                        "type": "intransit",
                        "backend": "adios",
                        "workload": "rendering",
                        "sim_nodes": nodes,
                        "stage_nodes": stage_nodes,
                        "grid_size": SCALE_GRID,
                        "stage_pipeline": f"{backend}_render",
                        "parent_id": pid,
                        "total_steps": p_init_steps + SCALE_RUN_STEPS,
                        "transport": "RDMA",
                        "launch": launch,
                        "time_limit": SCALE_TIME_LIMIT,
                    }
                )

    pid, p_init_steps = ensure_init(ADIOS_SWEEP_GRID)
    for nodes, stage_nodes, queue_limit in ADIOS_SWEEP_CONFIGS:
        EXPERIMENTS.append(
            {
                # "scale" first and a "transit" component, which orchestrate.py
                # reads as the paper and the in transit type.
                "id": f"scale_transit_adios_sweep_N{nodes:04d}_S{stage_nodes:03d}_q{queue_limit}_readonly",
                "paper": "scale",
                "type": "intransit",
                "backend": "adios",
                "workload": "transport",
                "sim_nodes": nodes,
                "stage_nodes": stage_nodes,
                "grid_size": ADIOS_SWEEP_GRID,
                "stage_pipeline": "readonly_transport",
                "parent_id": pid,
                "total_steps": p_init_steps + ADIOS_SWEEP_RUN_STEPS,
                "transport": "RDMA",
                "launch": "mpmd",
                "queue_limit": queue_limit,
                "time_limit": ADIOS_SWEEP_TIME_LIMIT,
            }
        )

    # 7. Reader cost study: every pipeline, RDMA, MPMD.
    for name, nodes, grid, stage_nodes in PIPE_CONFIGS:
        pid, p_init_steps = ensure_init(grid)
        for backend in ["ascent", "catalyst"]:
            for wl_suffix, wl_type in WORKLOAD_MAPPING:
                if wl_type == "data_save":
                    continue
                # 4.4 GB per field per reader: the isosurface runs out of
                # memory there, before and after the reader fixes
                # (sites/shaheen/README.md, "In transit reader costs").
                if name == "s256" and wl_type == "isosurface":
                    continue
                EXPERIMENTS.append(
                    {
                        "id": f"pipe_transit_rdma_mpmd_{name}_N{nodes:04d}_S{stage_nodes:03d}_{backend}_{wl_suffix}",
                        "paper": "pipe",
                        "type": "intransit",
                        "backend": "adios",
                        "workload": wl_type,
                        "sim_nodes": nodes,
                        "stage_nodes": stage_nodes,
                        "grid_size": grid,
                        "stage_pipeline": f"{backend}_{wl_suffix}",
                        "parent_id": pid,
                        "total_steps": p_init_steps + PIPE_RUN_STEPS,
                        "transport": "RDMA",
                        "launch": "mpmd",
                        "time_limit": PIPE_TIME_LIMIT,
                    }
                )

    # Repeats (REPEATS): every measured run except Paper 1's becomes
    # <id>_r01 ... <id>_rNN, each its own results directory and job; the
    # initialisations stay single (the repeats share their checkpoint).
    # getattr: sites/kw61316/run_generator_locally.py builds its own args.
    repeats = getattr(args, "repeats", 1)
    if repeats > 1 or getattr(args, "repeats_always_suffix", False):
        expanded = []
        for exp in EXPERIMENTS:
            if exp["workload"] == "initialization" or exp.get("paper") == "paper1":
                expanded.append(exp)
                continue
            for k in range(1, repeats + 1):
                rep_exp = dict(exp)
                rep_exp["id"] = f"{exp['id']}_r{k:02d}"
                rep_exp["repeat_of"] = exp["id"]
                rep_exp["repeat"] = k
                rep_exp["repeats"] = repeats
                expanded.append(rep_exp)
        EXPERIMENTS = expanded

    # Preflight, before any file is written: a run whose existing settings
    # differ (check_settings_unchanged) stops the whole generation, so
    # nothing beside that run's results (adios2.xml included) is rewritten.
    for exp in EXPERIMENTS:
        if exp["workload"] != "initialization":
            check_settings_unchanged(f"{args.results_dir}/{exp['id']}", exp)

    for exp in EXPERIMENTS:
        sim_ranks = exp["sim_nodes"] * SYSTEM_CONFIG["mpi_per_node"]
        total_stage_ranks = (
            exp.get("stage_nodes", 0) * 8
        )  # HARDCODED MPMD 8 ranks for staging nodes

        run_output_dir = f"{args.results_dir}/{exp['id']}"
        # Never rewrite a finished initialisation: its settings and adios2.xml
        # belong to the checkpoint they made, and its sbatch would overwrite it.
        if exp["workload"] == "initialization" and os.path.exists(
            f"{run_output_dir}/data/checkpoint.bp"
        ):
            print(f"Keeping {exp['id']}: it already holds a checkpoint")
            continue
        os.makedirs(run_output_dir, exist_ok=True)
        copied_files = copy_pipeline_files(exp, run_output_dir, args.repo_path)
        generate_settings_json(exp, run_output_dir, copied_files, args)
        total_nodes = exp["sim_nodes"] + exp.get("stage_nodes", 0)
        combined_total_ranks = sim_ranks + total_stage_ranks

        # Conditionally inject the global cpus-per-task header ONLY for inline runs
        cpus_line = (
            f"#SBATCH --cpus-per-task={SYSTEM_CONFIG['omp_threads']}"
            if exp["type"] == "inline"
            else ""
        )

        if exp["type"] != "intransit":
            cmd_template = CMD_INLINE
        else:
            cmd_template = (
                CMD_INTRANSIT_STEPS if exp.get("launch") == "steps" else CMD_INTRANSIT
            )
        # A staged run names each program's nodes (STAGE_NODELISTS).
        staged = catalyst_stage(exp)["enabled"]
        command = cmd_template.format(
            sim_nodes=exp["sim_nodes"],
            sim_nodelist=" --nodelist=$SIM_NODELIST" if staged else "",
            stage_nodelist=" --nodelist=$STAGE_NODELIST" if staged else "",
            sim_ranks=sim_ranks,
            stage_nodes=exp.get("stage_nodes", 0),
            stage_ranks=total_stage_ranks,
            mpi_per_node=SYSTEM_CONFIG["mpi_per_node"],
            omp_threads=SYSTEM_CONFIG["omp_threads"],
            total_ranks=combined_total_ranks
            if exp["type"] == "intransit"
            else sim_ranks,
            grid_size=exp["grid_size"],
            logging_level=GLOBAL_SETTINGS["logging_level"],
            reader_env=reader_env(exp),
            # --reader-smt: both hardware threads of the reader's 24 cores.
            reader_cpus="--cpus-per-task=48 --threads-per-core=2"
            if reader_smt(exp)
            else "--cpus-per-task=24",
            reader_hint="" if reader_smt(exp) else "--hint=nomultithread",
        )

        stage_setup, stage_cleanup = stage_scripts(exp, args.results_dir)
        time_limit = exp.get("time_limit", SYSTEM_CONFIG["time_limit"])
        large = total_nodes > WORKQ_MAX_NODES
        if large and _minutes(time_limit) < _minutes(LARGE_RUN_MIN_TIME):
            time_limit = LARGE_RUN_MIN_TIME
        script_content = SBATCH_TEMPLATE.format(
            id=exp["id"],
            account=args.account,
            partition=SYSTEM_CONFIG["partition"],
            qos_line=f"#SBATCH --qos={LARGE_RUN_QOS}" if large else "",
            # A job-wide nomultithread would refuse the reader's second
            # hardware threads; the simulation's srun still asks for it.
            hint_line=""
            if reader_smt(exp) and exp["type"] == "intransit"
            else "#SBATCH --hint=nomultithread",
            total_nodes=total_nodes,
            total_ranks=combined_total_ranks
            if exp["type"] == "intransit"
            else sim_ranks,
            cpus_per_task_line=cpus_line,
            network_line="#SBATCH --network=job_vni"
            if exp.get("launch") == "steps"
            else "",
            mpi_per_node=SYSTEM_CONFIG["mpi_per_node"],
            omp_threads=SYSTEM_CONFIG["omp_threads"],
            time_limit=time_limit,
            output_dir=run_output_dir,
            results_dir=args.results_dir,
            perf_env=args.perf_env,
            repo_path=args.repo_path,
            bin_path=args.bin_path,
            command=command,
            stage_setup=stage_setup,
            stage_cleanup=stage_cleanup,
            telemetry_start=TELEMETRY_START.format(
                repo_path=args.repo_path,
                darshan_start=""
                if args.no_darshan
                else DARSHAN_START.format(darshan_prefix=args.darshan_prefix),
            )
            if args.telemetry
            else "",
            telemetry_stop=TELEMETRY_STOP if args.telemetry else "",
            catalyst_lib_path=CATALYST_LIB_PATH,
            paraview_lib_path=os.path.dirname(CATALYST_LIB_PATH.rstrip("/")),
            gallium_driver="softpipe" if exp.get("paper") == "paper1" else "llvmpipe",
            mesa_cache_line="" if exp.get("paper") == "paper1" else MESA_CACHE_LINE,
        )

        reduce_content = REDUCE_TEMPLATE.format(
            id=exp["id"],
            account=args.account,
            partition=SYSTEM_CONFIG["partition"],
            output_dir=run_output_dir,
            results_dir=args.results_dir,
            perf_env=args.perf_env,
            repo_path=args.repo_path,
            data_cleanup=DATA_CLEANUP.format(results_dir=args.results_dir, id=exp["id"])
            if drops_data_output(exp)
            else "",
            telemetry_reduce=TELEMETRY_REDUCE.format(
                repo_path=args.repo_path,
                results_dir=args.results_dir,
                id=exp["id"],
                darshan_prefix=args.darshan_prefix,
            )
            if args.telemetry
            else "",
        )
        with open(f"{run_output_dir}/reduce.sbat", "w") as f:
            f.write(reduce_content)
        with open(f"{args.output_dir}/{exp['id']}.sbat", "w") as f:
            f.write(script_content)

    print(f"Generated {len(EXPERIMENTS)} scripts in {args.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument(
        "--bin-path",
        required=True,
        help="directory with gray-scott and analysis-reader, built against the "
        "same ParaView as CATALYST_LIB_PATH (config.bash)",
    )
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-dir", default="generated_scripts")
    parser.add_argument("--account", default=SYSTEM_CONFIG["account"])
    parser.add_argument(
        "--volume-samples-per-cell",
        type=float,
        default=VOLUME_SAMPLES_PER_CELL,
        help="Ascent volume samples per cell along the ray (9 avoids rank-dependent banding; fewer is cheaper)",
    )
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Sample per-node power, CPU, memory and NIC counters at 1 Hz, record "
        "Slurm step accounting with energy and an environment snapshot "
        "(sites/shaheen/README.md, Telemetry)",
    )
    parser.add_argument(
        "--no-darshan",
        action="store_true",
        help="With --telemetry, leave out Darshan (I/O characterization)",
    )
    parser.add_argument(
        "--darshan-prefix",
        default=DARSHAN_PREFIX,
        help="Darshan install with lib/libdarshan.so and bin/darshan-parser",
    )
    parser.add_argument(
        "--reader-decomposition",
        choices=("slab", "brick"),
        default=READ_DECOMPOSITION,
        help="How the in transit reader splits the domain: brick (aligned with writer blocks; the default) or "
        "slab (slowest axis, the layout of runs before 16 Nov 2026). Paper 1 jobs always use slab, as run",
    )
    parser.add_argument(
        "--adios-endstep-barrier",
        action="store_true",
        help="Diagnostic: MPI_Barrier before each SST EndStep, timed as endstep_barrier (ADIOS2 #5272)",
    )
    parser.add_argument(
        "--adios-queue-full-policy",
        choices=("Block", "Discard"),
        default=QUEUE_FULL_POLICY,
        help="SST QueueFullPolicy for the simulation's output (Discard: the writer never waits for readers)",
    )
    parser.add_argument(
        "--reader-shared-planes",
        choices=("exchange", "read"),
        default=READER_SHARED_PLANES,
        help="How each reader gets the plane it shares with the next: exchange (from the neighbouring reader "
        "over MPI) or read (from the writers, the old way)",
    )
    parser.add_argument(
        "--ascent-timings",
        action="store_true",
        help="Turn on Ascent's per-filter timings (ascent_options.yaml `timings`)",
    )
    parser.add_argument(
        "--ascent-tiled-rendering",
        action="store_true",
        help="Keep Ascent 0.9.6's default tiled rendering in Paper 2 renders "
        "(off by default; for A/B runs)",
    )
    # Python 3.6 on the login nodes has no BooleanOptionalAction.
    parser.add_argument(
        "--reader-smt",
        dest="reader_smt",
        action="store_true",
        help="Run the in transit reader with 48 threads on both hardware threads of its 24 cores (the default)",
    )
    parser.add_argument(
        "--no-reader-smt",
        dest="reader_smt",
        action="store_false",
        help="Run the in transit reader with 24 threads, one per core",
    )
    parser.set_defaults(reader_smt=READER_SMT)
    parser.add_argument(
        "--catalyst-stage",
        choices=("off", "tar", "sbcast", "auto"),
        default=CATALYST_STAGE,
        help="Copy ParaView's lib/ to node-local /tmp on the in transit Catalyst reader nodes and load it "
        "from there: tar (each node reads the tarball from Lustre), sbcast (Slurm fans it out), auto "
        f"(sbcast from {CATALYST_STAGE_SBCAST_MIN_NODES} reader nodes). Needs a reader built with "
        "GS_READER_RUNPATH=ON and the tarball from build-catalyst-stage.sh (default off)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=REPEATS,
        help=f"Generate every measured run (not Paper 1 or the initialisations) this many times, as <id>_r01 ... (default {REPEATS})",
    )
    parser.add_argument(
        "--repeats-always-suffix",
        action="store_true",
        help="Give measured runs the _r01 suffix even with --repeats 1, so a later generation with more repeats extends the same IDs",
    )
    parser.add_argument(
        "--perf-env",
        default=f"/scratch/{os.environ.get('USER', 'user')}/perf_env",
        help="Python venv with pandas, activated after each run to reduce its timings",
    )
    args = parser.parse_args()
    # The jobs cd into their run directory before using these paths, so a
    # relative --results-dir would resolve from there, not from here.
    args.results_dir = os.path.abspath(args.results_dir)
    # Every path below is written into shell scripts (the job, reduce.sbat)
    # and expanded there, much of it unquoted. Rather than quote each use,
    # accept only paths that need no quoting: letters, digits and . _ - + /
    # (no spaces, $, quotes or other shell characters).
    for name in (
        "repo_path",
        "bin_path",
        "results_dir",
        "output_dir",
        "perf_env",
        "darshan_prefix",
    ):
        value = getattr(args, name)
        if not re.fullmatch(r"[A-Za-z0-9._+/-]+", value):
            parser.error(
                f"--{name.replace('_', '-')} {value!r}: only letters, digits and . _ - + / are allowed, "
                "because the path is written unquoted into the generated job scripts"
            )
    VOLUME_SAMPLES_PER_CELL = args.volume_samples_per_cell
    READ_DECOMPOSITION = args.reader_decomposition
    READER_SHARED_PLANES = args.reader_shared_planes
    ADIOS_ENDSTEP_BARRIER = args.adios_endstep_barrier
    QUEUE_FULL_POLICY = args.adios_queue_full_policy
    ASCENT_TIMINGS = args.ascent_timings
    ASCENT_TILED_RENDERING = args.ascent_tiled_rendering
    READER_SMT = args.reader_smt
    CATALYST_STAGE = args.catalyst_stage
    READER_BIN_PATH = args.bin_path
    if args.repeats < 1 or args.repeats > 99:
        parser.error("--repeats must be between 1 and 99")
    generate_scripts(args)
