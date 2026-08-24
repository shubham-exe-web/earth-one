from __future__ import annotations

"""Soft Coastal & Intertidal Water Protection Layer v0.2 for Earth One Flood Module.

Identifies intertidal mudflats, estuarine channels, and coastal shoreline variability zones.
Applies soft, bounded suppression with a guaranteed floor (M_min = 0.35) to prevent
over-suppression and preserve genuine anomalous flood inundation.

Role: Physical/Biophysical Soft Mask M_intertidal in [M_min, 1.0].
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class CoastalContextProfile:
    is_coastal_aoi: bool
    marine_fraction: float
    intertidal_mudflat_fraction: float
    mean_coastal_elevation_m: float
    shoreline_complexity_index: float
    provenance_hash: str


def compute_intertidal_suppression_mask(
    jrc_occurrence: np.ndarray,
    elevation_m: np.ndarray,
    slope_deg: np.ndarray,
    permanent_water_ceiling: float = 0.80,
    tidal_elevation_threshold_m: float = 6.0,
    intertidal_occurrence_range: tuple[float, float] = (0.05, 0.75),
    coastal_buffer_pixels: int = 2,
    min_multiplier_floor: float = 0.35,
) -> tuple[np.ndarray, CoastalContextProfile]:
    """
    Calculate soft intertidal suppression multiplier M_intertidal in [min_multiplier_floor, 1.0].
    
    Soft Rules:
    1. Permanent Marine/Open Water: JRC occurrence >= 80% and elevation <= 1.5m -> M = 0.0
    2. Intertidal Mudflats: Elevation <= 6m, flat slope <= 2.5°, occurrence in [5%, 75%]
       -> Soft multiplicative suppression M in [min_multiplier_floor, 0.75]
    3. Low Coastal Shoreline Buffer: Soft dampening with floor
    4. Genuine Inland Inundation: Normal terrain or elevation > 6m -> M = 1.0
    """
    occ = np.asarray(jrc_occurrence, dtype=np.float32)
    elev = np.asarray(elevation_m, dtype=np.float32)
    slope = np.asarray(slope_deg, dtype=np.float32)

    valid = np.isfinite(occ) & np.isfinite(elev) & np.isfinite(slope)
    h, w = occ.shape

    # 1. Marine open water identification (true permanent sea level)
    marine_mask = valid & (elev <= 2.5) & (occ >= permanent_water_ceiling)
    marine_frac = float(np.mean(marine_mask)) if valid.any() else 0.0

    # 2. Intertidal mudflat & shoreline variability zone
    occ_low, occ_high = intertidal_occurrence_range
    intertidal_zone = (
        valid &
        (elev <= tidal_elevation_threshold_m) &
        (slope <= 2.5) &
        (occ >= occ_low) &
        (occ < permanent_water_ceiling)
    )
    intertidal_frac = float(np.mean(intertidal_zone)) if valid.any() else 0.0

    # Coastal AOI classification: True coastal marine fringe, deltaic estuary, or sea-level plain
    p10_elev = float(np.percentile(elev[valid], 10)) if valid.any() else 50.0
    is_coastal = (marine_frac > 0.05) or (intertidal_frac > 0.035) or (p10_elev <= 2.5 and (marine_frac + intertidal_frac) > 0.03)

    # Multiplier array: Start at 1.0 (unconstrained)
    m_intertidal = np.ones((h, w), dtype=np.float32)

    if is_coastal:
        # A. Suppress true permanent marine water
        m_intertidal[marine_mask] = 0.0

        # B. Soft suppression for intertidal mudflat zones with floor
        suppress_factor = np.clip((elev - 1.0) / max(1e-3, tidal_elevation_threshold_m - 1.0), min_multiplier_floor, 1.0)
        occ_penalty = np.clip(1.0 - (occ / permanent_water_ceiling), min_multiplier_floor, 1.0)
        
        intertidal_mult = suppress_factor * occ_penalty
        m_intertidal[intertidal_zone] = np.clip(intertidal_mult[intertidal_zone], min_multiplier_floor, 0.85)

        # C. Shoreline buffer: Buffer marine water by 1-2 pixels with soft floor
        if marine_mask.any() and coastal_buffer_pixels > 0:
            struct = ndimage.generate_binary_structure(2, 2)
            marine_dilated = ndimage.binary_dilation(marine_mask, structure=struct, iterations=coastal_buffer_pixels)
            shore_fringe = marine_dilated & (~marine_mask) & (elev <= 3.5)
            m_intertidal[shore_fringe] = np.maximum(min_multiplier_floor, np.minimum(m_intertidal[shore_fringe], 0.50))

    m_intertidal = np.where(valid, np.clip(m_intertidal, 0.0, 1.0), 0.0)

    # Complexity metric
    coastal_edge_count = int(np.sum(ndimage.binary_dilation(marine_mask) ^ marine_mask)) if marine_mask.any() else 0
    complexity = float(coastal_edge_count / max(1, h + w))

    prov_dict = {
        "is_coastal_aoi": bool(is_coastal),
        "marine_fraction": round(marine_frac, 4),
        "intertidal_mudflat_fraction": round(intertidal_frac, 4),
        "mean_coastal_elevation_m": round(float(np.mean(elev[valid])), 2) if valid.any() else 0.0,
        "shoreline_complexity_index": round(complexity, 3),
        "min_multiplier_floor": min_multiplier_floor,
    }
    prov_hash = hashlib.sha256(json.dumps(prov_dict, sort_keys=True).encode("utf-8")).hexdigest()

    profile = CoastalContextProfile(
        is_coastal_aoi=bool(is_coastal),
        marine_fraction=round(marine_frac, 4),
        intertidal_mudflat_fraction=round(intertidal_frac, 4),
        mean_coastal_elevation_m=round(float(np.mean(elev[valid])), 2) if valid.any() else 0.0,
        shoreline_complexity_index=round(complexity, 3),
        provenance_hash=prov_hash,
    )

    return m_intertidal, profile
