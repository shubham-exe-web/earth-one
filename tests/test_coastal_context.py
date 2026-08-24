import numpy as np
import pytest
from earth_one.coastal_context import compute_intertidal_suppression_mask, CoastalContextProfile


def test_coastal_suppression_marine_and_mudflats():
    h, w = 50, 50
    # Create coastal synthetic tile: Left half marine (elev=0, occ=100%), right half dry plain (elev=15m, occ=0%)
    occ = np.zeros((h, w), dtype=np.float32)
    elev = np.full((h, w), 15.0, dtype=np.float32)
    slope = np.full((h, w), 1.0, dtype=np.float32)

    occ[:, :20] = 0.95
    elev[:, :20] = 0.5

    # Intertidal strip between x=20 and x=25 (elev=3m, occ=40%)
    occ[:, 20:25] = 0.40
    elev[:, 20:25] = 3.0

    m_intertidal, profile = compute_intertidal_suppression_mask(occ, elev, slope)

    assert isinstance(profile, CoastalContextProfile)
    assert profile.is_coastal_aoi is True
    assert profile.marine_fraction > 0.35
    assert profile.intertidal_mudflat_fraction > 0.05

    # Marine zone must be completely suppressed (M=0)
    assert np.all(m_intertidal[:, :20] == 0.0)
    # Intertidal zone must be suppressed (M < 0.6)
    assert np.all(m_intertidal[:, 20:25] < 0.6)
    # Inland dry zone must be unconstrained (M=1.0)
    assert np.all(m_intertidal[:, 35:] == 1.0)


def test_inland_dry_plain_unconstrained():
    h, w = 50, 50
    occ = np.zeros((h, w), dtype=np.float32)
    elev = np.full((h, w), 120.0, dtype=np.float32)
    slope = np.full((h, w), 1.5, dtype=np.float32)

    m_intertidal, profile = compute_intertidal_suppression_mask(occ, elev, slope)
    assert profile.is_coastal_aoi is False
    assert np.all(m_intertidal == 1.0)
