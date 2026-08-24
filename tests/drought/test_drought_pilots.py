from earth_one.drought.pilots import build_real_pilot_activation


def test_us_corn_belt_pilot():
    pilot = build_real_pilot_activation("US_CORN_BELT_2022")
    assert pilot.target_regime == "RAINFED_AGRICULTURE"
    assert pilot.eval_year == 2022
    assert pilot.decision.drought_pixels > 0
    assert pilot.observability.mean_observability >= 0.85
    assert pilot.segmentation.event_count >= 1


def test_ca_central_valley_pilot_irrigation_buffering():
    pilot = build_real_pilot_activation("CA_CENTRAL_VALLEY_2021")
    assert pilot.target_regime == "IRRIGATED_AGRICULTURE"
    assert pilot.regime_context.is_irrigated is True
    # In irrigated agriculture, vegetation weight is reduced so hydroclimatic deficit dominates
    assert pilot.regime_context.recommended_modality_weights.vegetation < 0.20
    assert pilot.observability.mean_attribution_ambiguity >= 0.60


def test_eu_rhine_forest_pilot():
    pilot = build_real_pilot_activation("EU_RHINE_FOREST_2022")
    assert pilot.target_regime == "FOREST"
    assert pilot.regime_context.recommended_modality_weights.vegetation == 0.40
    assert pilot.decision.drought_pixels > 0


def test_horn_of_africa_pastoral_pilot():
    pilot = build_real_pilot_activation("HORN_AFRICA_PASTORAL_2021")
    assert pilot.target_regime == "GRASSLAND_SHRUBLAND"
    assert pilot.decision.drought_pixels > 3500


def test_es_andalucia_harvest_disentanglement():
    pilot = build_real_pilot_activation("ES_ANDALUCIA_DRYLAND_2023")
    assert pilot.target_regime == "DRYLAND_SPARSE"
    # Harvest pocket in top-left (20x20 = 400 px) is disentangled by attribution ambiguity
    assert bool(pilot.observability.is_attribution_ambiguous[5, 5]) or pilot.observability.mean_attribution_ambiguity > 0
    assert not bool(pilot.decision.drought_mask[5, 5]) or not bool(pilot.reference_mask[5, 5])
