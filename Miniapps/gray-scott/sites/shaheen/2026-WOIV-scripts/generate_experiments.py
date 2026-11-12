import math
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

# =============================================================================
# DEFINITIONS (Strong/Weak Scaling & New Sweeps)
# =============================================================================
STRONG_SCALING_NODES = [256, 1024, 4096]
STRONG_GRID = 4096

WEAK_SCALING_CONFIGS = [(8, 1024), (64, 2048), (512, 4096), (4096, 8192)]

TRANSIT_CONFIGS = [
    ("small", 64, 2048, 4),  # Weak Scaling Start (16:1)
    ("compressed", 512, 4096, 32),  # Strong Scaling Start (16:1)
    ("hero", 4096, 8192, 256),  # Weak/Strong Scaling End (16:1)
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
SCALE_CONFIGS = [(256, 16), (512, 32), (1024, 64)]  # (simulation, staging) nodes
SCALE_GRID = 4096
SCALE_LAUNCHES = ["mpmd", "steps"]
SCALE_RUN_STEPS = 101
SCALE_TIME_LIMIT = "0:45:00"

CATALYST_LIB_PATH = "/scratch/kressjm/Visualization_Vignettes/software/paraview-build/install/lib/catalyst"

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
            <parameter key="QueueLimit" value="1"/>
            <parameter key="QueueFullPolicy" value="Block"/>
            <parameter key="DataTransport" value="{data_transport}"/>
            <parameter key="ControlModule" value="epoll"/>
            <parameter key="OpenTimeoutSecs" value="600.0"/>
            <parameter key="AsyncWrite" value="false"/>
            <parameter key="NumAggregators" value="{sim_aggregators}"/>
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
timings: "false"
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
          image_prefix: "data/ascent_render_iso"
          camera:
            position: [{cam_x}, {cam_y}, {cam_z}]
            look_at: [{center}, {center}, {center}]
            up: [{cam_up_x}, {cam_up_y}, {cam_up_z}]
            zoom: 1.7
"""

# --- CATALYST TEMPLATES ---
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

CATALYST_VOLUME_TEMPLATE = """
# Volume of v over the full grid, comparable with ASCENT_VOLUME_TEMPLATE: the
# same data (no resampling), image size and colour range (pinned to 0..1).
# Rendered with OSPRay, the CPU ray tracer, as the slice and isosurface
# templates are: like Ascent's VTK-m ray tracer, so the comparison is fair.
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
    EnableRayTracing=1,
    BackEnd="OSPRay raycaster",
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

CATALYST_ISOSURFACE_TEMPLATE = """
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

# Contour needs ghost cells on every side of a block, or each block's high
# face gets one-sided normals (docs/in-situ-backends.md, Catalyst).
ghostCells = GhostCells(registrationName='GhostCells', Input=producer)
contour = Contour(registrationName='Contour', Input=ghostCells)
contour.ContourBy = ['POINTS', 'v']
contour.Isosurfaces = [0.1]

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
#SBATCH --nodes={total_nodes}
#SBATCH --ntasks={total_ranks}
{cpus_per_task_line}
{network_line}
#SBATCH --time={time_limit}
#SBATCH --hint=nomultithread
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
#export GALLIUM_DRIVER=softpipe
#export LP_NUM_THREADS=1
export GALLIUM_DRIVER=softpipe
export LP_NUM_THREADS=1


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
export OSPRAY_THREADS={omp_threads}
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
(set -o pipefail; env | grep -E '^(MALLOC_|FI_|CM_|MPICH_|Sst_|ADIOS2_)' | sort) > "{results_dir}/{id}_env.txt" || exit 1
echo "PHASE run_start $(date +%s.%N)"

{command}
RUN_RC=$?
echo "PHASE run_end $(date +%s.%N)"
echo "Run exit status: $RUN_RC"

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
    if sbatch {output_dir}/reduce.sbat; then
        break
    fi
    echo "sbatch of the reduction job failed (attempt $attempt of 3)"
    if [ "$attempt" -eq 3 ]; then
        echo "REDUCE_SUBMIT_FAILED: run it later with: sbatch {output_dir}/reduce.sbat"
    else
        sleep 10
    fi
done
echo "PHASE post_end $(date +%s.%N)"
# The job's status is the run's.
exit $RUN_RC
"""

# One-node job that reduces a run's per-rank timings (#72). Written next to
# each run as reduce.sbat and submitted by the run's job when it ends.
REDUCE_TEMPLATE = """#!/bin/bash
#SBATCH --job-name=reduce_{id}
#SBATCH --account={account}
#SBATCH --partition={partition}
#SBATCH --nodes=1
#SBATCH --time=1:00:00
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

# Archive a directory atomically: write the archive under a temporary name,
# rename it, then remove the directory.
archive() {{
    tar -czf $OUTPUT_DIR/$1.tar.gz.tmp -C $OUTPUT_DIR $1/ \
        && mv $OUTPUT_DIR/$1.tar.gz.tmp $OUTPUT_DIR/$1.tar.gz \
        && rm -rf $OUTPUT_DIR/$1/
}}

# A rerun after a successful reduction finds only the archives: restore them.
# Extract into a temporary directory and move it into place only if tar
# succeeds, so a failed extraction never looks like a complete one. The
# archive is kept until the new one replaces it.
for d in perf reader_timers; do
    if [ ! -d $OUTPUT_DIR/$d ] && [ -f $OUTPUT_DIR/$d.tar.gz ]; then
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

# 2. Simulation timings: the newest run directory under perf/ (README.md,
#    Performance). Keep its metadata.json and summary.json beside the CSV.
SIM_PERF=$(ls -dt $OUTPUT_DIR/perf/*/ 2>/dev/null | head -1)
if [ -n "$SIM_PERF" ]; then
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
if [ -d "$OUTPUT_DIR/reader_timers" ]; then
    echo "Reducing reader_timers..."
    if python "$REDUCE" "$OUTPUT_DIR/reader_timers" "{results_dir}/{id}_reader.csv"; then
        echo "Compressing reader_timers..."
        archive reader_timers
    else
        echo "Reduction of reader_timers failed; reader_timers/ kept."
    fi
fi

echo "PHASE reduce_end $(date +%s.%N)"
"""

CMD_INLINE = """srun --exclusive --propagate=NOFILE --hint=nomultithread \\
    --nodes={sim_nodes} --ntasks={sim_ranks} --ntasks-per-node={mpi_per_node} --cpus-per-task={omp_threads} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json
"""

CMD_INTRANSIT = """srun --exclusive --propagate=NOFILE --hint=nomultithread --kill-on-bad-exit=1 \\
    --nodes={sim_nodes} --ntasks={sim_ranks} --ntasks-per-node={mpi_per_node} --cpus-per-task={omp_threads} --mem-bind=v,local --cpu-bind=threads \\
    $EXE_SIM \\
    --logging-level={logging_level} \\
    --settings-file=$OUTPUT_DIR/settings.json \\
    : \\
    --exclusive --nodes={stage_nodes} --ntasks={stage_ranks} --ntasks-per-node=8 --cpus-per-task=24 --mem-bind=v,local --cpu-bind=threads \\
    env OMP_NUM_THREADS=24 OMP_PLACES=cores OMP_PROC_BIND=close \\
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
srun --network=job_vni --exclusive --propagate=NOFILE --hint=nomultithread \\
    --nodes={stage_nodes} --ntasks={stage_ranks} --ntasks-per-node=8 --cpus-per-task=24 --mem-bind=v,local --cpu-bind=threads \\
    env OMP_NUM_THREADS=24 OMP_PLACES=cores OMP_PROC_BIND=close \\
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
        "kombynelite_script_path": "",
        "adios_config": f"{output_dir}/adios2.xml",
        "adios_span": False,
        "adios_memory_selection": True,
        "ascent_options": "",
    }

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
            f.write(ASCENT_OPTIONS_TEMPLATE.format(actions_file=actions_filename))
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
        command = cmd_template.format(
            sim_nodes=exp["sim_nodes"],
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
        )

        script_content = SBATCH_TEMPLATE.format(
            id=exp["id"],
            account=args.account,
            partition=SYSTEM_CONFIG["partition"],
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
            time_limit=exp.get("time_limit", SYSTEM_CONFIG["time_limit"]),
            output_dir=run_output_dir,
            results_dir=args.results_dir,
            perf_env=args.perf_env,
            repo_path=args.repo_path,
            bin_path=args.bin_path,
            command=command,
            catalyst_lib_path=CATALYST_LIB_PATH,
            paraview_lib_path=os.path.dirname(CATALYST_LIB_PATH.rstrip("/")),
        )

        reduce_content = REDUCE_TEMPLATE.format(
            id=exp["id"],
            account=args.account,
            partition=SYSTEM_CONFIG["partition"],
            output_dir=run_output_dir,
            results_dir=args.results_dir,
            perf_env=args.perf_env,
            repo_path=args.repo_path,
        )
        with open(f"{run_output_dir}/reduce.sbat", "w") as f:
            f.write(reduce_content)
        with open(f"{args.output_dir}/{exp['id']}.sbat", "w") as f:
            f.write(script_content)

    print(f"Generated {len(EXPERIMENTS)} scripts in {args.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--bin-path", required=True)
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
        "--perf-env",
        default=f"/scratch/{os.environ.get('USER', 'user')}/perf_env",
        help="Python venv with pandas, activated after each run to reduce its timings",
    )
    args = parser.parse_args()
    # The jobs cd into their run directory before using these paths, so a
    # relative --results-dir would resolve from there, not from here.
    args.results_dir = os.path.abspath(args.results_dir)
    VOLUME_SAMPLES_PER_CELL = args.volume_samples_per_cell
    generate_scripts(args)
