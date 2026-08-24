from __future__ import annotations

"""Drought Module 3 Real Earth Observation Data Ingestion & Harmonization Layer (Phase 2)."""

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np

from .features import compute_ndvi, compute_evi, compute_ndre, compute_ndwi


@dataclass
class Sentinel2L2AGranule:
    """Bottom-Of-Atmosphere (BOA) surface reflectance granule with Scene Classification (SCL)."""
    granule_id: str
    acquisition_timestamp: str
    native_crs: str
    transform: tuple[float, float, float, float, float, float]  # Affine 6-tuple
    resolution_m: float

    # BOA Reflectance Bands (values in [0.0, 1.0])
    b02_blue: np.ndarray
    b04_red: np.ndarray
    b05_red_edge: np.ndarray
    b08_nir: np.ndarray
    b11_swir1: np.ndarray
    scl_classification: np.ndarray  # SCL: 3=cloud shadow, 4=veg, 5=bare, 6=water, 7=unclassified, 8/9/10=cloud, 11=snow

    def get_cloud_shadow_mask(self) -> np.ndarray:
        """Extract cloud and cloud-shadow mask from SCL layer."""
        # Cloud shadows (3), Cloud medium/high/cirrus (8, 9, 10), Snow/ice (11), Saturated/defective (1)
        is_bad = np.isin(self.scl_classification, [1, 3, 8, 9, 10, 11])
        return is_bad

    def compute_indices(self) -> dict[str, np.ndarray]:
        """Compute BOA optical indices with cloud/shadow QA filtering."""
        qa_mask = self.get_cloud_shadow_mask()
        valid = (~qa_mask) & np.isfinite(self.b02_blue) & np.isfinite(self.b04_red) & np.isfinite(self.b08_nir)

        ndvi = np.where(valid, compute_ndvi(self.b08_nir, self.b04_red), np.nan)
        evi = np.where(valid, compute_evi(self.b08_nir, self.b04_red, self.b02_blue), np.nan)
        ndre = np.where(valid, compute_ndre(self.b08_nir, self.b05_red_edge), np.nan)
        ndwi = np.where(valid, compute_ndwi(self.b08_nir, self.b11_swir1), np.nan)

        return {
            "ndvi": ndvi.astype(np.float32),
            "evi": evi.astype(np.float32),
            "ndre": ndre.astype(np.float32),
            "ndwi": ndwi.astype(np.float32),
            "valid_mask": valid,
            "cloud_mask": qa_mask,
        }


@dataclass
class PrecipitationRasterObservation:
    """Precipitation multi-window accumulations from GPM IMERG Final or ERA5-Land."""
    product_name: str  # e.g., "GPM_IMERG_V06B" or "ERA5_LAND_PRECIP"
    timestamp: str
    precip_1m_mm: np.ndarray
    precip_3m_mm: np.ndarray
    precip_6m_mm: np.ndarray
    provenance_hash: str


@dataclass
class SoilMoistureRasterObservation:
    """Surface and root-zone soil water content from SMAP L3 or ERA5-Land."""
    product_name: str  # e.g., "SMAP_L3_SM_P" or "ERA5_LAND_SOIL_WATER"
    timestamp: str
    surface_sm_m3m3: np.ndarray    # Layer 1: 0-7 cm
    rootzone_sm_m3m3: np.ndarray   # Layer 2/3: 7-100 cm
    provenance_hash: str


@dataclass
class ThermalLSTObservation:
    """Land Surface Temperature (LST) thermal observation from Landsat/MODIS/ERA5."""
    product_name: str  # e.g., "LANDSAT_8_9_ST" or "MODIS_MOD11A1"
    timestamp: str
    lst_kelvin: np.ndarray
    provenance_hash: str


@dataclass
class RealEODroughtSceneStack:
    """Complete synchronized real Earth Observation scene stack for one analysis epoch."""
    aoi_id: str
    epoch_timestamp: str
    optical: Sentinel2L2AGranule
    precipitation: PrecipitationRasterObservation
    soil_moisture: SoilMoistureRasterObservation
    thermal: ThermalLSTObservation
    provenance_hash: str
