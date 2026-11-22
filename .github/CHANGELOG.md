# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-11-22

### Highlights since 1.0.0

Merged since 1.0.0 (March to November 2026, up to #144). The sections
after this one keep the detailed notes from the local validation work.

**Gray-Scott miniapp**
- A core library with CTest numerical regression on 1, 2 and 4 ranks, CMake
  presets, a sanitizer preset with clean ASan/UBSan runs, and reproducible
  noise from seed, step and global position (#47, #50, #53, #54).
- One shared Blueprint mesh and ghost rules for every in situ backend
  (Ascent, Catalyst, Kombyne-lite, PVTI, ADIOS2), with zero-copy checks,
  per-step allocation counts and backend render checks, after a halo and
  restart audit (#51, #62 to #67).
- The in transit analysis reader: an ADIOS2 writer backend, deferred reads,
  brick decomposition with shared planes exchanged between readers (now the
  default), persistent field buffers, and engine parameters read from the
  XML; a Catalyst reader that renders on all 24 cores and stops the run
  when a Catalyst script fails (#81, #91, #103, #108, #110, #111, #117,
  #119).
- A structured performance log for every run, one step file per node,
  opt-in telemetry (power, NIC, Darshan), the SST write-path split (EndStep
  barrier and delivery latency), and provenance, platform and network
  placement recorded for every run; the performance log is written before
  the output closes, and teardown is bounded (#56, #77, #79, #109, #113,
  #114, #115, #122, #124).
- Docs written for people: a rewritten README, a getting-started guide, a
  tested Docker quick start, and `docs/in-situ-backends.md` (#49, #68, #87,
  #105, #135).
- The render and ghost-volume tests launch through CMake's MPI settings, so
  ctest passes under srun on Shaheen (#55, #141).

**Regression suite and dashboard**
- Baselines and recorded performance for ParaView 6.2.1 and VisIt 3.5.0 on
  the workstation, Ibex (CPU and six GPU types) and Shaheen III, with
  `VV_VISIT_MODULE` and `--baseline-ref` for testing other builds, and
  records backfilled for older ParaView and VisIt builds (#93, #95 to #102,
  #123, #128, #131).
- Trustworthy CPU and memory figures (PSS locally, Slurm accounting under
  srun), `--repeat N` judged by the median, and the host environment in each
  record (#104, #125).
- The results dashboard, published at
  <https://jameskress.github.io/Visualization_Vignettes/dashboard/>, with drift
  warnings, a tool-version axis, like-for-like vignette revisions and retired
  configurations, with no host names on the public site (#107, #112, #116,
  #132).
- A Pages landing page and a gallery of the baseline images, and an "add
  your site" guide with the checks its pull request runs (#137, #142, #143).

**Docker image and CI**
- The image moves to ParaView 6.2.1, ADIOS2 `release_213` at 8d7270164 and
  Ascent 0.9.6 (#6, #127).
- CI runs only what a change can affect, runs pre-commit on changed files,
  and builds the arm64 image natively on GitHub's hosted arm64 runner, off
  the shared self-hosted runner (#58, #61, #70, #74, #89, #121, #129).
- Releases: this changelog, a release workflow on `vX.Y.Z` tags and Zenodo
  archiving through `CITATION.cff` (#133).

**Paper 2 tooling (Shaheen III)**
- The experiment generator, orchestrator and large-run tools, with SST
  transport and launch options, scaling matrices, phase timestamps and
  per-job limits, and a local harness for the generator's jobs (#80, #82,
  #83, #84, #90, #94, #118).
- The Shaheen stack moves to ParaView 6.2.1 (GCC 13), ADIOS2 8d7270164 and
  Ascent 0.9.6, with Catalyst fixes (OSPRay, AcceleratedAlgorithms) and
  Ascent's tiled rendering off in Paper 2 renders (#85, #126, #130, #134).
- Sweeps: three repeats per configuration with outlier flags, `--qos=ex`
  runs up to 3,536 nodes, Catalyst libraries staged on node-local disk, and
  per-rank data output recorded and deleted after each run (#136, #138,
  #144).


### Local validation notes

Local validation of both suites against ParaView 6.1.0, VisIt 3.4.2 and
VisIt 3.4.1, before taking them to Shaheen. `Testing/LOCAL_VALIDATION.md`
carries the measurement behind each item below.

### Added
- `Testing/prepare_machine.py`: one idempotent command for every generated
  fixture, with `--check` as a job-script preflight. `test_suite.py` runs it
  before starting and refuses on a stale fixture, because every way those
  fail looks like a regression in a vignette rather than a setup problem.
- `data/make_time_series.py`: an XML time series carrying real `TIME` and
  `CYCLE`. The shipped `varying*.vtk` series carries neither, so both tools
  had been inventing a time from the file index and agreeing by coincidence.
- `Testing/RUNBOOK.md`: one document for running the suite on a
  workstation, Ibex, Shaheen `workq` and Shaheen `ppn`, for ParaView and
  VisIt, online or air-gapped, with the setup order, the per-machine
  resource limits and a troubleshooting table.
- A vignette can report itself **skipped** when its input is absent by design.
  `ex06` is the only one: its 5.7 GB dataset is fetched by `data/fetchData.sh`
  and deliberately not committed, so a fresh clone and CI both ran it and
  failed inside the reader. It now says why and stops, no gate runs against
  it, nothing is appended to its history, the suite still exits 0, and the
  skip is listed under `skipped_tests` in the summary report.
- `Testing/make_offline_bundle.sh`: collects the five runtime dependencies as
  wheels for a target platform, because a virtualenv is not relocatable and
  copying one to another machine produces a Python that cannot import itself.
- `AGENTS.md` and `CLAUDE.md`: working notes for an assistant or a new
  contributor, in the cross-tool convention.
- `Testing/LOCAL_VALIDATION.md`: the runbook, the defect log, and the
  measurements behind the baseline decisions.
- A `.flake8` config scoping `F821` to `VisIt_Vignettes/`, where VisIt's CLI
  injects its API into the global namespace and there is no import for flake8
  to resolve against.
- `ex05` puts the cycle and the simulation time on every frame, in both suites.
- `ex12` reports `timestep`, `cycle` and `time` as three separate columns, and
  the two suites' CSVs agree column for column.

### Changed
- The Docker image moves to the Gray-Scott target stack: ParaView 6.2.1
  (`PARAVIEW_VERSION=v6.2.1`), ADIOS2 at release_213 commit 8d7270164
  (was v2.12.1), and Ascent 0.9.6 (was 0.9.5), which brings Conduit 0.9.9
  and Viskores in place of VTK-m. Ascent is built as Release explicitly,
  because 0.9.6's build script defaults to Debug.
- ParaView 6.2.0 is the reference version: the workstation baselines, the CI
  download and the Docker image (`PARAVIEW_VERSION=v6.2.0`). ADIOS2 in the
  image is pinned to v2.12.1 instead of following its default branch. ex06's
  image baseline is re-blessed for 6.2's Surface LIC rendering.
- Performance metrics: peak memory and CPU are sampled across the vignette's
  whole process tree rather than taken from `RUSAGE_CHILDREN`, which is a
  high-water mark that never falls. `metrics_schema` is bumped to 4, and the
  performance gate and the plots both refuse to compare across that boundary.
- `Testing/plot_metrics.py` rewritten: one panel per configuration against its
  own run number rather than every configuration on a union-of-timestamps
  axis, a latest-run bar chart beside it, and the schema boundary drawn rather
  than hidden.
- `output/` is cleared before every local run, so a stale file cannot be
  counted or blessed.
- Generated fixtures (`data/topologies/`, `data/varying_series_xml/`,
  `ex11_state.pvsm`, `ex11_visit.session`, `ex11_series.visit`) are no longer
  committed. They are version-locked or path-locked and none announces a
  mismatch; `prepare_machine.py` rebuilds them per machine.
- `ex09` draws the input surface underneath a lower-dimensional contour, so
  the polydata frame shows the mesh rather than a hairline on empty space.
- All VisIt baselines re-blessed. `ex06`'s is blessed at the eight ranks its
  `.sbat` scripts request and disables its own image gate at any other rank
  count, because translucent geometry composites in a partition-dependent
  order.
- `data/README.md` rewritten: every dataset sorted into shipped, fetched or
  generated, with its size, which vignettes read it, and whether it can be
  copied to another machine or has to be rebuilt there.
- Every `.sbat` script passes shellcheck: the `cd` into the vignette directory
  is guarded, `source ../MODULES.sh` is annotated as resolved at run time, and
  the Shaheen scripts no longer compute a ranks-per-node value that only the
  Ibex `mpirun --map-by ppr` line ever used.
- CI prepares its fixtures before running either suite, and the ParaView
  version label follows what the job actually downloads.
- `Dockerfile` installs `pillow` and `psutil`, without which the image gate
  and the memory metric silently do not run.
- Updated links and instructions in the Miniapps README.
- Added project badges and citation information.
- Updated ParaView README for clarity on HPC usage.
- Updated ParaView baseline images to use ParaView 6.0 default backgrounds
  and colour tables.

### Fixed
- ParaView 6.2 compatibility, without changing a baseline: ex03 finds the
  contour normals under 6.2's `Gradients` name, ex05 accepts `CYCLE` as an int,
  and ex09 drops contour cells from blanked AMR cells, which 6.2's Contour no
  longer skips.
- VisIt's launcher exits 250 whether the script succeeded or not, so the
  verdict comes from the vignette's own results JSON, and only when that file
  was written after the run started.
- `-noconfig` hides 129 of VisIt's own colour tables as well as the user's;
  vignettes load what they need from the install rather than failing the plot
  asynchronously and returning `None` from every later query.
- `pvbatch` 6.1 segfaults during finalization when a render window exists and
  no display does; every rendering vignette exits through `vc.exit_vignette()`.
- ParaView's `Show()` auto-rescales a lookup table, so presets are applied and
  rescaled after it rather than before.
- `ex00`'s numeric gate had never run: the results file was resolved from the
  script name rather than the directory.
- `ex09` contoured the AMR hierarchy above its scalar range and the polydata
  surface at its own defining value, producing no geometry in either case and
  saying nothing.
- `ex12` ran the whole animation on every iteration and counted files left
  behind by a previous run.
- `ex07` queried `MinMax` on a plot carrying the Isosurface operator, so its
  "scalar range is non-degenerate" assertion could never pass.
- Animation vignettes could never pass: blessing caps at five images and the
  rest were reported as failing rather than as not baselined.

## [1.0.0] - 2026-03-05

### Added
- Expanded regression testing and vignette coverage (`ex00`-`ex12` in both
  suites), merged from `performanceRunUpdates`.

## [0.1.0] - 2025-09-16

### Added
- Initial release of the KAUST Visualization Vignettes cookbook.
- Added a `ParaView_Vignettes` section for ParaView examples.
- Added a `VisIt_Vignettes` section for VisIt examples
- Added a `Miniapps` section for in situ miniapps.
- Added `gray-scott` miniapp to demonstrate both in line and in transit in situ with Ascent, ADIOS2, Catalyst2, Kombyne, and VTK.
- Created `CONTRIBUTING.md` to guide new contributors.
- Docker support (`Dockerfile` and GitLab CI runner updates) for creating a consistent build environment.
- Initial integration for ADIOS2, Ascent, and ParaView Catalyst for in situ processing.
- Kombyne performance plotter and integration with the miniapp.
- Visualization scripts for gray-scott examples.
- Test suite functionality to run specific unit tests.
- `LICENSE` file.

### Changed
- Refactored analysis code and updated examples to be consistent across different in situ technologies.
- Updated numerous `README` files with improved documentation for testing, miniapp execution, and Docker usage.
- Modified `.gitlab-ci.yml` to use stable CI images and add CI jobs.
- Updated movie generation script (`createMovieFromImages.sh`).

### Fixed
- Corrected an invalid path in the SLURM batch script for the `VisIt_Vignettes/Interactive_Ibex` example.
- Movie generation script now works correctly with images of odd dimensions.
- Test suite now returns a proper error code on test failure.
- Improved error messages for clearer test failure analysis.
