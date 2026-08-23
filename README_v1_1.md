# Earth One v1.1 — Autonomous Research Production Engine

This release removes the manual Sentinel-1/QGIS extraction step used during the
first real-world trial.

## What changed

The production path is now:

1. Read the frozen research AOI from configuration.
2. Query Copernicus Data Space Sentinel-1 GRD catalog automatically.
3. Normalize scene metadata and derive relative orbit when needed.
4. Match before/after observations using relative orbit, orbit direction, IW
   mode, polarization, platform and slice evidence.
5. Select a real product ID before processing.
6. Request only the AOI through the Copernicus Data Space Process API.
7. Request terrain-corrected Gamma0 by default using Copernicus DEM 30 m.
8. Validate the resulting raster immediately.
9. Reject and delete empty, all-zero, non-finite or constant outputs.
10. Write a provenance manifest containing the exact scenes and QC results.

## Run

Set `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` in the environment.

Example for the frozen 10 x 10 km HAMFO-01 AOI:

```bash
earth-one s1-auto-pair \
  --bbox 82.5916,22.7751,82.6884,22.8649 \
  --before-start 2025-01-01 \
  --before-end 2025-01-31 \
  --after-start 2026-01-01 \
  --after-end 2026-01-31 \
  --output-dir data/processed/HAMFO01_S1_JAN25_JAN26
```

If a relative orbit is already known from an independently verified search,
pass it with `--relative-orbit 19`. Otherwise the matcher evaluates all
available candidates and selects the strongest valid pair.

## Important scientific guardrail

The engine does not accept a processing HTTP success response as evidence that
a raster is scientifically usable. The output must pass pixel-level QC before it
can enter the research pipeline.

The previous manual QGIS clipping trial produced correctly shaped but all-zero
rasters. v1.1 is specifically designed to prevent that failure mode.
