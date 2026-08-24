from __future__ import annotations

"""Drought Module 3 Feature Extraction & Provenance Layer."""

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class DroughtFeatureRecord:
    """Standardized metadata container for an extracted drought feature."""
    name: str
    sensor_source: str
    native_resolution_m: float
    aggregation_window: str
    mean_value: float
    min_value: float
    max_value: float
    valid_fraction: float
    provenance_hash: str


@dataclass
class OpticalVegetationFeatures:
    """Container for optical canopy and moisture indices."""
    ndvi: np.ndarray
    evi: np.ndarray
    ndre: np.ndarray
    ndwi: np.ndarray
    valid_mask: np.ndarray
    provenance: DroughtFeatureRecord


@dataclass
class HydroclimaticFeatures:
    """Container for hydroclimatic and soil moisture features."""
    precip_1m_mm: np.ndarray
    precip_3m_mm: np.ndarray
    precip_6m_mm: np.ndarray
    soil_moisture_surface: np.ndarray
    soil_moisture_rootzone: np.ndarray
    lst_k: np.ndarray
    valid_mask: np.ndarray
    provenance: DroughtFeatureRecord


def compute_ndvi(nir: np.ndarray, red: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Compute Normalized Difference Vegetation Index (NDVI)."""
    denom = nir + red
    ndvi = np.where(denom > eps, (nir - red) / np.maximum(denom, eps), 0.0)
    return np.clip(ndvi, -1.0, 1.0).astype(np.float32)


def compute_evi(
    nir: np.ndarray,
    red: np.ndarray,
    blue: np.ndarray,
    g: float = 2.5,
    c1: float = 6.0,
    c2: float = 7.5,
    l: float = 1.0,
    eps: float = 1e-6,
) -> np.ndarray:
    """Compute Enhanced Vegetation Index (EVI)."""
    denom = nir + c1 * red - c2 * blue + l
    evi = np.where(denom > eps, g * (nir - red) / np.maximum(denom, eps), 0.0)
    return np.clip(evi, -1.0, 1.5).astype(np.float32)


def compute_ndre(nir: np.ndarray, red_edge: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Compute Normalized Difference Red Edge Index (NDRE)."""
    denom = nir + red_edge
    ndre = np.where(denom > eps, (nir - red_edge) / np.maximum(denom, eps), 0.0)
    return np.clip(ndre, -1.0, 1.0).astype(np.float32)


def compute_ndwi(nir: np.ndarray, swir: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Compute Normalized Difference Water/Moisture Index (NDWI/NDII)."""
    denom = nir + swir
    ndwi = np.where(denom > eps, (nir - swir) / np.maximum(denom, eps), 0.0)
    return np.clip(ndwi, -1.0, 1.0).astype(np.float32)


def extract_optical_features(
    blue: np.ndarray,
    red: np.ndarray,
    red_edge: np.ndarray,
    nir: np.ndarray,
    swir: np.ndarray,
    cloud_mask: np.ndarray | None = None,
    resolution_m: float = 20.0,
) -> OpticalVegetationFeatures:
    """Extract and validate optical vegetation indices with provenance."""
    valid = np.isfinite(blue) & np.isfinite(red) & np.isfinite(nir) & np.isfinite(swir)
    if cloud_mask is not None:
        valid = valid & (~cloud_mask)

    ndvi = compute_ndvi(nir, red)
    evi = compute_evi(nir, red, blue)
    ndre = compute_ndre(nir, red_edge)
    ndwi = compute_ndwi(nir, swir)

    # Mask invalid pixels
    ndvi = np.where(valid, ndvi, np.nan)
    evi = np.where(valid, evi, np.nan)
    ndre = np.where(valid, ndre, np.nan)
    ndwi = np.where(valid, ndwi, np.nan)

    valid_frac = float(np.mean(valid))
    mean_val = float(np.nanmean(ndvi)) if valid_frac > 0 else 0.0
    min_val = float(np.nanmin(ndvi)) if valid_frac > 0 else 0.0
    max_val = float(np.nanmax(ndvi)) if valid_frac > 0 else 0.0

    prov_hash = hashlib.sha256(
        f"OPTICAL_VEG_{valid_frac:.4f}_{mean_val:.4f}_{resolution_m}".encode()
    ).hexdigest()

    record = DroughtFeatureRecord(
        name="optical_vegetation_suite",
        sensor_source="Sentinel-2_MSI_L2A",
        native_resolution_m=resolution_m,
        aggregation_window="instantaneous",
        mean_value=round(mean_val, 4),
        min_value=round(min_val, 4),
        max_value=round(max_val, 4),
        valid_fraction=round(valid_frac, 4),
        provenance_hash=prov_hash,
    )

    return OpticalVegetationFeatures(
        ndvi=ndvi,
        evi=evi,
        ndre=ndre,
        ndwi=ndwi,
        valid_mask=valid,
        provenance=record,
    )
