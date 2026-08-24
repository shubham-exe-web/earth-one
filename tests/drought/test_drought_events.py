import numpy as np
from earth_one.drought.classifier import TriStateDroughtDecision
from earth_one.drought.observability import DroughtObservabilityResult
from earth_one.drought.events import extract_drought_events


def test_drought_event_segmentation_with_geospatial_resolution():
    shape = (50, 50)
    drought_mask = np.zeros(shape, dtype=bool)
    drought_mask[10:30, 10:30] = True  # 20x20 = 400 px

    fused_score = np.full(shape, 0.20, dtype=np.float32)
    fused_score[10:30, 10:30] = 0.75

    obs_idx = np.full(shape, 0.90, dtype=np.float32)
    res_mask = np.ones(shape, dtype=bool)

    dec = TriStateDroughtDecision(
        drought_mask=drought_mask,
        no_drought_mask=~drought_mask,
        unresolved_mask=np.zeros(shape, dtype=bool),
        resolvable_mask=res_mask,
        total_pixels=2500,
        drought_pixels=400,
        no_drought_pixels=2100,
        unresolved_pixels=0,
        drought_fraction=0.16,
        unresolved_fraction=0.0,
        provenance_hash="TEST_DEC",
    )

    obs = DroughtObservabilityResult(
        observability_index=obs_idx,
        attribution_ambiguity_index=np.zeros(shape, dtype=np.float32),
        resolvable_mask=res_mask,
        unresolved_mask=~res_mask,
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

    # Test with 30m Landsat resolution (30m*30m = 0.09 ha/pixel)
    res_30m = extract_drought_events(dec, fused_score, obs, resolution_m=30.0)
    assert res_30m.pixel_area_ha == 0.09
    assert res_30m.total_drought_area_ha == 400 * 0.09  # 36.0 ha

    ev = res_30m.events[0]
    assert ev.area_expected_ha == 36.0
    assert ev.area_sensitivity_low_ha <= ev.area_expected_ha <= ev.area_sensitivity_high_ha
    assert ev.is_well_observed is True
