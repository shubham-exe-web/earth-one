# Earth One v1.4 - Multimodal Fusion Foundation

## Goal
Move from independently processed Sentinel-1 and Sentinel-2 products toward an auditable, common-grid multimodal feature cube.

## Added
- `multimodal_fusion.py`
- `multimodal-stack` CLI command
- explicit target-grid selection
- explicit resampling for each feature
- input feature QC
- output feature QC
- band descriptions
- machine-readable fusion provenance
- regression tests for valid fusion, constant input rejection, and zero-raster rejection

## Scientific guardrail
Fusion does not imply interpretation. The resulting stack is a common analysis substrate for subsequent change detection, event scoring, validation, and uncertainty analysis.
