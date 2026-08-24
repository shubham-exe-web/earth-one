from earth_one.drought.synthetic import generate_synthetic_benchmark_case


def test_synthetic_case_a_healthy():
    case = generate_synthetic_benchmark_case("CASE_A_HEALTHY")
    assert case.decision.drought_fraction == 0.0
    assert case.decision.unresolved_fraction == 0.0
    assert case.decision.no_drought_pixels == 4096
    assert case.segmentation.event_count == 0


def test_synthetic_case_c_agricultural_drought():
    case = generate_synthetic_benchmark_case("CASE_C_AGRICULTURAL_DROUGHT")
    assert case.decision.drought_fraction > 0.90
    assert case.observability.mean_observability == 1.0
    assert case.segmentation.event_count >= 1
    # Check that multi-window anomalies are distinct
    assert float(case.anomalies.veg_z_1m[0, 0]) != float(case.anomalies.veg_z_3m[0, 0])


def test_synthetic_case_d_irrigation_masked():
    case = generate_synthetic_benchmark_case("CASE_D_IRRIGATION_MASKED")
    assert case.regime_context.regime == "IRRIGATED_AGRICULTURE"
    assert case.observability.mean_attribution_ambiguity >= 0.60
    assert case.observability.mean_observability == 1.0  # Surface is observable


def test_synthetic_case_e_harvest_phenology():
    # In harvest, despite severe 1M NDVI plunge (-3.0z), lack of precipitation/soil moisture deficit
    # and attribution ambiguity prevents false drought declaration
    case = generate_synthetic_benchmark_case("CASE_E_HARVEST_TILLAGE")
    assert case.decision.drought_fraction == 0.0
    assert case.observability.mean_attribution_ambiguity == 0.85


def test_synthetic_case_f_cloud_blackout():
    # 100% cloud cover must transition to UNRESOLVED, not false NO_DROUGHT
    case = generate_synthetic_benchmark_case("CASE_F_CLOUDY_BLACKOUT")
    assert case.decision.unresolved_fraction == 1.0
    assert case.decision.drought_fraction == 0.0
