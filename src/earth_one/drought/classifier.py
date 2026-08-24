from __future__ import annotations

"""Drought Module 3 Tri-State Decision Engine (v0.2).

Enforces the Scientific Tri-State Decision Contract:
1. DROUGHT:
   - Sufficient sensor observability (O >= 0.50)
   - Statistically significant multi-modal stress evidence (S_drought >= T_drought)
   - Not confounded by non-drought harvest/tillage artifacts.

2. NO_DROUGHT:
   - Sufficient sensor observability (O >= 0.50)
   - Low stress score (S_drought < T_drought)
   - Positive evidence of normal/healthy conditions across at least 2 primary modalities.

3. UNRESOLVED:
   - Inadequate observability (O < 0.50), missing telemetry, or contradictory/unverifiable state.
   - Core guarantee: "No evidence" NEVER becomes "NO_DROUGHT".
"""

import hashlib
from dataclasses import dataclass
import numpy as np
from scipy import ndimage

from .config import DroughtConfig
from .observability import DroughtObservabilityResult
from .fusion import DroughtEvidenceBreakdown


@dataclass
class TriStateDroughtDecision:
    """Resolution-aware tri-state classification output with positive evidence verification."""
    drought_mask: np.ndarray        # State 1: Confirmed Drought
    no_drought_mask: np.ndarray     # State 2: Confirmed Normal/Healthy (Verified positive evidence)
    unresolved_mask: np.ndarray     # State 3: Observational Undecidability or Inadequate Evidence
    resolvable_mask: np.ndarray     # O >= 0.50
    total_pixels: int
    drought_pixels: int
    no_drought_pixels: int
    unresolved_pixels: int
    drought_fraction: float
    unresolved_fraction: float
    provenance_hash: str


def classify_tristate_drought(
    evidence: DroughtEvidenceBreakdown,
    observability: DroughtObservabilityResult,
    config: DroughtConfig = DroughtConfig(),
    apply_spatial_regularization: bool = False,
) -> TriStateDroughtDecision:
    """Enforce the Tri-State Drought Decision Contract."""
    s_score = evidence.fused_drought_score
    res_mask = observability.resolvable_mask

    # 1. State 1: Confirmed Drought
    # Must have high observability, score above threshold, and not be pure harvest artifact
    is_drought = res_mask & (s_score >= config.drought_detection_threshold)
    if observability.is_attribution_ambiguous is not None:
        # If confounded by harvest/tillage, suppress false drought declaration
        is_harvest = (observability.attribution_ambiguity_index >= 0.80)
        is_drought = is_drought & (~is_harvest)

    # Optional spatial regularization (disabled by default for raw fidelity)
    if apply_spatial_regularization and is_drought.any():
        is_drought = ndimage.binary_opening(is_drought, structure=np.ones((2, 2), dtype=bool))

    # 2. State 2: Confirmed NO_DROUGHT (Requires positive evidence of normal state)
    # Check that at least 2 primary modalities exhibit low stress (< 0.35)
    veg_normal = (evidence.vegetation_stress_score < config.drought_watch_threshold)
    pr_normal = (evidence.precipitation_deficit_score < config.drought_watch_threshold)
    sm_normal = (evidence.soil_moisture_deficit_score < config.drought_watch_threshold)
    
    normal_modality_count = veg_normal.astype(int) + pr_normal.astype(int) + sm_normal.astype(int)
    has_positive_normal_evidence = (normal_modality_count >= config.no_drought_min_required_modalities)

    is_no_drought = res_mask & (s_score < config.drought_detection_threshold) & has_positive_normal_evidence & (~is_drought)

    # 3. State 3: UNRESOLVED (Everything else: low observability, missing data, or unverified normal)
    is_unresolved = ~(is_drought | is_no_drought)

    n_tot = int(s_score.size)
    n_dr = int(np.sum(is_drought))
    n_nodr = int(np.sum(is_no_drought))
    n_unres = int(np.sum(is_unresolved))

    dr_frac = float(n_dr / n_tot) if n_tot > 0 else 0.0
    unres_frac = float(n_unres / n_tot) if n_tot > 0 else 0.0

    prov_hash = hashlib.sha256(
        f"TRISTATE_V2_{n_dr}_{n_nodr}_{n_unres}".encode()
    ).hexdigest()

    return TriStateDroughtDecision(
        drought_mask=is_drought,
        no_drought_mask=is_no_drought,
        unresolved_mask=is_unresolved,
        resolvable_mask=res_mask,
        total_pixels=n_tot,
        drought_pixels=n_dr,
        no_drought_pixels=n_nodr,
        unresolved_pixels=n_unres,
        drought_fraction=round(dr_frac, 4),
        unresolved_fraction=round(unres_frac, 4),
        provenance_hash=prov_hash,
    )
