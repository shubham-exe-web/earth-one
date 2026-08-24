import numpy as np
import pytest
from earth_one.flood_ablation import compute_dem_slope


def test_compute_dem_slope_flat():
    # 0 elevation change -> 0 slope
    elev = np.full((10, 10), 15.0, dtype=np.float32)
    slope = compute_dem_slope(elev, cell_size_x_m=10.0, cell_size_y_m=10.0)
    assert slope.shape == (10, 10)
    assert np.allclose(slope, 0.0)


def test_compute_dem_slope_gradient():
    # 10m rise over 10m run -> 45 degree slope
    elev = np.zeros((10, 10), dtype=np.float32)
    for r in range(10):
        elev[r, :] = r * 10.0  # 10m rise per cell in y direction
    slope = compute_dem_slope(elev, cell_size_x_m=10.0, cell_size_y_m=10.0)
    # Middle rows (away from boundary 1-sided diffs) should be exactly 45 degrees
    assert np.allclose(slope[2:8, :], 45.0, atol=1e-3)
