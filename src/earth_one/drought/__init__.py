"""Earth One Module 3: Autonomous Multimodal Drought Intelligence Engine (v0.11.0 Engineering Baseline)."""

from .config import (
    DroughtConfig,
    DroughtRegimeType,
    DroughtLifecycleState,
    TriStateDroughtLabel,
    TemporalWindowWeights,
    ModalityWeights,
)
from .features import (
    DroughtFeatureRecord,
    OpticalVegetationFeatures,
    HydroclimaticFeatures,
    compute_ndvi,
    compute_evi,
    compute_ndre,
    compute_ndwi,
    extract_optical_features,
)
from .spatial_harmonization import (
    TargetAnalysisGrid,
    HarmonizedRasterLayer,
    resample_raster_to_grid,
    harmonize_sensor_layer,
)
from .geospatial_reprojection import (
    ScientificResamplingContract,
    GeospatialSourceMetadata,
    ReprojectedRasterResult,
    reproject_geospatial_raster,
)
from .temporal_compositor import (
    MultiTemporalCompositeResult,
    compute_true_rolling_composites,
)
from .data_manifest import (
    ExecutionArchiveMode,
    SensorSupportMetadata,
    ReferenceIndependenceRecord,
    DroughtActivationManifest,
)
from .data_staging import (
    compute_file_sha256,
    write_geotiff_raster,
    stage_us_corn_belt_2022_real_data_archive,
)
from .data_sources import (
    Sentinel2L2AGranule,
    PrecipitationRasterObservation,
    SoilMoistureRasterObservation,
    ThermalLSTObservation,
    RealEODroughtSceneStack,
)
from .data_acquisition import (
    STACGranuleQuery,
    RealEODataAcquisitionManager,
    read_geotiff_with_metadata,
)
from .external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    RealEOAssetVerificationRecord,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    SCLQualityDistribution,
    compute_scl_quality_distribution,
    reproject_bounding_box,
    compute_bounding_box_coverage_fraction,
    compute_bounding_box_overlap_fraction,
    format_execution_provenance_summary,
)
from .reference_taxonomy import (
    ReferenceRole,
    ReferenceFormat,
    DroughtReferenceTarget,
)
from .reference_governance import (
    ValidationGovernanceAudit,
    audit_reference_governance,
)
from .validation_hierarchy import (
    TierAPhysicalValidationMetrics,
    TierBOperationalConcordanceMetrics,
    TierCImpactCorroborationMetrics,
    evaluate_tier_a_in_situ_physics,
    evaluate_tier_b_operational_concordance,
    evaluate_tier_c_impact_corroboration,
)
from .climatology import (
    BaselineClimatology,
    HistoricalClimatologyStore,
    compute_standardized_anomaly,
    compute_empirical_percentile,
    compute_vegetation_condition_index,
    compute_standardized_precipitation_anomaly,
    build_synthetic_climatology,
)
from .anomalies import (
    MultiWindowAnomalies,
    compute_multiwindow_anomalies,
)
from .regime import (
    RegimeEvidenceContext,
    RegimeClassificationResult,
    classify_drought_regime,
)
from .observability import (
    DroughtObservabilityResult,
    compute_drought_observability,
)
from .fusion import (
    DroughtEvidenceBreakdown,
    fuse_drought_evidence,
    z_to_evidence,
)
from .classifier import (
    TriStateDroughtDecision,
    classify_tristate_drought,
)
from .persistence import (
    PixelPersistenceState,
    update_pixel_lifecycle_state,
    evaluate_temporal_persistence_series,
)
from .events import (
    DroughtEventRecord,
    DroughtSegmentationResult,
    extract_drought_events,
)
from .tracking import (
    DroughtTrack,
    MultiEpochDroughtTracker,
    compute_mask_iou,
)
from .alerting import (
    DroughtAlert,
    DroughtAlertStateMachine,
)
from .synthetic import (
    SyntheticDroughtCase,
    generate_synthetic_benchmark_case,
)
from .pilots import (
    DroughtPilotActivation,
    build_real_pilot_activation,
)
from .evaluation import (
    DroughtBenchmarkMetrics,
    ObservabilityBinResult,
    compute_pr_auc,
    evaluate_drought_mode,
)
from .real_data_pipeline import (
    RealEODroughtPipelineResult,
    run_real_eo_drought_pipeline,
)
from .actual_eo_pipeline import (
    ActualEODroughtExperimentResult,
    run_actual_eo_drought_pipeline,
)
from .us_corn_belt_activation import (
    run_drought_activation,
    instantiate_us_corn_belt_2022_synthetic_eo_activation,
    run_us_corn_belt_2022_geospatial_synthetic_activation,
    run_us_corn_belt_2022_disk_backed_synthetic_activation,
    run_us_corn_belt_2022_real_observation_activation,
    run_us_corn_belt_2022_actual_eo_activation,
    instantiate_us_corn_belt_2022_real_activation,
    run_us_corn_belt_2022_real_data_activation,
)

