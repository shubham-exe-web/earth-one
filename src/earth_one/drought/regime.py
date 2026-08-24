from __future__ import annotations

"""Drought Module 3 Contextual Biophysical Regime Router (v0.2).

Disentangles biophysical landscape context using multi-layer evidence:
1. Land cover classification (if available).
2. Seasonal phenological dynamic amplitude (Delta_NDVI = max - min).
3. Baseline canopy density (mean NDVI).
4. Irrigation presence / likelihood.
5. Surface water occurrence.

Zero-leakage guarantee: Strictly independent of drought ground-truth validation labels.
"""

from dataclasses import dataclass
from typing import Any
import numpy as np

from .config import DroughtRegimeType, ModalityWeights


@dataclass
class RegimeEvidenceContext:
    mean_baseline_ndvi: float
    seasonal_phenology_amplitude: float
    irrigation_fraction: float
    surface_water_fraction: float
    land_cover_hint: str | None


@dataclass
class RegimeClassificationResult:
    """Result of biophysical regime routing with adapted modality fusion weights."""
    regime: DroughtRegimeType
    confidence: float
    is_irrigated: bool
    recommended_modality_weights: ModalityWeights
    evidence_context: RegimeEvidenceContext
    explanation: str


def classify_drought_regime(
    baseline_mean_ndvi: np.ndarray,
    baseline_min_ndvi: np.ndarray | None = None,
    baseline_max_ndvi: np.ndarray | None = None,
    land_cover_class: np.ndarray | str | None = None,
    is_irrigation_active: np.ndarray | None = None,
    surface_water_occurrence: np.ndarray | None = None,
) -> RegimeClassificationResult:
    """Autonomously route biophysical regime using contextual phenology and land structure."""
    mean_ndvi_scalar = float(np.nanmean(baseline_mean_ndvi))
    
    # Calculate seasonal phenological dynamic amplitude
    if baseline_min_ndvi is not None and baseline_max_ndvi is not None:
        amplitude = float(np.nanmean(baseline_max_ndvi - baseline_min_ndvi))
    else:
        # Default estimate based on mean NDVI if seasonal bounds not provided
        amplitude = 0.25

    irrig_frac = float(np.nanmean(is_irrigation_active)) if is_irrigation_active is not None else 0.0
    water_frac = float(np.nanmean(surface_water_occurrence)) if surface_water_occurrence is not None else 0.0

    lc_hint = land_cover_class if isinstance(land_cover_class, str) else None

    ctx = RegimeEvidenceContext(
        mean_baseline_ndvi=round(mean_ndvi_scalar, 3),
        seasonal_phenology_amplitude=round(amplitude, 3),
        irrigation_fraction=round(irrig_frac, 3),
        surface_water_fraction=round(water_frac, 3),
        land_cover_hint=lc_hint,
    )

    # 1. Wetland / Riparian Corridor
    if water_frac >= 0.20 or lc_hint == "wetland":
        weights = ModalityWeights(vegetation=0.20, precipitation=0.30, soil_moisture=0.40, thermal=0.10)
        return RegimeClassificationResult(
            regime="WETLAND_HIGH_MOISTURE",
            confidence=0.88,
            is_irrigated=False,
            recommended_modality_weights=weights,
            evidence_context=ctx,
            explanation="High surface water occurrence (>=20%) indicating riparian/wetland corridor.",
        )

    # 2. Irrigated Agriculture
    if irrig_frac >= 0.30 or lc_hint == "irrigated_cropland":
        # In irrigated crops, vegetation decline is artificially masked; prioritize soil & precipitation
        weights = ModalityWeights(vegetation=0.15, precipitation=0.40, soil_moisture=0.35, thermal=0.10)
        return RegimeClassificationResult(
            regime="IRRIGATED_AGRICULTURE",
            confidence=0.90,
            is_irrigated=True,
            recommended_modality_weights=weights,
            evidence_context=ctx,
            explanation="Active irrigation detected: down-weighting surface vegetation masking.",
        )

    # 3. Dryland / Sparse Vegetation (Low mean NDVI AND low seasonal amplitude)
    if mean_ndvi_scalar < 0.20 and amplitude < 0.20 or lc_hint == "dryland":
        weights = ModalityWeights(vegetation=0.20, precipitation=0.35, soil_moisture=0.30, thermal=0.15)
        return RegimeClassificationResult(
            regime="DRYLAND_SPARSE",
            confidence=0.88,
            is_irrigated=False,
            recommended_modality_weights=weights,
            evidence_context=ctx,
            explanation="Low baseline greenness (NDVI < 0.20) and low phenological range: arid dryland.",
        )

    # 4. Dense Cropland (High peak/mean NDVI, but HIGH seasonal phenology amplitude)
    if amplitude >= 0.35 or lc_hint == "cropland":
        weights = ModalityWeights(vegetation=0.35, precipitation=0.35, soil_moisture=0.20, thermal=0.10)
        return RegimeClassificationResult(
            regime="RAINFED_AGRICULTURE",
            confidence=0.86,
            is_irrigated=False,
            recommended_modality_weights=weights,
            evidence_context=ctx,
            explanation=f"High seasonal phenological amplitude (Δ={amplitude:.2f}): active annual agricultural cultivation.",
        )

    # 5. Forest (High baseline NDVI >= 0.55 AND low/moderate phenology amplitude < 0.30)
    if mean_ndvi_scalar >= 0.55 and amplitude < 0.30 or lc_hint == "forest":
        weights = ModalityWeights(vegetation=0.40, precipitation=0.25, soil_moisture=0.25, thermal=0.10)
        return RegimeClassificationResult(
            regime="FOREST",
            confidence=0.92,
            is_irrigated=False,
            recommended_modality_weights=weights,
            evidence_context=ctx,
            explanation="High baseline greenness with persistent canopy structure: dense forest regime.",
        )

    # 6. Grassland / Shrubland (Intermediate greenness)
    weights = ModalityWeights(vegetation=0.40, precipitation=0.35, soil_moisture=0.20, thermal=0.05)
    return RegimeClassificationResult(
        regime="GRASSLAND_SHRUBLAND",
        confidence=0.82,
        is_irrigated=False,
        recommended_modality_weights=weights,
        evidence_context=ctx,
        explanation="Herbaceous dynamic canopy: grassland/shrubland ecosystem.",
    )
