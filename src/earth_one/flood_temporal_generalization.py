from __future__ import annotations

"""Block 6C: Temporal & Interannual Generalization Benchmark for Flood Module 2.

Evaluates the frozen Earth One Flood Engine across distinct temporal eras:
1. Baseline Development Era (2020-2022 Multi-Season Activations)
2. Unseen Historic Era (2018-2019 Pre-Development Seasons)
   - EMSR348 Mozambique (Cyclone Idai, March 2019)
   - EMSR286 Colombia (Cauca River / Ituango Dam, May 2018)

Quantifies:
- Macro PR-AUC and F1 across eras
- Temporal domain shift delta: Delta_temporal = PR_AUC_unseen_era - PR_AUC_dev_era
- Dual-domain evaluation: Full Domain vs Resolvable Domain (O >= 0.50)
- Stratification across biophysical regimes
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .flood_multievent import FloodCohortEventSpec
from .flood_spatial_generalization import evaluate_spatial_event, DEVELOPMENT_SPECS, UNSEEN_SPATIAL_SPECS


# Unseen Historic Temporal Era Cohort (2018 - 2019)
UNSEEN_TEMPORAL_SPECS: list[FloodCohortEventSpec] = [
    # 1. Year 2019: Mozambique Cyclone Idai
    FloodCohortEventSpec(
        activation="EMSR348",
        event_key="EMSR348_Quelimane",
        aoi_name="Quelimane_Zambezia_Mozambique",
        country="Mozambique",
        flood_regime="COASTAL_ESTUARINE_TIDAL",
        bbox=(36.7515, -17.9895, 37.0494, -17.7383),
        grid_shape=(512, 512),
        s1_before_item="S1B_IW_GRDH_1SDV_20190314T160711_20190314T160736_015352_01CBEE",
        s1_event_item="S1B_IW_GRDH_1SDV_20190320T030748_20190320T030813_015432_01CE6E",
        s2_before_item="S2A_MSIL2A_20190225T072901_R049_T37KBA_20201007T202348",
        s2_event_item="S2B_MSIL2A_20190401T072619_R049_T37KBA_20201006T210326",
        cop_dem_item="Copernicus_DSM_COG_10_S18_00_E036_00_DEM",
        jrc_gsw_item="30E_10Sv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR348_01QUELIMANE_01DELINEATION_MAP_v2_vector/VECTOR/EMSR348_01QUELIMANE_DEL_v2_observed_event_a.shp",
    ),
    # 2. Year 2018: Colombia Ituango Dam Fluvial Outflow
    FloodCohortEventSpec(
        activation="EMSR286",
        event_key="EMSR286_Ituango",
        aoi_name="Ituango_Cauca_Colombia",
        country="Colombia",
        flood_regime="INLAND_RIVERINE_PLUVIAL",
        bbox=(-75.6700, 7.1100, -75.6400, 7.1450),
        grid_shape=(512, 512),
        s1_before_item="S1B_IW_GRDH_1SDV_20180427T104932_20180427T104957_010668_0137A7",
        s1_event_item="S1B_IW_GRDH_1SDV_20180521T104933_20180521T104958_011018_0142FA",
        s2_before_item=None,
        s2_event_item=None,  # Pre-2020 S2 cloudy
        cop_dem_item="Copernicus_DSM_COG_10_N07_00_W076_00_DEM",
        jrc_gsw_item="80W_10Nv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR286_01ITUANGODAM_01DELINEATION_MONIT01_v1_vector/EMSR286_01ITUANGODAM_DEL_MONIT01_v1_observed_event_a.shp",
    ),
]


def run_temporal_generalization_benchmark() -> dict[str, Any]:
    print("=" * 95)
    print("  EARTH ONE FLOOD MODULE: BLOCK 6C TEMPORAL & INTERANNUAL GENERALIZATION BENCHMARK")
    print("  Comparing 2020-2022 Development Era vs 2018-2019 Unseen Historic Era")
    print("=" * 95)

    # 1. 2020-2022 Era Events
    era_2020_2022_specs = [
        s for s in (DEVELOPMENT_SPECS + UNSEEN_SPATIAL_SPECS)
        if s.activation != "EMSR348"  # EMSR348 is 2019
    ]

    print(f"\n--- EVALUATING 2020-2022 ERA ({len(era_2020_2022_specs)} activations) ---")
    evals_dev_era = []
    for spec in era_2020_2022_specs:
        print(f"  Evaluating {spec.activation} ({spec.country} — {spec.flood_regime})...")
        ev = evaluate_spatial_event(spec)
        evals_dev_era.append(ev)
        m = ev["metrics"]
        print(f"    -> Classified: {ev['classified_regime']} | Full PR-AUC: {m['pr_auc_full_domain']:.4f} | Resolvable PR-AUC: {m['pr_auc_resolvable_domain']:.4f}")

    # 2. 2018-2019 Era Events
    print(f"\n--- EVALUATING UNSEEN 2018-2019 HISTORIC ERA ({len(UNSEEN_TEMPORAL_SPECS)} activations) ---")
    evals_unseen_era = []
    for spec in UNSEEN_TEMPORAL_SPECS:
        print(f"  Evaluating {spec.activation} ({spec.country} — {spec.flood_regime})...")
        ev = evaluate_spatial_event(spec)
        evals_unseen_era.append(ev)
        m = ev["metrics"]
        print(f"    -> Classified: {ev['classified_regime']} | Full PR-AUC: {m['pr_auc_full_domain']:.4f} | Resolvable PR-AUC: {m['pr_auc_resolvable_domain']:.4f}")

    pr_full_dev = float(np.mean([e["metrics"]["pr_auc_full_domain"] for e in evals_dev_era]))
    pr_res_dev = float(np.mean([e["metrics"]["pr_auc_resolvable_domain"] for e in evals_dev_era]))

    pr_full_unseen = float(np.mean([e["metrics"]["pr_auc_full_domain"] for e in evals_unseen_era]))
    pr_res_unseen = float(np.mean([e["metrics"]["pr_auc_resolvable_domain"] for e in evals_unseen_era]))

    delta_temporal_full = pr_full_unseen - pr_full_dev
    delta_temporal_res = pr_res_unseen - pr_res_dev

    manifest = {
        "schema": "earth_one_flood_temporal_generalization_v1.0",
        "benchmark_summary": {
            "dev_era_years": "2020-2022",
            "unseen_era_years": "2018-2019",
            "total_dev_era_events": len(evals_dev_era),
            "total_unseen_era_events": len(evals_unseen_era),
            "macro_pr_auc_full_dev_era": round(pr_full_dev, 5),
            "macro_pr_auc_full_unseen_era": round(pr_full_unseen, 5),
            "macro_pr_auc_resolvable_dev_era": round(pr_res_dev, 5),
            "macro_pr_auc_resolvable_unseen_era": round(pr_res_unseen, 5),
            "temporal_domain_shift_delta_full": round(delta_temporal_full, 5),
            "temporal_domain_shift_delta_resolvable": round(delta_temporal_res, 5),
        },
        "dev_era_evaluations": evals_dev_era,
        "unseen_era_evaluations": evals_unseen_era,
    }

    out_file = Path("data/results/flood_regime_routing/temporal_generalization_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nSaved Temporal Generalization Manifest to {out_file}")
    return manifest
