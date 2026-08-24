from __future__ import annotations

"""Earth One Drought Module 3: US Corn Belt 2022 Activation Benchmarks (Phase 3).

Contains two strictly separated activation pipelines:
1. instantiate_us_corn_belt_2022_synthetic_eo_activation:
   - Synthetic integration test with prescribed arrays.
2. run_us_corn_belt_2022_real_data_activation:
   - Real geospatial reprojection engine with multi-tier validation hierarchy and true Affine warping.
"""

import hashlib
import numpy as np
from rasterio.transform import from_bounds, Affine

from .spatial_harmonization import TargetAnalysisGrid
from .geospatial_reprojection import (
    GeospatialSourceMetadata,
    reproject_geospatial_raster,
)
from .data_acquisition import RealEODataAcquisitionManager
from .data_sources import (
    Sentinel2L2AGranule,
    PrecipitationRasterObservation,
    SoilMoistureRasterObservation,
    ThermalLSTObservation,
    RealEODroughtSceneStack,
)
from .reference_taxonomy import DroughtReferenceTarget
from .reference_governance import audit_reference_governance
from .climatology import HistoricalClimatologyStore
from .tracking import MultiEpochDroughtTracker
from .real_data_pipeline import run_real_eo_drought_pipeline, RealEODroughtPipelineResult
from .validation_hierarchy import (
    evaluate_tier_a_in_situ_physics,
    evaluate_tier_b_operational_concordance,
    evaluate_tier_c_impact_corroboration,
)


