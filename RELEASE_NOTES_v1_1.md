# v1.1 release notes

- Uses the current Copernicus Data Space Catalog API for Sentinel-1 GRD discovery.
- Uses the current Sentinel-1 GRD Process API for AOI-sized on-demand processing.
- Defaults to Gamma0 terrain backscatter with Copernicus DEM 30 m and orthorectification.
- Adds exact-scene filtering in the evalscript.
- Adds mandatory raster-value QC and fail-closed behavior.
- Adds automated temporal-pair matching and provenance manifest generation.
