from earth_one.drought.us_corn_belt_activation import instantiate_us_corn_belt_2022_real_activation


def test_us_corn_belt_real_activation():
    res = instantiate_us_corn_belt_2022_real_activation(grid_shape=(32, 32), pixel_size_m=100.0)

    # 1. Target grid & area check (100m x 100m = 1.0 ha/pixel)
    assert res.target_grid.crs == "EPSG:32615"
    assert res.target_grid.pixel_area_ha == 1.0
    assert res.segmentation.pixel_area_ha == 1.0

    # 2. Multi-window genuine distinct departures (Tasks D-14 & D-15)
    zv1 = float(res.anomalies.veg_z_1m[0, 0])
    zv3 = float(res.anomalies.veg_z_3m[0, 0])
    zv6 = float(res.anomalies.veg_z_6m[0, 0])
    assert zv1 < 0 and zv3 < 0 and zv6 < 0
    assert zv1 != zv3 or zv3 != zv6  # Distinct multi-window vegetation departures

    zp1 = float(res.anomalies.precip_z_1m[0, 0])
    zp3 = float(res.anomalies.precip_z_3m[0, 0])
    zp6 = float(res.anomalies.precip_z_6m[0, 0])
    assert zp1 < 0 and zp3 < 0 and zp6 < 0

    # 3. Regime routing
    assert res.regime_context.regime == "RAINFED_AGRICULTURE"
    assert res.regime_context.recommended_modality_weights.vegetation >= 0.30

    # 4. Tri-State decision & segmentation
    assert res.decision.drought_pixels > 0
    assert res.segmentation.event_count >= 1
    assert len(res.active_tracks) >= 1

    # 5. Governance Audit
    assert res.governance_audit is not None
    assert res.governance_audit.is_independent_truth is False  # USDM is an operational comparator
    assert "operational comparator" in res.governance_audit.scientific_disclaimer.lower()

    # 6. Validation metrics against USDM D2+
    assert res.validation_metrics is not None
    assert res.validation_metrics.f1_score >= 0.85
    assert res.validation_metrics.pr_auc >= 0.78
    assert len(res.provenance_hash) == 64
