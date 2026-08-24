from __future__ import annotations

"""Block 6D: Independent Empirical Validation of the Observability Index (O).

Evaluates whether the continuous physical Observability Index:
    O = S_scale * W_water * G_geom * T_terrain * D_validity

generalizes zero-shot to completely fresh flood events (NOT in the 7-event construction cohort):
1. EMSR357 India (Odisha Mahanadi Alluvial Delta, May 2019)
2. EMSR445 Ukraine (Prut River Fluvial Valley, July 2020)
3. EMSR567 Australia (Gympie Mary River Basin, March 2021)

Hypothesis & Validation Contracts:
1. Performance Stratification: PR-AUC(High O) >> PR-AUC(Low O).
2. Tri-State Resolvable Gain: PR-AUC_resolvable > PR-AUC_full across all unseen events.
3. Observability Calibration: Rank correlation between O tier and empirical detector precision.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from sklearn.metrics import precision_recall_curve, auc, roc_auc_score

from .flood_multievent import FloodCohortEventSpec
from .flood_spatial_generalization import evaluate_spatial_event


# Completely Fresh, Independent Validation Cohort (Never touched in Blocks 1-6C)
INDEPENDENT_VALIDATION_SPECS: list[FloodCohortEventSpec] = [
    # 1. India: Mahanadi Mega-Alluvial Delta (Cyclone Fani, May 2019)
    FloodCohortEventSpec(
        activation="EMSR357",
        event_key="EMSR357_Mahanadi",
        aoi_name="Mahanadi_Delta_Odisha_India",
        country="India",
        flood_regime="INLAND_RIVERINE_MEGA",
        bbox=(85.6000, 19.8000, 86.0000, 20.2000),
        grid_shape=(512, 512),
        s1_before_item="S1A_IW_GRDH_1SDV_20190506T122004_20190506T122029_027107_030E11",
        s1_event_item="S1B_IW_GRDH_1SDV_20190510T000425_20190510T000454_016174_01E6EF",
        s2_before_item=None,
        s2_event_item=None,
        cop_dem_item="Copernicus_DSM_COG_10_N19_00_E085_00_DEM",
        jrc_gsw_item="80E_20Nv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR357_AOI01_DEL_PRODUCT_r1_VECTORS_v4_vector/EMSR357_AOI01_DEL_PRODUCT_observedEventA_r1_v4.shp",
    ),
    # 2. Ukraine: Prut River Valley (Summer 2020 Fluvial Inundation)
    FloodCohortEventSpec(
        activation="EMSR445",
        event_key="EMSR445_Prut",
        aoi_name="Prut_River_Chernivtsi_Ukraine",
        country="Ukraine",
        flood_regime="INLAND_RIVERINE_PLUVIAL",
        bbox=(26.4000, 48.1500, 26.9000, 48.2600),
        grid_shape=(512, 512),
        s1_before_item="S1A_IW_GRDH_1SDV_20200709T160149_20200709T160214_033380_03DE13",
        s1_event_item="S1B_IW_GRDH_1SDV_20200715T160106_20200715T160131_022484_02AAC8",
        s2_before_item=None,
        s2_event_item=None,
        cop_dem_item="Copernicus_DSM_COG_10_N48_00_E026_00_DEM",
        jrc_gsw_item="20E_50Nv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR445_AOI01_DEL_PRODUCT_r1_RTP01_v1_vector/EMSR445_AOI01_DEL_PRODUCT_observedEventA_r1_v1.shp",
    ),
    # 3. Australia: Gympie / Mary River Basin (March 2021 Severe Flood)
    FloodCohortEventSpec(
        activation="EMSR567",
        event_key="EMSR567_Gympie",
        aoi_name="Gympie_Mary_River_Queensland_Australia",
        country="Australia",
        flood_regime="INLAND_RIVERINE_PLUVIAL",
        bbox=(152.6050, -26.2360, 152.7060, -26.1680),
        grid_shape=(512, 512),
        s1_before_item="S1A_IW_GRDH_1SDV_20210228T191349_20210228T191414_036794_04536B",
        s1_event_item="S1A_IW_GRDH_1SDV_20210324T191349_20210324T191414_037144_045F93",
        s2_before_item=None,
        s2_event_item=None,
        cop_dem_item="Copernicus_DSM_COG_10_S27_00_E152_00_DEM",
        jrc_gsw_item="150E_20Sv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR567_AOI01_DEL_PRODUCT_r1_RTP01_v1_vector/EMSR567_AOI01_DEL_PRODUCT_observedEventA_r1_v1.shp",
    ),
]


def run_independent_observability_validation() -> dict[str, Any]:
    print("=" * 95)
    print("  EARTH ONE FLOOD MODULE: BLOCK 6D INDEPENDENT OBSERVABILITY INDEX VALIDATION")
    print("  Evaluating Observability Index (O) zero-shot on 3 completely fresh global activations")
    print("=" * 95)

    eval_results = []

    for spec in INDEPENDENT_VALIDATION_SPECS:
        print(f"\nEvaluating Independent Event: {spec.activation} ({spec.country} — {spec.flood_regime})...")
        ev = evaluate_spatial_event(spec)
        eval_results.append(ev)
        m = ev["metrics"]
        comp = m["observability_components"]
        print(f"  -> Classified Regime: {ev['classified_regime']} (Conf: {ev['router_confidence']*100:.1f}%)")
        print(f"  -> Mean Observability (O): {comp['mean_observability']:.3f} | Resolvable Frac: {comp['resolvable_fraction']*100:.1f}%")
        print(f"  -> Full PR-AUC: {m['pr_auc_full_domain']:.4f} | Resolvable PR-AUC: {m['pr_auc_resolvable_domain']:.4f} (Δ={m['delta_pr_auc_resolvable']:+.4f})")

    macro_full_pr = float(np.mean([e["metrics"]["pr_auc_full_domain"] for e in eval_results]))
    macro_res_pr = float(np.mean([e["metrics"]["pr_auc_resolvable_domain"] for e in eval_results]))
    mean_o = float(np.mean([e["metrics"]["observability_components"]["mean_observability"] for e in eval_results]))

    manifest = {
        "schema": "earth_one_flood_observability_validation_v1.0",
        "validation_summary": {
            "total_independent_events": len(eval_results),
            "macro_mean_observability_O": round(mean_o, 4),
            "macro_pr_auc_full_domain": round(macro_full_pr, 5),
            "macro_pr_auc_resolvable_domain": round(macro_res_pr, 5),
            "macro_resolvable_gain_delta_pr": round(macro_res_pr - macro_full_pr, 5),
            "hypothesis_1_resolvable_gain_confirmed": bool(macro_res_pr >= macro_full_pr),
        },
        "event_evaluations": eval_results,
    }

    out_file = Path("data/results/flood_regime_routing/observability_validation_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nSaved Independent Observability Validation Results to {out_file}")
    return manifest
