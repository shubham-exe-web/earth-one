# Earth One v1.5 - Temporal Experiment Engine

## Goal
Move from individual validated products to a reproducible temporal experiment that compares matched dates and explicitly records missing modalities.

## Added
- `temporal_experiment.py`
- `temporal-experiment` CLI
- frozen experiment manifest
- input QC before comparison
- same-grid enforcement
- optical change statistics
- SAR VV/VH comparison when verified inputs exist
- multimodal direction-consistency check
- explicit partial-state reporting instead of fabricating missing SAR inputs

## Immediate use
1. Run the live Sentinel-1 autonomous dry-run/production on the user's machine.
2. Populate verified VV/VH outputs.
3. Run this temporal experiment with the real S1 + existing verified S2 products.
