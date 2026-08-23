# Earth One v1.3 - Autonomous S1 Reliability

## Purpose
Harden the live Sentinel-1 production path after the real-world zero-raster failure encountered during manual GIS clipping.

## Changes
- Added local `s1-preflight` command that checks required CDSE credentials without printing secrets.
- Normalized Sentinel-1 polarization metadata (`DV`, `VV+VH`, etc.).
- Made dual-polarization (`DV`) a hard requirement for the current production S1 pair matcher.
- Improved network failure reporting.
- Kept provenance-gated Process API validation and multiband raster QC.
- Preserved the existing `s1-auto-pair --dry-run` workflow.

## Important
This version does not claim a live CDSE run was completed in this environment because outbound access to `sh.dataspace.copernicus.eu` is unavailable here. The live run must be executed on the user's machine with local CDSE credentials.
