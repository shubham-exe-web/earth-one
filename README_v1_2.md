# Earth One v1.2 — Provenance-Gated Sentinel-1 Production

v1.2 hardens the v1.1 autonomous Sentinel-1 workflow around a key real-world failure discovered during HAMFO-01 testing: a raster can have plausible dimensions, extent, CRS, and a successful GIS/API status while containing no usable signal.

## What changed

- Process API responses are requested as multipart/tar with `default.tif` plus `userdata.json`.
- The returned provenance is checked against the exact catalog-selected Sentinel-1 product ID.
- Sentinel-1 processing requests explicitly pass `acquisitionMode`, `orbitDirection`, and polarization.
- Gamma0 terrain processing uses orthorectification and Copernicus DEM 30 m, consistent with current CDSE Sentinel-1 processing documentation.
- QC validates every returned data band, not only band 1.
- All-zero, constant, empty, non-finite, unreadable, and provenance-mismatched outputs are rejected and removed.
- Backward-compatible `validate_raster()` remains available for existing modules.
- Dedicated S1 regression tests: 5/5 pass in the release environment.

## Production target

Frozen HAMFO-01 AOI:

`82.5916,22.7751,82.6884,22.8649`

Example live run:

```bash
earth-one s1-auto-pair \
  --bbox 82.5916,22.7751,82.6884,22.8649 \
  --before-start 2025-01-01 \
  --before-end 2025-01-31 \
  --after-start 2026-01-01 \
  --after-end 2026-01-31 \
  --relative-orbit 19 \
  --output-dir data/processed/HAMFO01_S1_JAN25_JAN26
```

The command requires locally configured `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET`. Do not place secrets in source files or commit them.

## Scientific rule

A successful HTTP/API response is not a scientific pass. The output is accepted only after both provenance verification and raster-value QC succeed.
