from __future__ import annotations

"""Block 6B-C: Quantitative Observability Index & Resolution-Aware Tri-State Engine.

Formulates a continuous, physically grounded Observability Index:
    O = S_scale * W_water * G_geom * T_terrain * D_validity

Where:
1. D_validity in {0.0, 1.0}: Valid satellite pixel (SAR or Optical valid mask)
2. T_terrain in [0.0, 1.0]: Topographic slope penalty
   T = clip(1.0 - (slope_deg / 15.0), 0.0, 1.0)
3. G_geom in [0.0, 1.0]: Local relief roughness / radar shadow layover susceptibility
   G = clip(1.0 - (local_relief_m / 150.0), 0.0, 1.0)
4. W_water in [0.0, 1.0]: Intertidal dynamic water ambiguity
   W = 0.35 if (elev <= 2.5m and 0.10 <= occurrence < 0.70) else 1.0
5. S_scale in [0.0, 1.0]: Spatial resolution / channel width observability
   Estimated via distance transform / morphological scale relative to 20m SAR resolution:
   Narrow linear features (< 2 pixels / 40m) are penalized.

Decision Output Contract:
- Resolvable Domain: O >= O_threshold (default 0.50)
- FLOOD:      (O >= O_threshold) and (Score >= Threshold)
- NO_FLOOD:   (O >= O_threshold) and (Score < Threshold)
- UNRESOLVED: (O < O_threshold)
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from sklearn.metrics import precision_recall_curve, auc


@dataclass
class ObservabilityComponents:
    mean_observability: float
    resolvable_fraction: float
    unresolved_fraction: float
    mean_terrain_factor: float
    mean_geometry_factor: float
    mean_coastal_factor: float
    mean_scale_factor: float


@dataclass
class TriStateClassificationResult:
    status: str
    flood_mask: np.ndarray        # State 1: Confirmed Flood
    no_flood_mask: np.ndarray     # State 2: Confirmed Dry
    unresolved_mask: np.ndarray   # State 3: Observational Undecidability
    resolvable_mask: np.ndarray   # flood_mask | no_flood_mask
    observability_index: np.ndarray # Continuous O in [0.0, 1.0]
    total_pixels: int
    flood_pixels: int
    no_flood_pixels: int
    unresolved_pixels: int
    unresolved_fraction: float
    resolvable_pr_auc: float | None
    unconstrained_pr_auc: float | None
    delta_pr_auc: float | None
    components: ObservabilityComponents
    provenance_hash: str


def compute_continuous_observability_index(
    valid_mask: np.ndarray,
    slope_deg: np.ndarray,
    elevation_m: np.ndarray,
    jrc_occurrence: np.ndarray,
    pixel_resolution_m: float = 20.0,
    slope_max_deg: float = 15.0,
    relief_max_m: float = 150.0,
) -> tuple[np.ndarray, dict[str, float]]:
    """Compute continuous physical observability index O in [0.0, 1.0]."""
    # 1. Data Validity
    D = valid_mask.astype(np.float32)

    # 2. Terrain Slope Penalty
    T = np.clip(1.0 - (slope_deg / slope_max_deg), 0.0, 1.0)

    # 3. Local Relief Roughness (SAR Radar Shadow / Layover)
    # Computed as local max minus local min elevation in 5x5 neighborhood (100m window)
    local_max = ndimage.maximum_filter(elevation_m, size=5)
    local_min = ndimage.minimum_filter(elevation_m, size=5)
    local_relief = np.clip(local_max - local_min, 0.0, relief_max_m)
    G = np.clip(1.0 - (local_relief / relief_max_m), 0.0, 1.0)

    # 4. Coastal / Intertidal Ambiguity
    is_intertidal = (elevation_m <= 2.5) & (jrc_occurrence >= 0.10) & (jrc_occurrence < 0.70)
    W = np.where(is_intertidal, 0.35, 1.0).astype(np.float32)

    # 5. Spatial Scale & Channel Width Observability
    # For potential water / low elevation drainage channels, estimate hydraulic width
    # using morphological distance transform from non-water/ridge edges
    potential_valley = (slope_deg <= 5.0) | (jrc_occurrence > 0.0)
    dist_valley = ndimage.distance_transform_edt(potential_valley) * pixel_resolution_m
    # Channels narrower than 40m (2 pixels) have attenuated scale observability
    S = np.clip(dist_valley / (2.0 * pixel_resolution_m), 0.50, 1.0)
    # If not a valley, scale observability is 1.0
    S = np.where(potential_valley, S, 1.0).astype(np.float32)

    # Multiplicative Observability Formulation
    O = D * T * G * W * S
    O = np.clip(O, 0.0, 1.0)

    stats = {
        "mean_observability": float(np.mean(O)),
        "mean_terrain_factor": float(np.mean(T)),
        "mean_geometry_factor": float(np.mean(G)),
        "mean_coastal_factor": float(np.mean(W)),
        "mean_scale_factor": float(np.mean(S)),
    }
    return O, stats


def compute_tristate_flood_decision(
    flood_score: np.ndarray,
    valid_mask: np.ndarray,
    slope_deg: np.ndarray,
    elevation_m: np.ndarray,
    jrc_occurrence: np.ndarray,
    detection_threshold: float = 0.20,
    observability_threshold: float = 0.50,
    pixel_resolution_m: float = 20.0,
    cems_reference_mask: np.ndarray | None = None,
) -> TriStateClassificationResult:
    """Compute resolution-aware tri-state flood classification using continuous Observability Index."""
    O, stats = compute_continuous_observability_index(
        valid_mask=valid_mask,
        slope_deg=slope_deg,
        elevation_m=elevation_m,
        jrc_occurrence=jrc_occurrence,
        pixel_resolution_m=pixel_resolution_m,
    )

    resolvable_mask = (O >= observability_threshold) & valid_mask
    unresolved_mask = ~resolvable_mask

    flood_mask = resolvable_mask & (flood_score >= detection_threshold)
    no_flood_mask = resolvable_mask & (flood_score < detection_threshold)

    if flood_mask.any():
        flood_mask = ndimage.binary_opening(flood_mask, structure=np.ones((2, 2), dtype=bool))

    n_tot = int(flood_score.size)
    n_flood = int(np.sum(flood_mask))
    n_dry = int(np.sum(no_flood_mask))
    n_unres = int(np.sum(unresolved_mask))
    unres_frac = float(n_unres / n_tot)
    res_frac = float(1.0 - unres_frac)

    # Calculate PR-AUC over Full Domain vs Resolvable Domain
    pr_unconstrained = None
    pr_resolvable = None
    delta_pr = None

    if cems_reference_mask is not None and cems_reference_mask.any():
        ref_flat = cems_reference_mask.flatten().astype(int)
        sc_flat = flood_score.flatten()
        p_u, r_u, _ = precision_recall_curve(ref_flat, sc_flat)
        pr_unconstrained = float(auc(r_u, p_u))

        # Resolvable subset
        res_flat = resolvable_mask.flatten()
        if res_flat.any() and ref_flat[res_flat].any():
            p_r, r_r, _ = precision_recall_curve(ref_flat[res_flat], sc_flat[res_flat])
            pr_resolvable = float(auc(r_r, p_r))
            delta_pr = float(pr_resolvable - pr_unconstrained)

    comp = ObservabilityComponents(
        mean_observability=round(stats["mean_observability"], 4),
        resolvable_fraction=round(res_frac, 4),
        unresolved_fraction=round(unres_frac, 4),
        mean_terrain_factor=round(stats["mean_terrain_factor"], 4),
        mean_geometry_factor=round(stats["mean_geometry_factor"], 4),
        mean_coastal_factor=round(stats["mean_coastal_factor"], 4),
        mean_scale_factor=round(stats["mean_scale_factor"], 4),
    )

    prov_hash = hashlib.sha256(
        f"TRISTATE_V2_{n_flood}_{n_dry}_{n_unres}_{stats['mean_observability']:.4f}".encode()
    ).hexdigest()

    return TriStateClassificationResult(
        status="completed",
        flood_mask=flood_mask,
        no_flood_mask=no_flood_mask,
        unresolved_mask=unresolved_mask,
        resolvable_mask=resolvable_mask,
        observability_index=O,
        total_pixels=n_tot,
        flood_pixels=n_flood,
        no_flood_pixels=n_dry,
        unresolved_pixels=n_unres,
        unresolved_fraction=round(unres_frac, 4),
        resolvable_pr_auc=round(pr_resolvable, 5) if pr_resolvable is not None else None,
        unconstrained_pr_auc=round(pr_unconstrained, 5) if pr_unconstrained is not None else None,
        delta_pr_auc=round(delta_pr, 5) if delta_pr is not None else None,
        components=comp,
        provenance_hash=prov_hash,
    )
