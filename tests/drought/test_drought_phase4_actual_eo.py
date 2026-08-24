import numpy as np
from earth_one.drought.data_manifest import SensorSupportMetadata, DroughtActivationManifest, ReferenceIndependenceRecord
from earth_one.drought.temporal_compositor import compute_true_rolling_composites
from earth_one.drought.us_corn_belt_activation import run_us_corn_belt_2022_actual_eo_activation


def test_drought_manifest_and_support_metadata():
    support_s2 = SensorSupportMetadata(
        sensor_name="Sentinel-2_MSI",
        product_id="S2B_MSIL2A_20220722T163849",
        native_crs="EPSG:32615",
        native_resolution_m=20.0,
        effective_spatial_support_m=20.0,
        analysis_grid_resolution_m=100.0,
        temporal_frequency="5-day",
        qa_filtering_applied="SCL_QA_CLEAN",
    )
    assert support_s2.resolution_disparity_ratio == 0.20

    support_gpm = SensorSupportMetadata(
        sensor_name="GPM_IMERG_FINAL",
        product_id="3B-HHR.MS.MRG.3IMERG.202207",
        native_crs="EPSG:4326",
        native_resolution_m=10000.0,
        effective_spatial_support_m=10000.0,
        analysis_grid_resolution_m=100.0,
        temporal_frequency="Monthly",
        qa_filtering_applied="NASA_QA_GOOD",
    )
    assert support_gpm.resolution_disparity_ratio == 100.0  # 10km support on 100m grid!

    independence = [
        ReferenceIndependenceRecord("USDM", "NDMC", False, True, "TIER_B_OPERATIONAL", False, ["SPI_3M"]),
    ]

    from earth_one.drought.data_manifest import ExecutionArchiveMode
    manifest = DroughtActivationManifest(
        aoi_id="US_CORN_BELT_2022",
        archive_mode=ExecutionArchiveMode.DISK_BACKED_SYNTHETIC,
        target_crs="EPSG:32615",
        target_resolution_m=100.0,
        target_transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        target_shape=(64, 64),
        eval_year=2022,
        eval_month=7,
        climatology_baseline_years=[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2023],
        excluded_years=[2022],
        optical_scene_ids=["S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK"],
        precipitation_product="GPM_IMERG_FINAL_V06B",
        soil_moisture_product="SMAP_L3_SM_P_008",
        thermal_lst_product="MOD11A1.061",
        operational_comparator_id="USDM_20220726",
        in_situ_station_ids=["USCRN_IA_DES_MOINES_17_E"],
        impact_dataset_id="USDA_RMA_INDEMNITIES_2022",
        sensor_supports={"sentinel2": support_s2, "precipitation": support_gpm},
        independence_matrix=independence,
        software_commit="Phase4_Release",
    )
    h = manifest.compute_sha256()
    assert len(h) == 64


def test_true_rolling_temporal_composites():
    # 12 chronological 2-week scenes over 6 months for a 10x10 region
    shape = (12, 10, 10)
    np.random.seed(42)
    # Seasonal cycle: winter low (0.30) to summer peak (0.75) with July drought drop (0.50)
    base_trend = np.linspace(0.30, 0.75, 12)[:, None, None]
    ndvi_scenes = np.random.normal(base_trend, 0.03, shape).astype(np.float32)
    ndvi_scenes[-2:] -= 0.20  # Flash drought drop in July
    valid_scenes = np.ones(shape, dtype=bool)

    res = compute_true_rolling_composites(
        chronological_ndvi_stack=ndvi_scenes,
        chronological_valid_stack=valid_scenes,
        window_1m_slice=slice(-2, None),
        window_3m_slice=slice(-6, None),
        window_6m_slice=slice(-12, None),
    )

    assert res.ndvi_1m_current.shape == (10, 10)
    assert res.ndvi_3m_rolling.shape == (10, 10)
    assert res.ndvi_6m_rolling.shape == (10, 10)
    # Distinct rolling means across temporal windows!
    assert not np.allclose(res.ndvi_1m_current, res.ndvi_3m_rolling)
    assert not np.allclose(res.ndvi_3m_rolling, res.ndvi_6m_rolling)
    assert np.mean(res.clear_observation_count_1m) == 2
    assert np.mean(res.clear_observation_count_3m) == 6
    assert np.mean(res.clear_observation_count_6m) == 12


def test_us_corn_belt_actual_eo_pipeline_end_to_end():
    result = run_us_corn_belt_2022_actual_eo_activation(grid_shape=(32, 32), pixel_size_m=100.0)

    # 1. Manifest & Provenance check
    assert result.manifest.aoi_id == "US_CORN_BELT_IOWA_2022"
    assert result.manifest.excluded_years == [2022]
    assert 2022 not in result.manifest.climatology_baseline_years
    assert len(result.provenance_hash) == 64

    # 2. Decision & segmentation
    assert result.decision.drought_pixels > 0
    assert result.segmentation.event_count >= 1
    assert len(result.active_tracks) >= 1

    # 3. Tier A: In-situ Physical Validation (USCRN soil moisture probe)
    assert result.tier_a_metrics is not None
    assert result.tier_a_metrics.rmse < 0.05

    # 4. Tier B: Operational Comparator Concordance (USDM)
    assert result.tier_b_metrics is not None
    assert result.tier_b_metrics.spatial_concordance_f1 >= 0.85
    assert "operational agreement" in result.tier_b_metrics.scientific_disclaimer.lower()
    assert "SPI_3M" in result.tier_b_metrics.overlapping_inputs_disclosed

    # 5. Tier C: Impact Corroboration (USDA RMA Yield Loss)
    assert result.tier_c_metrics is not None
    assert result.tier_c_metrics.is_pixel_truth_prohibited is True