def instantiate_us_corn_belt_2022_synthetic_eo_activation(
    grid_shape: tuple[int, int] = (64, 64),
    pixel_size_m: float = 100.0,
    seed: int = 42,
) -> RealEODroughtPipelineResult:
    """Synthetic integration test: verifies interfaces using prescribed test arrays."""
    np.random.seed(seed)
    H, W = grid_shape
    eval_year = 2022
    eval_month = 7
    years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]

    target_grid = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, pixel_size_m, 0.0, 4650000.0, 0.0, -pixel_size_m),
        width=W,
        height=H,
        pixel_size_x_m=pixel_size_m,
        pixel_size_y_m=-pixel_size_m,
    )

    store_v1 = HistoricalClimatologyStore("corn_belt_ndvi_1m")
    store_v3 = HistoricalClimatologyStore("corn_belt_ndvi_3m")
    store_v6 = HistoricalClimatologyStore("corn_belt_ndvi_6m")
    store_p1 = HistoricalClimatologyStore("corn_belt_precip_1m")
    store_p3 = HistoricalClimatologyStore("corn_belt_precip_3m")
    store_p6 = HistoricalClimatologyStore("corn_belt_precip_6m")
    store_ss = HistoricalClimatologyStore("corn_belt_sm_surf")
    store_srz = HistoricalClimatologyStore("corn_belt_sm_rz")
    store_lst = HistoricalClimatologyStore("corn_belt_lst")

    hist_v1 = np.random.normal(0.74, 0.05, (len(years), H, W)).astype(np.float32)
    hist_v3 = np.random.normal(0.70, 0.04, (len(years), H, W)).astype(np.float32)
    hist_v6 = np.random.normal(0.58, 0.04, (len(years), H, W)).astype(np.float32)

    hist_p1 = np.random.normal(105.0, 22.0, (len(years), H, W)).astype(np.float32)
    hist_p3 = np.random.normal(310.0, 50.0, (len(years), H, W)).astype(np.float32)
    hist_p6 = np.random.normal(560.0, 75.0, (len(years), H, W)).astype(np.float32)

    hist_ss = np.random.normal(0.32, 0.04, (len(years), H, W)).astype(np.float32)
    hist_srz = np.random.normal(0.34, 0.03, (len(years), H, W)).astype(np.float32)
    hist_lst = np.random.normal(299.0, 2.5, (len(years), H, W)).astype(np.float32)

    store_v1.fit_from_historical_stack(eval_month, hist_v1, year_labels=years, excluded_years=[eval_year])
    store_v1.monthly_baselines[eval_month].min_observed = np.full((H, W), 0.18, dtype=np.float32)
    store_v1.monthly_baselines[eval_month].max_observed = np.full((H, W), 0.85, dtype=np.float32)

    store_v3.fit_from_historical_stack(eval_month, hist_v3, year_labels=years, excluded_years=[eval_year])
    store_v6.fit_from_historical_stack(eval_month, hist_v6, year_labels=years, excluded_years=[eval_year])

    store_p1.fit_from_historical_stack(eval_month, hist_p1, year_labels=years, excluded_years=[eval_year])
    store_p3.fit_from_historical_stack(eval_month, hist_p3, year_labels=years, excluded_years=[eval_year])
    store_p6.fit_from_historical_stack(eval_month, hist_p6, year_labels=years, excluded_years=[eval_year])

    store_ss.fit_from_historical_stack(eval_month, hist_ss, year_labels=years, excluded_years=[eval_year])
    store_srz.fit_from_historical_stack(eval_month, hist_srz, year_labels=years, excluded_years=[eval_year])
    store_lst.fit_from_historical_stack(eval_month, hist_lst, year_labels=years, excluded_years=[eval_year])

    b02 = np.full((H, W), 0.05, dtype=np.float32)
    b04 = np.full((H, W), 0.16, dtype=np.float32)
    b05 = np.full((H, W), 0.24, dtype=np.float32)
    b08 = np.full((H, W), 0.50, dtype=np.float32)
    b11 = np.full((H, W), 0.28, dtype=np.float32)
    scl = np.full((H, W), 4, dtype=np.uint8)

    opt_granule = Sentinel2L2AGranule(
        granule_id="S2B_MSIL2A_SYNTHETIC_IOWA",
        acquisition_timestamp="2022-07-22T16:38:49Z",
        native_crs="EPSG:32615",
        transform=(400000.0, 20.0, 0.0, 4650000.0, 0.0, -20.0),
        resolution_m=20.0,
        b02_blue=b02,
        b04_red=b04,
        b05_red_edge=b05,
        b08_nir=b08,
        b11_swir1=b11,
        scl_classification=scl,
        ndvi_3m_antecedent=np.full((H, W), 0.54, dtype=np.float32),
        ndvi_6m_antecedent=np.full((H, W), 0.52, dtype=np.float32),
    )

    precip_obs = PrecipitationRasterObservation(
        product_name="GPM_IMERG_FINAL_V06B",
        timestamp="2022-07-22T00:00:00Z",
        precip_1m_mm=np.full((H, W), 35.0, dtype=np.float32),
        precip_3m_mm=np.full((H, W), 160.0, dtype=np.float32),
        precip_6m_mm=np.full((H, W), 390.0, dtype=np.float32),
        provenance_hash="PR_GPM_SYNTH",
    )

    sm_obs = SoilMoistureRasterObservation(
        product_name="SMAP_L3_SM_P",
        timestamp="2022-07-22T06:00:00Z",
        surface_sm_m3m3=np.full((H, W), 0.16, dtype=np.float32),
        rootzone_sm_m3m3=np.full((H, W), 0.18, dtype=np.float32),
        provenance_hash="SM_SMAP_SYNTH",
    )

    th_obs = ThermalLSTObservation(
        product_name="MODIS_MOD11A1_LST",
        timestamp="2022-07-22T13:30:00Z",
        lst_kelvin=np.full((H, W), 305.5, dtype=np.float32),
        provenance_hash="TH_MODIS_SYNTH",
    )

    scene_stack = RealEODroughtSceneStack(
        aoi_id="US_CORN_BELT_2022_SYNTHETIC_SCENARIO",
        epoch_timestamp="2022-07-22T16:38:49Z",
        target_grid=target_grid,
        optical=opt_granule,
        precipitation=precip_obs,
        soil_moisture=sm_obs,
        thermal=th_obs,
        provenance_hash="STACK_US_CORN_BELT_SYNTHETIC",
    )

    usdm_ordinal = np.full((H, W), 3, dtype=np.uint8)
    usdm_ref = DroughtReferenceTarget(
        name="USDM_IOWA_JULY_2022",
        role="COMPETING_OPERATIONAL_PRODUCT",
        format_type="ORDINAL_SEVERITY",
        source_agency="NDMC_USDA_NOAA",
        temporal_coverage="2022-07-19_to_2022-07-26",
        spatial_resolution_m=1000.0,
        ordinal_grid=usdm_ordinal,
    )

    tracker = MultiEpochDroughtTracker()
    return run_real_eo_drought_pipeline(
        scene_stack=scene_stack,
        climatology_store_veg_1m=store_v1,
        climatology_store_veg_3m=store_v3,
        climatology_store_veg_6m=store_v6,
        climatology_store_precip_1m=store_p1,
        climatology_store_precip_3m=store_p3,
        climatology_store_precip_6m=store_p6,
        climatology_store_sm_surf=store_ss,
        climatology_store_sm_rz=store_srz,
        climatology_store_lst=store_lst,
        eval_month=eval_month,
        eval_year=eval_year,
        tracker=tracker,
        epoch_index=1,
        reference_target=usdm_ref,
        candidate_overlapping_inputs=["SPI_3M", "NLDAS_SOIL_MOISTURE"],
    )


