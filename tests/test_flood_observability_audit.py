import numpy as np
from earth_one.flood_observability_audit import audit_event_observability
from earth_one.flood_spatial_generalization import DEVELOPMENT_SPECS
from earth_one.flood_tristate import compute_tristate_flood_decision, TriStateClassificationResult


def test_observability_audit_pakistan():
    pak_spec = next(s for s in DEVELOPMENT_SPECS if s.activation == "EMSR629")
    prof = audit_event_observability(pak_spec)
    
    assert prof.activation == "EMSR629"
    assert prof.polygon_count > 1000
    assert prof.is_observability_limited is False
    assert "Alluvial Sheet Flood" in prof.primary_failure_mechanism


def test_tristate_flood_decision():
    shape = (50, 50)
    score = np.full(shape, 0.10, dtype=np.float32)
    score[:10, :10] = 0.85  # Flood pixels
    
    valid = np.ones(shape, dtype=bool)
    slope = np.zeros(shape, dtype=np.float32)
    slope[40:, :] = 15.0  # Steep slope (> 12 deg)
    
    elev = np.full(shape, 20.0, dtype=np.float32)
    jrc = np.zeros(shape, dtype=np.float32)
    
    res = compute_tristate_flood_decision(
        flood_score=score,
        valid_mask=valid,
        slope_deg=slope,
        elevation_m=elev,
        jrc_occurrence=jrc,
        detection_threshold=0.20,
    )
    
    assert isinstance(res, TriStateClassificationResult)
    assert res.status == "completed"
    assert res.flood_pixels == 100  # 10x10 flood
    assert res.unresolved_pixels == 500  # 10x50 steep slope
    assert res.unresolved_fraction == 0.20
