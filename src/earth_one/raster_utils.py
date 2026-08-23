from __future__ import annotations

from typing import Any


def normalize_geotiff_profile(
    profile: dict[str, Any],
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    """
    Normalize a GeoTIFF write profile for both tiny test rasters and
    production-sized rasters.

    Small rasters are written untiled because GDAL requires tiled block
    dimensions to be positive multiples of 16.

    Larger rasters use tiled GeoTIFFs with legal block dimensions.
    """
    out = dict(profile)

    out["driver"] = "GTiff"

    if width >= 16 and height >= 16:
        block_x = min(256, max(16, (width // 16) * 16))
        block_y = min(256, max(16, (height // 16) * 16))

        out.update(
            tiled=True,
            blockxsize=block_x,
            blockysize=block_y,
        )
    else:
        out["tiled"] = False
        out.pop("blockxsize", None)
        out.pop("blockysize", None)

    return out