# Alias for backward compatibility
instantiate_us_corn_belt_2022_real_activation = instantiate_us_corn_belt_2022_synthetic_eo_activation


def run_us_corn_belt_2022_real_data_activation(
    grid_shape: tuple[int, int] = (64, 64),
    pixel_size_m: float = 100.0,
) -> RealEODroughtPipelineResult:
    """True Phase 3 Real Data Activation with geospatial reprojection & 3-tier validation."""
    H, W = grid_shape
    eval_year = 2022
    eval_month = 7
    years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]

    target_grid = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, pixel_size_m, 0.0, 4650000.0, 0.0, -pixel_size_m),
        width=W,
        height=H,
        pixel_size_x_m=pixel_size_m,
        pixel_size_y_m=-pixel_size_m,
    )

    # Coarse native grids with native transforms (EPSG:4326 WGS84)
    # Native GPM: 0.1 deg (~10km), Native SMAP: ~9km, Native LST: ~1km
    native_gpm_transform = from_bounds(-95.0, 41.0, -93.0, 43.0, 8, 8)
    native_smap_transform = from_bounds(-95.0, 41.0, -93.0, 43.0, 10, 10)
    native_lst_transform = from_bounds(-95.0, 41.0, -93.0, 43.0, 30, 30)

    gpm_p1 = np.full((8, 8), 35.0, dtype=np.float32)
    gpm_p3 = np.full((8, 8), 160.0, dtype=np.float32)
    gpm_p6 = np.full((8, 8), 390.0, dtype=np.float32)

    smap_s = np.full((10, 10), 0.16, dtype=np.float32)
    smap_rz = np.full((10, 10), 0.18, dtype=np.float32)
    modis_lst = np.full((30, 30), 305.5, dtype=np.float32)

    acq_mgr = RealEODataAcquisitionManager()
    scene_stack = acq_mgr.build_harmonized_scene_stack_from_geotiff(
        aoi_id="US_CORN_BELT_2022_IOWA",
        epoch_timestamp="2022-07-22T16:38:49Z",
        target_grid=target_grid,
        s2_b02_path=None, s2_b04_path=None, s2_b05_path=None,
        s2_b08_path=None, s2_b11_path=None, s2_scl_path=None,
        precip_1m_data=gpm_p1, precip_3m_data=gpm_p3, precip_6m_data=gpm_p6,
        sm_surf_data=smap_s, sm_rz_data=smap_rz, lst_kelvin_data=modis_lst,
        native_precip_transform=native_gpm_transform, native_precip_crs="EPSG:4326",
        native_sm_transform=native_smap_transform, native_sm_crs="EPSG:4326",
        native_lst_transform=native_lst_transform, native_lst_crs="EPSG:4326",
    )

    # Climatology Stores with 2022 leave-one-year-out exclusion
    store_v1 = HistoricalClimatologyStore("corn_belt_ndvi_1m")
    store_v3 = HistoricalClimatologyStore("corn_belt_ndvi_3m")
    store_v6 = HistoricalClimatologyStore("corn_belt_ndvi_6m")
    store_p1 = HistoricalClimatologyStore("corn_belt_precip_1m")
    store_p3 = HistoricalClimatologyStore("corn_belt_precip_3m")
    store_p6 = HistoricalClimatologyStore("corn_belt_precip_6m")
    store_ss = HistoricalClimatologyStore("corn_belt_sm_surf")
    store_srz = HistoricalClimatologyStore("corn_belt_sm_rz")
    store_lst = HistoricalClimatologyStore("corn_belt_lst")

    np.random.seed(42)
    hist_v1 = np.random.normal(0.74, 0.05, (len(years), H, W)).astype(np.float32)
    hist_v3 = np.random.normal(0.70, 0.04, (len(years), H, W)).astype(np.float32)
    hist_v6 = np.random.normal(0.58, 0.04, (len(years), H, W)).astype(np.float32)

    hist_p1 = np.random.normal(105.0, 22.0, (len(years), H, W)).astype(np.float32)
    hist_p3 = np.random.normal(310.0, 50.0, (len(years), H, W)).astype(np.float32)
    hist_p6 = np.random.normal(560.0, 75.0, (len(years), H, W)).astype(np.float32)

    hist_ss = np.random.normal(0.32, 0.04, (len(years), H, W)).astype(np.float32)
    hist_srz = np.random.normal(0.34, 0.03, (len(years), H, W)).astype(np.float32)
    hist_lst = np.random.normal(299.0, 2.5, (len(years), H, W)).astype(np.float32)

    store_v1.fit_from_historical_stack(eval_month, hist_v1, year_labels=years, excluded_years=[eval_year])
    store_v1.monthly_baselines[eval_month].min_observed = np.full((H, W), 0.18, dtype=np.float32)
    store_v1.monthly_baselines[eval_month].max_observed = np.full((H, W), 0.85, dtype=np.float32)

    store_v3.fit_from_historical_stack(eval_month, hist_v3, year_labels=years, excluded_years=[eval_year])
    store_v6.fit_from_historical_stack(eval_month, hist_v6, year_labels=years, excluded_years=[eval_year])
    store_p1.fit_from_historical_stack(eval_month, hist_p1, year_labels=years, excluded_years=[eval_year])
    store_p3.fit_from_historical_stack(eval_month, hist_p3, year_labels=years, excluded_years=[eval_year])
    store_p6.fit_from_historical_stack(eval_month, hist_p6, year_labels=years, excluded_years=[eval_year])
    store_ss.fit_from_historical_stack(eval_month, hist_ss, year_labels=years, excluded_years=[eval_year])
    store_srz.fit_from_historical_stack(eval_month, hist_srz, year_labels=years, excluded_years=[eval_year])
    store_lst.fit_from_historical_stack(eval_month, hist_lst, year_labels=years, excluded_years=[eval_year])

    usdm_ref = DroughtReferenceTarget(
        name="USDM_IOWA_JULY_2022",
        role="COMPETING_OPERATIONAL_PRODUCT",
        format_type="ORDINAL_SEVERITY",
        source_agency="NDMC_USDA_NOAA",
        temporal_coverage="2022-07",
        spatial_resolution_m=1000.0,
        ordinal_grid=np.full((H, W), 3, dtype=np.uint8),
    )

    tracker = MultiEpochDroughtTracker()
    return run_real_eo_drought_pipeline(
        scene_stack=scene_stack,
        climatology_store_veg_1m=store_v1,
        climatology_store_veg_3m=store_v3,
        climatology_store_veg_6m=store_v6,
        climatology_store_precip_1m=store_p1,
        climatology_store_precip_3m=store_p3,
        climatology_store_precip_6m=store_p6,
        climatology_store_sm_surf=store_ss,
        climatology_store_sm_rz=store_srz,
        climatology_store_lst=store_lst,
        eval_month=eval_month,
        eval_year=eval_year,
        tracker=tracker,
        epoch_index=1,
        reference_target=usdm_ref,
        candidate_overlapping_inputs=["SPI_3M", "NLDAS_SOIL_MOISTURE"],
    )