__all__ = [
    "DroughtConfig",
    "DroughtRegimeType",
    "DroughtLifecycleState",
    "TriStateDroughtLabel",
    "TemporalWindowWeights",
    "ModalityWeights",
    "DroughtFeatureRecord",
    "OpticalVegetationFeatures",
    "HydroclimaticFeatures",
    "TargetAnalysisGrid",
    "HarmonizedRasterLayer",
    "resample_raster_to_grid",
    "harmonize_sensor_layer",
    "ScientificResamplingContract",
    "GeospatialSourceMetadata",
    "ReprojectedRasterResult",
    "reproject_geospatial_raster",
    "MultiTemporalCompositeResult",
    "compute_true_rolling_composites",
    "ExecutionArchiveMode",
    "SensorSupportMetadata",
    "ReferenceIndependenceRecord",
    "DroughtActivationManifest",
    "compute_file_sha256",
    "write_geotiff_raster",
    "stage_us_corn_belt_2022_real_data_archive",
    "Sentinel2L2AGranule",
    "PrecipitationRasterObservation",
    "SoilMoistureRasterObservation",
    "ThermalLSTObservation",
    "RealEODroughtSceneStack",
    "STACGranuleQuery",
    "RealEODataAcquisitionManager",
    "read_geotiff_with_metadata",
    "AssetOriginType",
    "STACCatalogItemDeclaration",
    "RealEOAssetVerificationRecord",
    "ExternalSatelliteAcquisitionSession",
    "STACDiscoveryEngine",
    "SCLQualityDistribution",
    "compute_scl_quality_distribution",
    "reproject_bounding_box",
    "compute_bounding_box_coverage_fraction",
    "compute_bounding_box_overlap_fraction",
    "format_execution_provenance_summary",
    "ReferenceRole",
    "ReferenceFormat",
    "DroughtReferenceTarget",
    "ValidationGovernanceAudit",
    "audit_reference_governance",
    "TierAPhysicalValidationMetrics",
    "TierBOperationalConcordanceMetrics",
    "TierCImpactCorroborationMetrics",
    "evaluate_tier_a_in_situ_physics",
    "evaluate_tier_b_operational_concordance",
    "evaluate_tier_c_impact_corroboration",
    "compute_ndvi",
    "compute_evi",
    "compute_ndre",
    "compute_ndwi",
    "extract_optical_features",
    "BaselineClimatology",
    "HistoricalClimatologyStore",
    "compute_standardized_anomaly",
    "compute_empirical_percentile",
    "compute_vegetation_condition_index",
    "compute_standardized_precipitation_anomaly",
    "build_synthetic_climatology",
    "MultiWindowAnomalies",
    "compute_multiwindow_anomalies",
    "RegimeEvidenceContext",
    "RegimeClassificationResult",
    "classify_drought_regime",
    "DroughtObservabilityResult",
    "compute_drought_observability",
    "DroughtEvidenceBreakdown",
    "fuse_drought_evidence",
    "z_to_evidence",
    "TriStateDroughtDecision",
    "classify_tristate_drought",
    "PixelPersistenceState",
    "update_pixel_lifecycle_state",
    "evaluate_temporal_persistence_series",
    "DroughtEventRecord",
    "DroughtSegmentationResult",
    "extract_drought_events",
    "DroughtTrack",
    "MultiEpochDroughtTracker",
    "compute_mask_iou",
    "DroughtAlert",
    "DroughtAlertStateMachine",
    "SyntheticDroughtCase",
    "generate_synthetic_benchmark_case",
    "DroughtPilotActivation",
    "build_real_pilot_activation",
    "DroughtBenchmarkMetrics",
    "ObservabilityBinResult",
    "compute_pr_auc",
    "evaluate_drought_mode",
    "RealEODroughtPipelineResult",
    "run_real_eo_drought_pipeline",
    "ActualEODroughtExperimentResult",
    "run_actual_eo_drought_pipeline",
    "run_drought_activation",
    "instantiate_us_corn_belt_2022_synthetic_eo_activation",
    "run_us_corn_belt_2022_geospatial_synthetic_activation",
    "run_us_corn_belt_2022_disk_backed_synthetic_activation",
    "run_us_corn_belt_2022_real_observation_activation",
    "run_us_corn_belt_2022_actual_eo_activation",
    "instantiate_us_corn_belt_2022_real_activation",
    "run_us_corn_belt_2022_real_data_activation",
]
