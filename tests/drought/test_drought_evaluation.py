import numpy as np
from earth_one.drought.pilots import build_real_pilot_activation
from earth_one.drought.evaluation import evaluate_drought_mode, compute_pr_auc


def test_pr_auc_computation():
    y_true = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=bool)
    y_perfect = np.array([0.9, 0.8, 0.85, 0.95, 0.1, 0.2, 0.05, 0.15], dtype=np.float32)
    
    pr_auc = compute_pr_auc(y_true, y_perfect)
    assert pr_auc >= 0.80


def test_multimodal_ablation_comparison():
    pilot = build_real_pilot_activation("US_CORN_BELT_2022")

    # Mode A: Veg only
    mA = evaluate_drought_mode(pilot, "MODE_A_VEG_ONLY")
    assert mA.mode_name == "MODE_A_VEG_ONLY"
    assert mA.total_pixels == 4096

    # Mode B: Precip only
    mB = evaluate_drought_mode(pilot, "MODE_B_PRECIP_ONLY")
    assert mB.mode_name == "MODE_B_PRECIP_ONLY"

    # Mode H: Full Earth One
    mH = evaluate_drought_mode(pilot, "MODE_H_FULL_EARTH_ONE")
    assert mH.f1_score >= 0.80
    assert mH.pr_auc >= 0.80
    assert mH.resolvable_pr_auc >= mH.pr_auc  # Resolvable PR-AUC is equal or higher
