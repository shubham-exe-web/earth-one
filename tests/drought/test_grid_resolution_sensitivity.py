"""Unit tests for computational grid resolution sensitivity analysis (Phase 31.5B)."""

from pathlib import Path
import pytest
import rasterio

from run_grid_resolution_sensitivity import run_grid_sensitivity


def test_grid_resolution_sensitivity_execution(tmp_path: Path):
    prob_file = Path("data/drought_raw/phase29_scientific_release/drought_probability.tif")
    if not prob_file.exists():
        pytest.skip(f"Test probability file not found: {prob_file}")

    out_csv = tmp_path / "test_grid_sensitivity.csv"
    rasters_dir = tmp_path / "rasters"

    results = run_grid_sensitivity(
        prob_path=prob_file,
        usdm_mask_path=None,
        threshold=0.25,
        out_csv=out_csv,
        export_rasters_dir=rasters_dir,
    )

    assert len(results) == 3
    assert out_csv.exists()
    assert (tmp_path / "test_grid_sensitivity.json").exists()

    res_labels = [r["grid_label"] for r in results]
    assert res_labels == ["100 m", "500 m", "1 km"]

    # Assert metric ranges
    for r in results:
        assert r["f1_score"] >= 0.0 and r["f1_score"] <= 1.0
        assert r["iou_jaccard"] >= 0.0 and r["iou_jaccard"] <= 1.0
        assert r["brier_score"] >= 0.0 and r["brier_score"] <= 1.0
        assert r["expected_calibration_error"] >= 0.0 and r["expected_calibration_error"] <= 1.0
        assert r["total_pixels"] > 0

    # Verify that raster files were written and are valid GeoTIFFs
    for res_tag in ["100m", "500m", "1km"]:
        p_tif = rasters_dir / f"drought_probability_{res_tag}.tif"
        u_tif = rasters_dir / f"usdm_reference_{res_tag}.tif"
        assert p_tif.exists()
        assert u_tif.exists()
        with rasterio.open(p_tif) as src:
            assert src.count == 1
            assert src.width > 0 and src.height > 0
        with rasterio.open(u_tif) as src:
            assert src.count == 1
            assert src.width > 0 and src.height > 0
