import numpy as np
from earth_one.drought.config import DroughtConfig
from earth_one.drought.observability import DroughtObservabilityResult
from earth_one.drought.fusion import DroughtEvidenceBreakdown
from earth_one.drought.classifier import classify_tristate_drought


def test_tristate_positive_normal_evidence_required():
    shape = (20, 20)
    score_low = np.full(shape, 0.15, dtype=np.float32)
    score_high = np.full(shape, 0.85, dtype=np.float32)

    # Sub-region 1: High stress (Confirmed Drought)
    score = score_low.copy()
    score[0:10, 0:10] = 0.85

    obs_idx = np.full(shape, 0.90, dtype=np.float32)
    res_mask = (obs_idx >= 0.50)
    unres_mask = ~res_mask

    ev = DroughtEvidenceBreakdown(
        vegetation_stress_score=score,
        precipitation_deficit_score=score,
        soil_moisture_deficit_score=score,
        thermal_stress_score=score,
        fused_drought_score=score,
        modality_weights_applied=None,
        provenance_hash="TEST_EV",
    )

    obs = DroughtObservabilityResult(
        observability_index=obs_idx,
        attribution_ambiguity_index=np.zeros(shape, dtype=np.float32),
        resolvable_mask=res_mask,
        unresolved_mask=unres_mask,
        is_attribution_ambiguous=np.zeros(shape, dtype=bool),
        mean_observability=0.90,
        mean_attribution_ambiguity=0.0,
        resolvable_fraction=1.0,
        unresolved_fraction=0.0,
        mean_telemetry_factor=1.0,
        mean_cloud_factor=1.0,
        mean_canopy_factor=1.0,
        mean_irrigation_buffering=0.0,
        mean_harvest_confound=0.0,
        provenance_hash="TEST_OBS",
    )

    dec = classify_tristate_drought(ev, obs)

    assert dec.total_pixels == 400
    assert dec.drought_pixels == 100
    assert dec.no_drought_pixels == 300
    assert dec.unresolved_pixels == 0


def test_inadequate_evidence_becomes_unresolved():
    # If stress is low, but modalities are unverified / missing (e.g. only 1 modality verified normal),
    # system must declare UNRESOLVED, never assuming NO_DROUGHT blindly.
    shape = (10, 10)
    ev_unverified = DroughtEvidenceBreakdown(
        vegetation_stress_score=np.full(shape, 0.10, dtype=np.float32),  # 1 normal
        precipitation_deficit_score=np.full(shape, 0.45, dtype=np.float32), # missing/elevated
        soil_moisture_deficit_score=np.full(shape, 0.45, dtype=np.float32), # missing/elevated
        thermal_stress_score=np.full(shape, 0.45, dtype=np.float32),
        fused_drought_score=np.full(shape, 0.25, dtype=np.float32),       # fused score is low
        modality_weights_applied=None,
        provenance_hash="TEST_UNVERIFIED",
    )

    obs = DroughtObservabilityResult(
        observability_index=np.ones(shape, dtype=np.float32),
        attribution_ambiguity_index=np.zeros(shape, dtype=np.float32),
        resolvable_mask=np.ones(shape, dtype=bool),
        unresolved_mask=np.zeros(shape, dtype=bool),
        is_attribution_ambiguous=np.zeros(shape, dtype=bool),
        mean_observability=1.0,
        mean_attribution_ambiguity=0.0,
        resolvable_fraction=1.0,
        unresolved_fraction=0.0,
        mean_telemetry_factor=1.0,
        mean_cloud_factor=1.0,
        mean_canopy_factor=1.0,
        mean_irrigation_buffering=0.0,
        mean_harvest_confound=0.0,
        provenance_hash="TEST_OBS",
    )

    dec = classify_tristate_drought(ev_unverified, obs)
    # Because only 1 modality is verified normal (<2 required), it becomes UNRESOLVED
    assert dec.drought_pixels == 0
    assert dec.no_drought_pixels == 0
    assert dec.unresolved_pixels == 100
