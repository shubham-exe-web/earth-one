# Earth One v2.4.5

Minimal Sentinel-2 Process API diagnostic.

This release deliberately mirrors the official CDSE Sentinel-2 L2A true-color
request shape:
- `input.data.type`: `sentinel-2-l2a`
- CRS84 bbox
- Jan 2026 time range
- B02/B03/B04 only
- `output.width` / `output.height`
- no `output.responses` object
- `Accept: image/tiff`

The goal is to isolate Process API contract issues before reintroducing
mosaicking, SCL/dataMask, multiple outputs, and scene-specific controls.
