from __future__ import annotations

"""Drought Module 3 Multi-Window Standardized Anomaly Vectors."""

import hashlib
from dataclasses import dataclass
import numpy as np

from .climatology import compute_standardized_anomaly, BaselineClimatology


@dataclass
class MultiWindowAnomalies:
    """Synchronized standardized anomaly fields across genuine 1M, 3M, and 6M temporal windows."""
    # Vegetation Anomaly (NDVI/EVI z-scores: negative indicates stress)
    veg_z_1m: np.ndarray
    veg_z_3m: np.ndarray
    veg_z_6m: np.ndarray

    # Precipitation Anomaly (z-scores: negative indicates deficit)
    precip_z_1m: np.ndarray
    precip_z_3m: np.ndarray
    precip_z_6m: np.ndarray

    # Soil Moisture Anomaly (Surface & Rootzone z-scores)
    sm_surf_z_1m: np.ndarray
    sm_rz_z_3m: np.ndarray

    # Thermal Stress Anomaly (LST z-score: positive indicates excessive heat)
    thermal_z_1m: np.ndarray

    valid_mask: np.ndarray
    provenance_hash: str


def compute_multiwindow_anomalies(
    current_ndvi_1m: np.ndarray,
    current_ndvi_3m: np.ndarray,
    current_ndvi_6m: np.ndarray,
    current_precip_1m_mm: np.ndarray,
    current_precip_3m_mm: np.ndarray,
    current_precip_6m_mm: np.ndarray,
    current_sm_surf: np.ndarray,
    current_sm_rz: np.ndarray,
    current_lst_k: np.ndarray,
    clim_ndvi_1m: BaselineClimatology,
    clim_ndvi_3m: BaselineClimatology,
    clim_ndvi_6m: BaselineClimatology,
    clim_precip_1m: BaselineClimatology,
    clim_precip_3m: BaselineClimatology,
    clim_precip_6m: BaselineClimatology,
    clim_sm_surf: BaselineClimatology,
    clim_sm_rz: BaselineClimatology,
    clim_lst: BaselineClimatology,
    valid_mask: np.ndarray,
) -> MultiWindowAnomalies:
    """Compute genuine, distinct standardized anomalies across all multi-temporal channels."""
    # Distinct 1M, 3M, and 6M vegetation anomalies
    z_veg_1m = compute_standardized_anomaly(current_ndvi_1m, clim_ndvi_1m.mean, clim_ndvi_1m.std)
    z_veg_3m = compute_standardized_anomaly(current_ndvi_3m, clim_ndvi_3m.mean, clim_ndvi_3m.std)
    z_veg_6m = compute_standardized_anomaly(current_ndvi_6m, clim_ndvi_6m.mean, clim_ndvi_6m.std)

    # Distinct 1M, 3M, and 6M precipitation anomalies
    z_precip_1m = compute_standardized_anomaly(current_precip_1m_mm, clim_precip_1m.mean, clim_precip_1m.std, min_std=5.0)
    z_precip_3m = compute_standardized_anomaly(current_precip_3m_mm, clim_precip_3m.mean, clim_precip_3m.std, min_std=10.0)
    z_precip_6m = compute_standardized_anomaly(current_precip_6m_mm, clim_precip_6m.mean, clim_precip_6m.std, min_std=15.0)

    # Surface (1M) and Root-Zone (3M) Soil Moisture anomalies
    z_sm_surf = compute_standardized_anomaly(current_sm_surf, clim_sm_surf.mean, clim_sm_surf.std, min_std=0.01)
    z_sm_rz = compute_standardized_anomaly(current_sm_rz, clim_sm_rz.mean, clim_sm_rz.std, min_std=0.01)

    # Thermal Stress (1M) LST anomaly
    z_lst = compute_standardized_anomaly(current_lst_k, clim_lst.mean, clim_lst.std, min_std=1.0)

    prov_hash = hashlib.sha256(
        f"MULTI_ANOM_V2_{np.nanmean(z_veg_1m):.3f}_{np.nanmean(z_veg_3m):.3f}_{np.nanmean(z_precip_3m):.3f}".encode()
    ).hexdigest()

    return MultiWindowAnomalies(
        veg_z_1m=z_veg_1m,
        veg_z_3m=z_veg_3m,
        veg_z_6m=z_veg_6m,
        precip_z_1m=z_precip_1m,
        precip_z_3m=z_precip_3m,
        precip_z_6m=z_precip_6m,
        sm_surf_z_1m=z_sm_surf,
        sm_rz_z_3m=z_sm_rz,
        thermal_z_1m=z_lst,
        valid_mask=valid_mask,
        provenance_hash=prov_hash,
    )
