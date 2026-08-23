# Earth One v2.4.6

Six-band Sentinel-2 production smoke test.

- Extends the known-good minimal S2 Process API payload from 3 bands to 6.
- Keeps the same simple request shape: one `sentinel-2-l2a` dataset, one bbox,
  one time range, one 512x512 output, one TIFF response.
- Requests B02/B03/B04/B08 as REFLECTANCE, SCL as DN, and dataMask as DN.
- Returns a single FLOAT32 six-band GeoTIFF.
- Records an explicit six-band contract in provenance.
- QC now requires exactly six bands, validates SCL 0..11, validates dataMask 0/1,
  and reports the band contract.
