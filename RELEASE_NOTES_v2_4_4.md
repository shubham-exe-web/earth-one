# Earth One v2.4.4

Live Sentinel-2 Process API fix.

Changes:
- Replaced the fragile multi-response `application/tar` request with a
  single documented `image/tiff` response for the live acquisition smoke test.
- Uses the documented `sentinel-2-l2a` data type.
- Uses a standard six-band evalscript: B02, B03, B04, B08, SCL, dataMask.
- Narrows the request to a 6-minute window around the STAC-selected scene.
- Records local process request provenance in `process_provenance.json`.
- CDSE non-2xx responses now include the server response body in the raised
  error, so future failures are actionable rather than opaque.
