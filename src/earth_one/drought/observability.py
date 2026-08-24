from __future__ import annotations

"""Drought Module 3 Observability & Attribution Ambiguity Engine (v0.2).

Disentangles two fundamentally distinct scientific quantities:
1. SENSOR OBSERVABILITY (O in [0.0, 1.0]):
   Can Earth One physically observe the land surface?
   O = D_telemetry * T_cloud * V_canopy_resolv

2. ATTRIBUTION AMBIGUITY (A in [0.0, 1.0]):
   Is the observed signal confounded by non-drought human or seasonal processes?
   A = max(A_irrigation_buffering, A_harvest_tillage)
"""

import hashlib
from dataclasses import dataclass
import numpy as np

from .config import DroughtConfig


@dataclass
class DroughtObservabilityResult:
    """Quantitative observability and attribution ambiguity breakdown."""
    observability_index: np.ndarray          # Pure Sensor Observability O in [0.0, 1.0]
    attribution_ambiguity_index: np.ndarray  # Attribution Confounder Index A in [0.0, 1.0]
    resolvable_mask: np.ndarray              # O >= threshold (0.50)
    unresolved_mask: np.ndarray              # O < threshold
    is_attribution_ambiguous: np.ndarray     # A >= 0.60
    mean_observability: float
    mean_attribution_ambiguity: float
    resolvable_fraction: float
    unresolved_fraction: float
    mean_telemetry_factor: float
    mean_cloud_factor: float
    mean_canopy_factor: float
    mean_irrigation_buffering: float
    mean_harvest_confound: float
    provenance_hash: str


def compute_drought_observability(
    valid_mask: np.ndarray,
    cloud_fraction: np.ndarray | float = 0.0,
    baseline_ndvi: np.ndarray | None = None,
    is_irrigated: np.ndarray | None = None,
    is_harvest_or_tillage: np.ndarray | None = None,
    config: DroughtConfig = DroughtConfig(),
) -> DroughtObservabilityResult:
    """Compute decoupled sensor observability O and attribution ambiguity A."""
    shape = valid_mask.shape

    # 1. Telemetry Validity Factor (D)
    D = valid_mask.astype(np.float32)

    # 2. Temporal Cloud Cover Factor (T) - using config.max_cloud_cover_fraction (0.40)
    if isinstance(cloud_fraction, (int, float)):
        cf_arr = np.full(shape, float(cloud_fraction), dtype=np.float32)
    else:
        cf_arr = cloud_fraction.astype(np.float32)
    T = np.clip(1.0 - (cf_arr / config.max_cloud_cover_fraction), 0.0, 1.0)

    # 3. Canopy Resolvability Factor (V) - bare sand/rock has low vegetation signal
    if baseline_ndvi is not None:
        V = np.clip(baseline_ndvi / config.min_vegetation_cover_ndvi, 0.25, 1.0).astype(np.float32)
    else:
        V = np.ones(shape, dtype=np.float32)

    # Pure Sensor Observability Formulation
    O = D * T * V
    O = np.clip(O, 0.0, 1.0)

    # 4. Attribution Ambiguity Factors (A)
    # Irrigation buffering: meteorological drought may exist but surface vegetation is artificially buffered
    if is_irrigated is not None:
        A_irrig = np.where(is_irrigated, 0.70, 0.0).astype(np.float32)
    else:
        A_irrig = np.zeros(shape, dtype=np.float32)

    # Harvest / sudden mechanical tillage: sudden drop in greenness is not meteorological drought
    if is_harvest_or_tillage is not None:
        A_harvest = np.where(is_harvest_or_tillage, 0.85, 0.0).astype(np.float32)
    else:
        A_harvest = np.zeros(shape, dtype=np.float32)

    A = np.maximum(A_irrig, A_harvest)
    A = np.clip(A, 0.0, 1.0)

    resolvable = (O >= config.observability_threshold) & valid_mask
    unresolved = ~resolvable
    is_ambig = (A >= config.attribution_ambiguity_threshold) & resolvable

    n_tot = int(O.size)
    n_res = int(np.sum(resolvable))
    res_frac = float(n_res / n_tot) if n_tot > 0 else 0.0
    unres_frac = float(1.0 - res_frac)

    prov_hash = hashlib.sha256(
        f"OBS_V2_{np.mean(O):.4f}_{np.mean(A):.4f}_{res_frac:.4f}".encode()
    ).hexdigest()

    return DroughtObservabilityResult(
        observability_index=O,
        attribution_ambiguity_index=A,
        resolvable_mask=resolvable,
        unresolved_mask=unresolved,
        is_attribution_ambiguous=is_ambig,
        mean_observability=round(float(np.mean(O)), 4),
        mean_attribution_ambiguity=round(float(np.mean(A)), 4),
        resolvable_fraction=round(res_frac, 4),
        unresolved_fraction=round(unres_frac, 4),
        mean_telemetry_factor=round(float(np.mean(D)), 4),
        mean_cloud_factor=round(float(np.mean(T)), 4),
        mean_canopy_factor=round(float(np.mean(V)), 4),
        mean_irrigation_buffering=round(float(np.mean(A_irrig)), 4),
        mean_harvest_confound=round(float(np.mean(A_harvest)), 4),
        provenance_hash=prov_hash,
    )
