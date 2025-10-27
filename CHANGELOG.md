# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
 - Updated links and instructions in the Miniapps README.
 - Added project badges and citation information. 
 - Updated ParaView README for clarity on HPC usage
 - Moved repo to GiHub

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
