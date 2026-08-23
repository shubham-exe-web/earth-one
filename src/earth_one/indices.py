from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import numpy as np
import rasterio


@dataclass
class IndexResult:
    source: str
    output: str
    index: str
    width: int
    height: int
    valid_fraction: float
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    processor_version: str = "0.5.0"


def _safe_normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = a + b
    out = np.full(a.shape, np.nan, dtype=np.float32)
    valid = np.isfinite(a) & np.isfinite(b) & (np.abs(denom) > 1e-8)
    out[valid] = ((a[valid] - b[valid]) / denom[valid]).astype(np.float32)
    return out


def _read_band(ds, description: str) -> np.ndarray:
    descriptions = list(ds.descriptions or [])
    if description in descriptions:
        idx = descriptions.index(description) + 1
        return ds.read(idx).astype(np.float32)

    # Fallback for products whose descriptions are not preserved.
    mapping = {"B02_blue": 1, "B03_green": 2, "B04_red": 3, "B08_nir": 4}
    if description in mapping and mapping[description] <= ds.count:
        return ds.read(mapping[description]).astype(np.float32)

    raise ValueError(f"Band {description} not found in {ds}")


def calculate_indices(
    input_path: str | Path,
    output_path: str | Path,
    index_names: list[str] | None = None,
) -> list[IndexResult]:
    """
    Calculate spectral indices from the Earth One v0.4 four-band S2 product.

    Supported:
      NDVI = (NIR - Red) / (NIR + Red)
      NDMI = (NIR - SWIR) / (NIR + SWIR)  [requires SWIR and therefore is not
             calculated from the current v0.4 four-band product]

    v0.5 therefore implements NDVI directly and explicitly refuses NDMI until
    a SWIR-capable preprocessing product is available.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    requested = index_names or ["NDVI"]

    unsupported = set(requested) - {"NDVI"}
    if unsupported:
        raise ValueError(
            "Unsupported indices in v0.5: "
            + ", ".join(sorted(unsupported))
            + ". NDMI requires a SWIR band and will be added with the "
              "expanded Sentinel-2 product."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results = []

    with rasterio.open(input_path) as ds:
        red = _read_band(ds, "B04_red")
        nir = _read_band(ds, "B08_nir")
        ndvi = _safe_normalized_difference(nir, red)

        profile = ds.profile.copy()
        profile.update(
            count=1,
            dtype="float32",
            nodata=np.nan,
            compress="deflate",
            predictor=3,
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(ndvi, 1)
            dst.set_band_description(1, "NDVI")
            dst.update_tags(
                EARTH_ONE_PROCESSOR_VERSION="0.5.0",
                EARTH_ONE_PRODUCT="spectral_index",
                EARTH_ONE_INDEX="NDVI",
                EARTH_ONE_FORMULA="(B08-B04)/(B08+B04)",
                EARTH_ONE_INPUT=str(input_path),
            )

        valid = np.isfinite(ndvi)
        values = ndvi[valid]

        results.append(
            IndexResult(
                source=str(input_path),
                output=str(output_path),
                index="NDVI",
                width=ds.width,
                height=ds.height,
                valid_fraction=float(valid.mean()),
                min_value=float(values.min()) if values.size else None,
                max_value=float(values.max()) if values.size else None,
                mean_value=float(values.mean()) if values.size else None,
            )
        )

    return results


def write_index_results(results: list[IndexResult], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in results], indent=2),
        encoding="utf-8",
    )
