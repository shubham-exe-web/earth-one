# Earth One v2.4.8

Sentinel-2 Process API payload correction.

Root cause confirmed from the live diagnostic payload:
1. The evalscript used multiple input objects without dataset IDs. In a
   single-dataset request, this is interpreted as a data-fusion style
   multi-source input and caused CDSE's `Dataset with id: 1 not found`.
2. The output block omitted an explicit TIFF response, so the request did not
   explicitly declare the desired raster response format.

Fix:
- Flatten the evalscript input to one string array:
  B02, B03, B04, B08, SCL, dataMask.
- Rely on collection-default units; Evalscript input-object `units` is optional
  and the Sentinel-2 collection defines defaults.
- Restore an explicit `responses` entry with `image/tiff`.
- Keep the six-band FLOAT32 output and existing QC/provenance.

No manual data download or QGIS step is introduced.
