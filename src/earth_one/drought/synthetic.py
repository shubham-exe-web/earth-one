from __future__ import annotations

"""Drought Module 3 Synthetic Benchmark Case Generator (Cases A–I, v0.2)."""

from dataclasses import dataclass
import numpy as np

from .climatology import build_synthetic_climatology, BaselineClimatology
from .anomalies import MultiWindowAnomalies
from .regime import classify_drought_regime, RegimeClassificationResult
from .observability import compute_drought_observability, DroughtObservabilityResult
from .fusion import fuse_drought_evidence, DroughtEvidenceBreakdown
from .classifier import classify_tristate_drought, TriStateDroughtDecision
from .events import extract_drought_events, DroughtSegmentationResult


@dataclass
class SyntheticDroughtCase:
    """Standardized synthetic benchmark test case container."""
    case_name: str
    description: str
    shape: tuple[int, int]
    anomalies: MultiWindowAnomalies
    regime_context: RegimeClassificationResult
    observability: DroughtObservabilityResult
    evidence: DroughtEvidenceBreakdown
    decision: TriStateDroughtDecision
    segmentation: DroughtSegmentationResult


def generate_synthetic_benchmark_case(
    case_key: str,
    shape: tuple[int, int] = (64, 64),
) -> SyntheticDroughtCase:
    """Generate reproducible synthetic benchmark test case A–I with distinct multi-temporal windows."""
    H, W = shape
    valid_mask = np.ones(shape, dtype=bool)

    # Climatologies with seasonal amplitude for regime router
    clim_ndvi_1m = build_synthetic_climatology(shape, "ndvi_1m", 7, 0.60, 0.08)
    clim_ndvi_3m = build_synthetic_climatology(shape, "ndvi_3m", 7, 0.58, 0.07)
    clim_ndvi_6m = build_synthetic_climatology(shape, "ndvi_6m", 7, 0.55, 0.06)

    cloud_frac = 0.0
    is_irrig = None
    is_harvest = None

    if case_key == "CASE_A_HEALTHY":
        desc = "Healthy vegetation: normal greenness across all windows, zero precipitation or soil moisture deficit."
        z_v1, z_v3, z_v6 = 0.2, 0.1, 0.1
        z_p1, z_p3, z_p6 = 0.1, 0.0, 0.0
        z_sms, z_smrz, z_lst = 0.1, 0.1, -0.2

    elif case_key == "CASE_B_METEOROLOGICAL_DROUGHT":
        desc = "Rapid meteorological drought: sharp 1-month rainfall deficit (-2.2z), surface drying, vegetation not yet degraded (-0.2z)."
        z_v1, z_v3, z_v6 = -0.2, 0.0, 0.1
        z_p1, z_p3, z_p6 = -2.2, -1.2, -0.5
        z_sms, z_smrz, z_lst = -1.5, -0.8, 1.2

    elif case_key == "CASE_C_AGRICULTURAL_DROUGHT":
        desc = "Prolonged agricultural drought: 3M/6M precipitation deficit, root-zone soil moisture deficit, severe multi-window NDVI drop."
        z_v1, z_v3, z_v6 = -2.1, -2.4, -2.0
        z_p1, z_p3, z_p6 = -1.8, -2.4, -2.0
        z_sms, z_smrz, z_lst = -2.2, -2.3, 1.8

    elif case_key == "CASE_D_IRRIGATION_MASKED":
        desc = "Irrigated agriculture: severe precipitation deficit, but active irrigation maintains high NDVI."
        z_v1, z_v3, z_v6 = 0.1, 0.2, 0.1
        z_p1, z_p3, z_p6 = -2.2, -2.1, -1.9
        z_sms, z_smrz, z_lst = -1.8, -1.6, 0.8
        is_irrig = np.ones(shape, dtype=bool)

    elif case_key == "CASE_E_HARVEST_TILLAGE":
        desc = "Crop harvest: sudden sharp 1M NDVI plunge (-3.0z) without precipitation or soil moisture deficit."
        z_v1, z_v3, z_v6 = -3.0, -1.0, 0.0
        z_p1, z_p3, z_p6 = 0.2, 0.1, 0.0
        z_sms, z_smrz, z_lst = 0.0, 0.1, 0.2
        is_harvest = np.ones(shape, dtype=bool)

    elif case_key == "CASE_F_CLOUDY_BLACKOUT":
        desc = "Sensor blackout: 100% persistent cloud obscuration with missing optical telemetry."
        z_v1, z_v3, z_v6 = 0.0, 0.0, 0.0
        z_p1, z_p3, z_p6 = -1.5, -1.5, -1.5
        z_sms, z_smrz, z_lst = -1.5, -1.5, 0.0
        cloud_frac = 1.0

    elif case_key == "CASE_G_CONTRADICTORY":
        desc = "Contradictory evidence: strong rainfall surplus (+2.2z) with anomalous localized 1M NDVI drop."
        z_v1, z_v3, z_v6 = -1.8, -0.5, 0.0
        z_p1, z_p3, z_p6 = 2.2, 2.0, 1.8
        z_sms, z_smrz, z_lst = 1.5, 1.2, -1.0

    elif case_key == "CASE_H_EXTREME_DROUGHT":
        desc = "Extreme multi-season drought: severe deficits across all multi-temporal channels."
        z_v1, z_v3, z_v6 = -2.8, -3.0, -2.9
        z_p1, z_p3, z_p6 = -2.7, -3.0, -2.9
        z_sms, z_smrz, z_lst = -2.8, -2.9, 2.5

    elif case_key == "CASE_I_RECOVERY":
        desc = "Post-drought recovery: returning rainfall (+1.5z) and recharging soil moisture (+0.8z)."
        z_v1, z_v3, z_v6 = -0.5, -0.8, -1.2
        z_p1, z_p3, z_p6 = 1.5, 1.2, 0.8
        z_sms, z_smrz, z_lst = 0.8, 0.5, -0.5

    else:
        raise ValueError(f"Unknown synthetic case key: {case_key}")

    anom = MultiWindowAnomalies(
        veg_z_1m=np.full(shape, z_v1, dtype=np.float32),
        veg_z_3m=np.full(shape, z_v3, dtype=np.float32),
        veg_z_6m=np.full(shape, z_v6, dtype=np.float32),
        precip_z_1m=np.full(shape, z_p1, dtype=np.float32),
        precip_z_3m=np.full(shape, z_p3, dtype=np.float32),
        precip_z_6m=np.full(shape, z_p6, dtype=np.float32),
        sm_surf_z_1m=np.full(shape, z_sms, dtype=np.float32),
        sm_rz_z_3m=np.full(shape, z_smrz, dtype=np.float32),
        thermal_z_1m=np.full(shape, z_lst, dtype=np.float32),
        valid_mask=valid_mask,
        provenance_hash=f"SYNTH_V2_{case_key}",
    )

    regime = classify_drought_regime(
        baseline_mean_ndvi=clim_ndvi_1m.mean,
        baseline_min_ndvi=clim_ndvi_1m.min_observed,
        baseline_max_ndvi=clim_ndvi_1m.max_observed,
        is_irrigation_active=is_irrig,
    )

    obs = compute_drought_observability(
        valid_mask=valid_mask,
        cloud_fraction=cloud_frac,
        baseline_ndvi=clim_ndvi_1m.mean,
        is_irrigated=is_irrig,
        is_harvest_or_tillage=is_harvest,
    )

    ev = fuse_drought_evidence(anom, regime)
    dec = classify_tristate_drought(ev, obs)
    seg = extract_drought_events(dec, ev.fused_drought_score, obs, resolution_m=20.0)

    return SyntheticDroughtCase(
        case_name=case_key,
        description=desc,
        shape=shape,
        anomalies=anom,
        regime_context=regime,
        observability=obs,
        evidence=ev,
        decision=dec,
        segmentation=seg,
    )
