# Earth One v2.4.9 - Clean S2 production handoff

The successful live Sentinel-2 smoke test can now be treated as the production
baseline after removing the temporary payload-print diagnostic.

Added:
- clean S2 worker without diagnostic payload dumping
- `earth-one s2-qc --path <tif>` for explicit post-run validation
- preservation of the six-band contract and QC rules

Production acceptance sequence:
1. Live S2 acquisition returns without traceback.
2. `s2-qc` returns `valid: true`, count 6.
3. Provenance sidecar exists.
4. Result is eligible for ingestion into temporal analysis.

No manual scene selection or QGIS step is introduced.
