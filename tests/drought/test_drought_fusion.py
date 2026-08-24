import numpy as np
from earth_one.drought.anomalies import MultiWindowAnomalies
from earth_one.drought.regime import classify_drought_regime
from earth_one.drought.fusion import fuse_drought_evidence


def test_drought_evidence_fusion():
    shape = (10, 10)
    valid = np.ones(shape, dtype=bool)

    # Severe stress across all channels
    anom = MultiWindowAnomalies(
        veg_z_1m=np.full(shape, -2.0, dtype=np.float32),
        veg_z_3m=np.full(shape, -2.0, dtype=np.float32),
        veg_z_6m=np.full(shape, -2.0, dtype=np.float32),
        precip_z_1m=np.full(shape, -2.0, dtype=np.float32),
        precip_z_3m=np.full(shape, -2.0, dtype=np.float32),
        precip_z_6m=np.full(shape, -2.0, dtype=np.float32),
        sm_surf_z_1m=np.full(shape, -2.0, dtype=np.float32),
        sm_rz_z_3m=np.full(shape, -2.0, dtype=np.float32),
        thermal_z_1m=np.full(shape, 2.0, dtype=np.float32),
        valid_mask=valid,
        provenance_hash="TEST_ANOM",
    )

    regime = classify_drought_regime(np.full(shape, 0.50, dtype=np.float32))
    ev = fuse_drought_evidence(anom, regime)

    assert ev.fused_drought_score.shape == shape
    assert np.allclose(ev.fused_drought_score, 1.0)
    assert np.allclose(ev.vegetation_stress_score, 1.0)
    assert np.allclose(ev.precipitation_deficit_score, 1.0)
