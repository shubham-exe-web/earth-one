import numpy as np
from earth_one.drought.data_sources import (
    Sentinel2L2AGranule,
    PrecipitationRasterObservation,
    SoilMoistureRasterObservation,
    ThermalLSTObservation,
    RealEODroughtSceneStack,
)
from earth_one.drought.reference_taxonomy import DroughtReferenceTarget
from earth_one.drought.climatology import HistoricalClimatologyStore
from earth_one.drought.tracking import MultiEpochDroughtTracker
from earth_one.drought.real_data_pipeline import run_real_eo_drought_pipeline


def test_sentinel2_l2a_granule_cloud_masking_and_indices():
    shape = (20, 20)
    b02 = np.full(shape, 0.05, dtype=np.float32)
    b04 = np.full(shape, 0.12, dtype=np.float32)
    b05 = np.full(shape, 0.22, dtype=np.float32)
    b08 = np.full(shape, 0.50, dtype=np.float32)
    b11 = np.full(shape, 0.20, dtype=np.float32)
    
    # SCL layer: 4 = vegetation, 8 = cloud medium probability, 3 = cloud shadow
    scl = np.full(shape, 4, dtype=np.uint8)
    scl[0:5, 0:5] = 8   # 25 cloud pixels
    scl[0:5, 5:10] = 3  # 25 shadow pixels

    granule = Sentinel2L2AGranule(
        granule_id="S2A_MSIL2A_20220715T163841_N0400_R083_T15TVK",
        acquisition_timestamp="2022-07-15T16:38:41Z",
        native_crs="EPSG:32615",
        transform=(400000.0, 20.0, 0.0, 4600000.0, 0.0, -20.0),
        resolution_m=20.0,
        b02_blue=b02,
        b04_red=b04,
        b05_red_edge=b05,
        b08_nir=b08,
        b11_swir1=b11,
        scl_classification=scl,
    )

    indices = granule.compute_indices()
    assert indices["ndvi"].shape == shape
    assert np.sum(indices["cloud_mask"]) == 50
    assert np.sum(indices["valid_mask"]) == (400 - 50)
    assert np.isnan(indices["ndvi"][0, 0])  # Masked pixel is NaN
    assert np.isclose(float(indices["ndvi"][10, 10]), (0.50 - 0.12) / (0.50 + 0.12))


def test_drought_reference_taxonomy():
    shape = (10, 10)
    # Ordinal grid: D0=1, D1=2, D2=3, D3=4, D4=5
    ordinal_grid = np.zeros(shape, dtype=np.uint8)
    ordinal_grid[0:5, :] = 3  # D2 Severe Drought
    ordinal_grid[5:10, :] = 1 # D0 Abnormally Dry

    ref_target = DroughtReferenceTarget(
        name="USDM_IOWA_20220715",
        role="COMPETING_OPERATIONAL_PRODUCT",
        format_type="ORDINAL_SEVERITY",
        source_agency="NDMC_USDA_NOAA",
        temporal_coverage="2022-07",
        spatial_resolution_m=1000.0,
        ordinal_grid=ordinal_grid,
    )

    # D2+ threshold (>=3)
    eval_mask = ref_target.get_eval_binary_mask(ordinal_threshold=3)
    assert np.sum(eval_mask) == 50
    assert np.all(eval_mask[0:5, :])
    assert not np.any(eval_mask[5:10, :])


