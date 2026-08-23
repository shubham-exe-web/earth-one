# Earth One v2.4.7

Clean six-band Sentinel-2 worker.

- Removes the remaining three-band diagnostic `process_exact_scene` implementation.
- Keeps exactly one `process_exact_scene` method.
- Requests B02/B03/B04/B08 + SCL + dataMask.
- Produces one six-band Float32 GeoTIFF.
- Adds strict six-band/SCL/dataMask QC.
- Keeps the known-good CDSE minimal request shape.
