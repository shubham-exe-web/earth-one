from earth_one.drought.reference_taxonomy import DroughtReferenceTarget
from earth_one.drought.reference_governance import audit_reference_governance


def test_reference_governance_rules():
    # 1. Operational product (USDM)
    usdm_target = DroughtReferenceTarget(
        name="USDM_IOWA_2022",
        role="COMPETING_OPERATIONAL_PRODUCT",
        format_type="ORDINAL_SEVERITY",
        source_agency="NDMC",
        temporal_coverage="2022-07",
        spatial_resolution_m=1000.0,
    )
    audit_usdm = audit_reference_governance(usdm_target, candidate_overlapping_inputs=["SPI", "NLDAS_SM"])
    assert audit_usdm.is_independent_truth is False
    assert audit_usdm.is_pixel_truth_allowed is True
    assert "operational comparator" in audit_usdm.scientific_disclaimer.lower()

    # 2. Independent physical observation (In-situ soil probe)
    probe_target = DroughtReferenceTarget(
        name="USCRN_IN_SITU_SOIL_PROBE",
        role="INDEPENDENT_VALIDATION",
        format_type="CONTINUOUS_INDEX",
        source_agency="NOAA_USCRN",
        temporal_coverage="2022-07",
        spatial_resolution_m=1.0,
    )
    audit_probe = audit_reference_governance(probe_target)
    assert audit_probe.is_independent_truth is True
    assert audit_probe.is_pixel_truth_allowed is True

    # 3. Impact corroboration (Crop insurance yield loss)
    impact_target = DroughtReferenceTarget(
        name="USDA_RMA_CROP_LOSS_CLAIMS",
        role="IMPACT_CORROBORATION",
        format_type="EVENT_POLYGON",
        source_agency="USDA_RMA",
        temporal_coverage="2022-Season",
        spatial_resolution_m=50000.0,
    )
    audit_impact = audit_reference_governance(impact_target)
    assert audit_impact.is_independent_truth is True
    assert audit_impact.is_pixel_truth_allowed is False  # Prohibited from binary pixel evaluation