def test_real_eo_drought_pipeline_end_to_end():
    shape = (32, 32)
    eval_year = 2022
    eval_month = 7
    years = [2017, 2018, 2019, 2020, 2021, 2022]

    # 1. Historical Climatology Stores with strict 2022 exclusion
    store_v1 = HistoricalClimatologyStore("ndvi_1m")
    store_v3 = HistoricalClimatologyStore("ndvi_3m")
    store_v6 = HistoricalClimatologyStore("ndvi_6m")
    store_p1 = HistoricalClimatologyStore("precip_1m")
    store_p3 = HistoricalClimatologyStore("precip_3m")
    store_p6 = HistoricalClimatologyStore("precip_6m")
    store_ss = HistoricalClimatologyStore("sm_surf")
    store_srz = HistoricalClimatologyStore("sm_rz")
    store_t = HistoricalClimatologyStore("lst_k")

    np.random.seed(42)
    hist_v = np.random.normal(0.70, 0.05, (len(years), shape[0], shape[1])).astype(np.float32)
    hist_p = np.random.normal(90.0, 20.0, (len(years), shape[0], shape[1])).astype(np.float32)
    hist_s = np.random.normal(0.30, 0.04, (len(years), shape[0], shape[1])).astype(np.float32)
    hist_t = np.random.normal(298.0, 3.0, (len(years), shape[0], shape[1])).astype(np.float32)

    store_v1.fit_from_historical_stack(eval_month, hist_v, year_labels=years, excluded_years=[eval_year])
    store_v3.fit_from_historical_stack(eval_month, hist_v, year_labels=years, excluded_years=[eval_year])
    store_v6.fit_from_historical_stack(eval_month, hist_v, year_labels=years, excluded_years=[eval_year])

    store_p1.fit_from_historical_stack(eval_month, hist_p, year_labels=years, excluded_years=[eval_year])
    store_p3.fit_from_historical_stack(eval_month, hist_p * 3.0, year_labels=years, excluded_years=[eval_year])
    store_p6.fit_from_historical_stack(eval_month, hist_p * 6.0, year_labels=years, excluded_years=[eval_year])

    store_ss.fit_from_historical_stack(eval_month, hist_s, year_labels=years, excluded_years=[eval_year])
    store_srz.fit_from_historical_stack(eval_month, hist_s * 1.05, year_labels=years, excluded_years=[eval_year])
    store_t.fit_from_historical_stack(eval_month, hist_t, year_labels=years, excluded_years=[eval_year])

    # 2. Construct Real EO Scene Stack for Iowa 2022 (Severe agricultural drought)
    b02 = np.full(shape, 0.06, dtype=np.float32)
    b04 = np.full(shape, 0.20, dtype=np.float32)  # High red = lower NDVI ~0.43 (severe drop from 0.70)
    b05 = np.full(shape, 0.25, dtype=np.float32)
    b08 = np.full(shape, 0.50, dtype=np.float32)
    b11 = np.full(shape, 0.28, dtype=np.float32)
    scl = np.full(shape, 4, dtype=np.uint8)  # Vegetation class

    opt = Sentinel2L2AGranule(
        granule_id="S2B_MSIL2A_20220722_IOWA",
        acquisition_timestamp="2022-07-22T16:40:00Z",
        native_crs="EPSG:32615",
        transform=(400000.0, 20.0, 0.0, 4600000.0, 0.0, -20.0),
        resolution_m=20.0,
        b02_blue=b02,
        b04_red=b04,
        b05_red_edge=b05,
        b08_nir=b08,
        b11_swir1=b11,
        scl_classification=scl,
    )

    precip = PrecipitationRasterObservation(
        product_name="GPM_IMERG_FINAL_V06B",
        timestamp="2022-07-22T00:00:00Z",
        precip_1m_mm=np.full(shape, 25.0, dtype=np.float32),   # Severe deficit
        precip_3m_mm=np.full(shape, 110.0, dtype=np.float32),  # Severe deficit
        precip_6m_mm=np.full(shape, 280.0, dtype=np.float32),
        provenance_hash="PR_GPM",
    )

    sm = SoilMoistureRasterObservation(
        product_name="SMAP_L3_SM_P",
        timestamp="2022-07-22T06:00:00Z",
        surface_sm_m3m3=np.full(shape, 0.14, dtype=np.float32), # Severe deficit (0.14 vs 0.30)
        rootzone_sm_m3m3=np.full(shape, 0.16, dtype=np.float32),
        provenance_hash="SM_SMAP",
    )

    th = ThermalLSTObservation(
        product_name="MODIS_MOD11A1_LST",
        timestamp="2022-07-22T13:30:00Z",
        lst_kelvin=np.full(shape, 304.0, dtype=np.float32),     # Elevated heat (+6K)
        provenance_hash="TH_MODIS",
    )

    from earth_one.drought.spatial_harmonization import TargetAnalysisGrid
    target_grid = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, 20.0, 0.0, 4600000.0, 0.0, -20.0),
        width=shape[1],
        height=shape[0],
        pixel_size_x_m=20.0,
        pixel_size_y_m=-20.0,
    )

    scene_stack = RealEODroughtSceneStack(
        aoi_id="AOI_IOWA_CORN_BELT",
        epoch_timestamp="2022-07-22T16:40:00Z",
        target_grid=target_grid,
        optical=opt,
        precipitation=precip,
        soil_moisture=sm,
        thermal=th,
        provenance_hash="STACK_IOWA_2022",
    )

    # 3. Independent Reference Target
    ref = DroughtReferenceTarget(
        name="USDM_IOWA_20220722",
        role="COMPETING_OPERATIONAL_PRODUCT",
        format_type="BINARY_MASK",
        source_agency="NDMC",
        temporal_coverage="2022-07",
        spatial_resolution_m=1000.0,
        binary_mask=np.ones(shape, dtype=bool),
    )

    tracker = MultiEpochDroughtTracker()
    res = run_real_eo_drought_pipeline(
        scene_stack=scene_stack,
        climatology_store_veg_1m=store_v1,
        climatology_store_veg_3m=store_v3,
        climatology_store_veg_6m=store_v6,
        climatology_store_precip_1m=store_p1,
        climatology_store_precip_3m=store_p3,
        climatology_store_precip_6m=store_p6,
        climatology_store_sm_surf=store_ss,
        climatology_store_sm_rz=store_srz,
        climatology_store_lst=store_t,
        eval_month=eval_month,
        eval_year=eval_year,
        tracker=tracker,
        epoch_index=1,
        reference_target=ref,
    )

    assert res.aoi_id == "AOI_IOWA_CORN_BELT"
    assert res.decision.drought_pixels > 0
    assert res.validation_metrics is not None
    assert res.validation_metrics.f1_score >= 0.85
    assert len(res.active_tracks) >= 1
    assert len(res.provenance_hash) == 64
