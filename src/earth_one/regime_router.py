from __future__ import annotations

"""Autonomous Biophysical Regime Router v0.2 for Earth One Flood Module.

Classifies the biophysical and hydrologic regime of an AOI using ONLY independent,
pre-event Earth observation baselines (JRC GSW occurrence, Copernicus DEM elevation,
slope, and coastal profile). Strictly zero ground-truth validation leakage.

Key v0.2 Enhancements:
1. Robust Physical Discrimination: Distinguishes interior river valleys from true coastal mudflats.
2. Continuous Confidence-Weighted Score Blending: S_final = (1 - C) * S_global + C * S_regime.
3. Explicit Abstention: When confidence C < 0.60, router flags MIXED_UNCERTAIN and defaults to global baseline.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .flood import FloodEvidenceConfig
from .coastal_context import compute_intertidal_suppression_mask, CoastalContextProfile


@dataclass(frozen=True)
class RegimeRoutingResult:
    regime: str
    confidence: float
    recommended_config: FloodEvidenceConfig
    features: dict[str, float]
    uncertainty: float
    coastal_profile: CoastalContextProfile
    provenance_hash: str


def classify_biophysical_regime(
    jrc_occurrence: np.ndarray,
    elevation_m: np.ndarray,
    slope_deg: np.ndarray,
    centroid_lat: float = 0.0,
    centroid_lon: float = 0.0,
) -> RegimeRoutingResult:
    """
    Autonomous, zero-leakage biophysical regime classification.
    Derives regime from purely physical & historical hydrologic baseline rasters.
    """
    occ = np.asarray(jrc_occurrence, dtype=np.float32)
    elev = np.asarray(elevation_m, dtype=np.float32)
    slope = np.asarray(slope_deg, dtype=np.float32)

    valid = np.isfinite(occ) & np.isfinite(elev) & np.isfinite(slope)
    if not valid.any():
        raise ValueError("No valid pixels found in regime classification rasters.")

    # Compute Coastal Profile
    m_intertidal, coastal_prof = compute_intertidal_suppression_mask(occ, elev, slope)

    # Physical feature extraction
    v_occ = occ[valid]
    v_elev = elev[valid]
    v_slope = slope[valid]

    perm_water_frac = float(np.mean(v_occ >= 0.80))
    seasonal_water_frac = float(np.mean((v_occ >= 0.10) & (v_occ < 0.80)))
    dry_land_frac = float(np.mean(v_occ < 0.10))

    mean_elev = float(np.mean(v_elev))
    min_elev = float(np.min(v_elev))
    p10_elev = float(np.percentile(v_elev, 10))
    p90_elev = float(np.percentile(v_elev, 90))
    elev_relief = p90_elev - p10_elev

    mean_slope = float(np.mean(v_slope))
    flat_slope_frac = float(np.mean(v_slope <= 2.0))
    steep_slope_frac = float(np.mean(v_slope > 8.0))

    features = {
        "permanent_water_fraction": round(perm_water_frac, 4),
        "seasonal_water_fraction": round(seasonal_water_frac, 4),
        "dry_land_fraction": round(dry_land_frac, 4),
        "mean_elevation_m": round(mean_elev, 2),
        "min_elevation_m": round(min_elev, 2),
        "p10_elevation_m": round(p10_elev, 2),
        "elevation_relief_m": round(elev_relief, 2),
        "mean_slope_deg": round(mean_slope, 2),
        "flat_slope_fraction": round(flat_slope_frac, 4),
        "steep_slope_fraction": round(steep_slope_frac, 4),
        "is_coastal_aoi": bool(coastal_prof.is_coastal_aoi),
        "marine_fraction": round(coastal_prof.marine_fraction, 4),
        "intertidal_mudflat_fraction": round(coastal_prof.intertidal_mudflat_fraction, 4),
    }

    # Autonomous Physical Decision Tree v0.2
    # 1. Inland Riverine / Pluvial Valley: High relief or steep valleys (even if draining to low elevation)
    if elev_relief > 60.0 or steep_slope_frac > 0.10 or (mean_elev > 50.0 and steep_slope_frac > 0.05):
        regime = "INLAND_RIVERINE_PLUVIAL"
        confidence = float(np.clip(0.70 + 0.30 * min(1.0, elev_relief / 200.0), 0.70, 0.95))
        uncertainty = 1.0 - confidence

        cfg = FloodEvidenceConfig(
            fusion_strategy="gated_physics",
            weight_sar=0.35,
            weight_optical=0.25,
            weight_novelty=0.20,
            weight_rain=0.10,
            weight_terrain=0.10,
            terrain_max_slope_deg=6.0,
            terrain_cutoff_slope_deg=12.0,
            apply_morphological_opening=True,
            morphology_kernel_size=2,
            default_detection_threshold=0.20,
        )

    # 2. Coastal / Estuarine / Tidal: Low sea-level coastal plains, deltaic estuaries, and tidal flats
    elif coastal_prof.is_coastal_aoi and (coastal_prof.marine_fraction > 0.04 or coastal_prof.intertidal_mudflat_fraction > 0.03 or p10_elev <= 3.0):
        regime = "COASTAL_ESTUARINE_TIDAL"
        confidence = float(np.clip(0.70 + 0.30 * (coastal_prof.marine_fraction + coastal_prof.intertidal_mudflat_fraction), 0.70, 0.95))
        uncertainty = 1.0 - confidence

        cfg = FloodEvidenceConfig(
            fusion_strategy="gated_physics",
            weight_sar=0.32,
            weight_optical=0.28,
            weight_novelty=0.25,
            weight_rain=0.08,
            weight_terrain=0.07,
            sar_delta_vv_thresh_db=-2.2,
            permanent_water_max_freq=0.75,
            apply_morphological_opening=True,
            morphology_kernel_size=2,  # Soft 2x2 morphology
            default_detection_threshold=0.20,
        )

    # 3. Inland Mega-Riverine Basin: Flat expansive plains, dry land dominated
    elif flat_slope_frac >= 0.65 and elev_relief <= 60.0 and dry_land_frac >= 0.65:
        regime = "INLAND_RIVERINE_MEGA"
        confidence = float(np.clip(0.75 + 0.25 * flat_slope_frac, 0.75, 0.98))
        uncertainty = 1.0 - confidence

        cfg = FloodEvidenceConfig(
            fusion_strategy="gated_physics",
            weight_sar=0.40,
            weight_optical=0.25,
            weight_novelty=0.20,
            weight_rain=0.10,
            weight_terrain=0.05,
            sar_delta_vv_thresh_db=-2.0,
            permanent_water_max_freq=0.80,
            apply_morphological_opening=True,
            morphology_kernel_size=2,
            default_detection_threshold=0.20,
        )

    # 4. Wetland / Seasonal Water
    elif seasonal_water_frac >= 0.20:
        regime = "WETLAND_SEASONAL"
        confidence = 0.75
        uncertainty = 0.25
        cfg = FloodEvidenceConfig(
            fusion_strategy="gated_physics",
            weight_sar=0.30,
            weight_optical=0.30,
            weight_novelty=0.30,
            weight_rain=0.05,
            weight_terrain=0.05,
            permanent_water_max_freq=0.60,
            apply_morphological_opening=True,
            morphology_kernel_size=2,
            default_detection_threshold=0.20,
        )

    # 5. Mixed / Uncertain (Abstain)
    else:
        regime = "MIXED_UNCERTAIN"
        confidence = 0.50
        uncertainty = 0.50
        cfg = FloodEvidenceConfig(fusion_strategy="gated_physics")

    # If confidence is below safety floor, abstain to MIXED_UNCERTAIN
    if confidence < 0.60:
        regime = "MIXED_UNCERTAIN"
        confidence = 0.50
        uncertainty = 0.50
        cfg = FloodEvidenceConfig(fusion_strategy="gated_physics")

    prov_dict = {
        "regime": regime,
        "confidence": round(confidence, 4),
        "features": features,
        "centroid_lat": round(centroid_lat, 4),
        "centroid_lon": round(centroid_lon, 4),
    }
    prov_hash = hashlib.sha256(json.dumps(prov_dict, sort_keys=True).encode("utf-8")).hexdigest()

    return RegimeRoutingResult(
        regime=regime,
        confidence=round(confidence, 4),
        recommended_config=cfg,
        features=features,
        uncertainty=round(uncertainty, 4),
        coastal_profile=coastal_prof,
        provenance_hash=prov_hash,
    )
