import numpy as np
from earth_one.drought.reference_taxonomy import DroughtReferenceTarget
from earth_one.drought.validation_hierarchy import (
    evaluate_tier_a_in_situ_physics,
    evaluate_tier_b_operational_concordance,
    evaluate_tier_c_impact_corroboration,
)


def test_tier_a_in_situ_physics_metrics():
    # 10 in-situ soil moisture stations
    true_sm = np.array([0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25, 0.28, 0.32], dtype=np.float32)
    pred_sm = true_sm + np.array([0.01, -0.01, 0.02, 0.00, -0.02, 0.01, -0.01, 0.02, -0.01, 0.00], dtype=np.float32)

    tier_a = evaluate_tier_a_in_situ_physics(pred_sm, true_sm)
    assert tier_a.station_count == 10
    assert tier_a.pearson_r >= 0.95
    assert tier_a.spearman_rho >= 0.95
    assert tier_a.rmse < 0.03


def test_tier_b_operational_concordance_metrics():
    shape = (20, 20)
    y_pred = np.zeros(shape, dtype=bool)
    y_pred[0:15, :] = True  # 300 pixels predicted drought
    fused_score = np.where(y_pred, 0.85, 0.15).astype(np.float32)

    usdm_ordinal = np.zeros(shape, dtype=np.uint8)
    usdm_ordinal[0:14, :] = 3  # 280 pixels D2+ severe drought

    usdm_ref = DroughtReferenceTarget(
        name="USDM_IOWA_JULY_2022",
        role="COMPETING_OPERATIONAL_PRODUCT",
        format_type="ORDINAL_SEVERITY",
        source_agency="NDMC",
        temporal_coverage="2022-07",
        spatial_resolution_m=1000.0,
        ordinal_grid=usdm_ordinal,
    )

    tier_b = evaluate_tier_b_operational_concordance(
        y_pred_drought=y_pred,
        fused_drought_score=fused_score,
        usdm_target=usdm_ref,
        overlapping_inputs=["SPI_3M", "NLDAS_SM"],
    )

    assert tier_b.spatial_concordance_f1 >= 0.90
    assert tier_b.cohen_kappa >= 0.80
    assert "operational agreement" in tier_b.scientific_disclaimer.lower()
    assert "SPI_3M" in tier_b.overlapping_inputs_disclosed


def test_tier_c_impact_corroboration_metrics():
    # 8 agricultural districts in Iowa
    severity = [0.85, 0.80, 0.75, 0.60, 0.50, 0.40, 0.30, 0.20]
    yield_loss = [35.0, 32.0, 30.0, 22.0, 18.0, 15.0, 10.0, 5.0]

    tier_c = evaluate_tier_c_impact_corroboration(
        regional_drought_severity_series=severity,
        regional_crop_yield_loss_series=yield_loss,
        impact_name="USDA_RMA_CROP_LOSS_2022",
        detected_onset_day=12.0,
        recorded_disaster_day=15.0,
    )

    assert tier_c.regional_rank_correlation >= 0.90
    assert tier_c.is_pixel_truth_prohibited is True
    assert tier_c.event_onset_delay_days == -3.0  # Detected 3 days before official disaster declaration!
