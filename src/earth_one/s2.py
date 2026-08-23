from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import shutil
import tempfile
import zipfile

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject


S2_BANDS_10M = {
    "B02": "blue",
    "B03": "green",
    "B04": "red",
    "B08": "nir",
}

# Sentinel-2 Scene Classification Layer (SCL) classes that should not enter
# vegetation/carbon inference by default.
DEFAULT_MASK_CLASSES = {
    0,   # no data
    1,   # saturated / defective
    3,   # cloud shadow
    8,   # cloud medium probability
    9,   # cloud high probability
    10,  # thin cirrus
    11,  # snow / ice
}


@dataclass
class S2ProcessingResult:
    source: str
    output: str
    sensor: str
    bands: list[str]
    width: int
    height: int
    crs: str
    resolution: tuple[float, float]
    valid_fraction: float
    cloud_masked_fraction: float
    processor_version: str


def _extract_if_zip(input_path: Path):
    if input_path.suffix.lower() != ".zip":
        return input_path, None

    temp_dir = Path(tempfile.mkdtemp(prefix="earth_one_s2_"))
    with zipfile.ZipFile(input_path, "r") as z:
        z.extractall(temp_dir)

    safe_dirs = list(temp_dir.glob("*.SAFE"))
    if not safe_dirs:
        safe_dirs = [p for p in temp_dir.iterdir() if p.is_dir()]
    if not safe_dirs:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError("No SAFE/product directory found inside Sentinel-2 archive")

    return safe_dirs[0], temp_dir


def _find_band(root: Path, band: str) -> Path:
    # L2A SAFE JP2 naming convention contains _B02_10m, etc.
    matches = sorted(root.rglob(f"*_{band}_10m.jp2"))
    if not matches:
        matches = sorted(root.rglob(f"*_{band}_10m.JP2"))
    if not matches:
        raise FileNotFoundError(f"Sentinel-2 {band} 10 m JP2 not found")
    return matches[0]


def _find_scl(root: Path) -> Path:
    matches = sorted(root.rglob("*_SCL_20m.jp2"))
    if not matches:
        matches = sorted(root.rglob("*_SCL_20m.JP2"))
    if not matches:
        raise FileNotFoundError("Sentinel-2 SCL 20 m JP2 not found")
    return matches[0]


def _reproject_array(src, src_transform, src_crs, dst_transform, dst_crs, width, height, resampling, dst_nodata):
    dst = np.full((height, width), dst_nodata, dtype=np.float32)
    reproject(
        source=src,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        src_nodata=0 if resampling == Resampling.nearest else None,
        dst_nodata=dst_nodata,
        resampling=resampling,
        num_threads=2,
    )
    return dst


def preprocess_s2_l2a(
    input_path: str | Path,
    output_path: str | Path,
    target_crs: str | None = None,
    target_resolution: float = 10.0,
    mask_classes: set[int] | None = None,
    scale_reflectance: bool = True,
) -> S2ProcessingResult:
    """
    Create a 4-band, 10 m analysis-ready Sentinel-2 L2A GeoTIFF.

    Bands:
      B02 blue, B03 green, B04 red, B08 NIR

    Processing:
      - locate L2A 10 m JP2 assets and SCL
      - convert digital numbers to reflectance when requested
      - reproject/resample all bands to a common grid
      - resample SCL with nearest neighbour
      - mask invalid/cloud/shadow/snow classes
      - write float32 GeoTIFF with explicit provenance tags
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    mask_classes = DEFAULT_MASK_CLASSES if mask_classes is None else mask_classes

    root, cleanup_dir = _extract_if_zip(input_path)

    try:
        band_paths = {band: _find_band(root, band) for band in S2_BANDS_10M}
        scl_path = _find_scl(root)

        with rasterio.open(band_paths["B04"]) as reference:
            src_crs = reference.crs
            if src_crs is None:
                raise ValueError("Reference Sentinel-2 band has no CRS")
            src_bounds = reference.bounds
            src_width = reference.width
            src_height = reference.height

        dst_crs = target_crs or src_crs
        transform, width, height = calculate_default_transform(
            src_crs,
            dst_crs,
            src_width,
            src_height,
            *src_bounds,
            resolution=target_resolution,
        )

        processed = {}
        for band, path in band_paths.items():
            with rasterio.open(path) as ds:
                arr = ds.read(1).astype(np.float32)

                # Sentinel-2 L2A reflectance is distributed as scaled integer
                # values. Keep the conversion explicit and recorded.
                if scale_reflectance:
                    arr /= 10000.0

                out = _reproject_array(
                    arr,
                    ds.transform,
                    ds.crs,
                    transform,
                    dst_crs,
                    width,
                    height,
                    Resampling.bilinear,
                    np.nan,
                )
                processed[band] = out

        with rasterio.open(scl_path) as ds:
            scl = ds.read(1).astype(np.float32)
            scl_out = _reproject_array(
                scl,
                ds.transform,
                ds.crs,
                transform,
                dst_crs,
                width,
                height,
                Resampling.nearest,
                -1,
            )

        invalid = ~np.isfinite(processed["B04"])
        cloud_mask = np.isin(scl_out.astype(np.int16), list(mask_classes))
        mask = invalid | cloud_mask

        stack = np.stack([processed[b] for b in S2_BANDS_10M], axis=0)
        stack[:, mask] = np.nan

        output_path.parent.mkdir(parents=True, exist_ok=True)
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": len(S2_BANDS_10M),
            "dtype": "float32",
            "crs": dst_crs,
            "transform": transform,
            "nodata": np.nan,
            "compress": "deflate",
            "predictor": 3,
            "tiled": True,
        }

        with rasterio.open(output_path, "w", **profile) as dst:
            for idx, band in enumerate(S2_BANDS_10M, 1):
                dst.write(stack[idx - 1], idx)
                dst.set_band_description(idx, f"{band}_{S2_BANDS_10M[band]}")
            dst.update_tags(
                EARTH_ONE_SENSOR="sentinel-2",
                EARTH_ONE_PROCESSOR_VERSION="0.4.0",
                EARTH_ONE_PRODUCT="L2A_analysis_ready",
                EARTH_ONE_INPUT=str(input_path),
                EARTH_ONE_REFLECTANCE_SCALE="0.0001" if scale_reflectance else "none",
                EARTH_ONE_MASK_CLASSES=",".join(map(str, sorted(mask_classes))),
                EARTH_ONE_TARGET_RESOLUTION_M=str(target_resolution),
            )

        total = mask.size
        cloud_masked = np.count_nonzero(cloud_mask)
        valid = np.count_nonzero(~mask)

        return S2ProcessingResult(
            source=str(input_path),
            output=str(output_path),
            sensor="sentinel-2",
            bands=list(S2_BANDS_10M),
            width=width,
            height=height,
            crs=str(dst_crs),
            resolution=(abs(transform.a), abs(transform.e)),
            valid_fraction=valid / total if total else 0.0,
            cloud_masked_fraction=cloud_masked / total if total else 0.0,
            processor_version="0.4.0",
        )
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def write_result(result: S2ProcessingResult, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "source": result.source,
            "output": result.output,
            "sensor": result.sensor,
            "bands": result.bands,
            "width": result.width,
            "height": result.height,
            "crs": result.crs,
            "resolution": result.resolution,
            "valid_fraction": result.valid_fraction,
            "cloud_masked_fraction": result.cloud_masked_fraction,
            "processor_version": result.processor_version,
        }, indent=2),
        encoding="utf-8",
    )
