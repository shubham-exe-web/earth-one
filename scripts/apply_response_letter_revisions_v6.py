#!/usr/bin/env python3
"""Script to apply verified updates to RESPONSE_TO_REVIEWERS_PAGEOPH.md."""

from pathlib import Path

def update_response_letter(text: str) -> str:
    # 1. Update Executive Response
    old_exec_start = "## Executive Response to Editor Alexander Rabinovich and Guest Editor Rana Muhammad Adnan Ikram"
    old_detailed_start = "## Detailed Responses to Reviewers"
    p_ex_s = text.find(old_exec_start)
    p_ex_e = text.find(old_detailed_start)
    assert p_ex_s != -1 and p_ex_e != -1

    new_exec_response = """## Executive Response to Editor Alexander Rabinovich and Guest Editor Rana Muhammad Adnan Ikram

Dear Dr. Alexander Rabinovich and Dr. Rana Muhammad Adnan Ikram,

We express our sincere gratitude to the Editorial Board and the three anonymous reviewers for their thorough, incisive, and constructive evaluation of our manuscript. We appreciate the opportunity to undertake a comprehensive "Revise and Resubmit" major revision.

Following an exhaustive audit of the initial draft and reviewer critiques, we have executed a ground-up restructuring of the study. Specifically, we have resolved all major scientific, methodological, and presentation issues:

1. **Resolution of Cohort Overlap & Definitive Event Manifest:**  
   In the previous draft, the experimental cohorts overlapped confusingly. We have rebuilt the experimental design into a **single, unambiguous partitioning structure**:
   - **Development Cohort ($N = 3$):** EMSR439 (Bangladesh), EMSR629 (Pakistan), and EMSR548 (Italy Catania). Used strictly for initial parameter bounding and isotonic probability fitting.
   - **Held-Out Validation Cohort ($N = 8$):** EMSR286 (Colombia), EMSR348 (Mozambique), EMSR357 (India), EMSR445 (Ukraine), EMSR464 (Vietnam), EMSR468 (Italy Tanaro), EMSR517 (Germany), and EMSR567 (Australia). Evaluated zero-shot without parameter tuning.
   - **Primary Independent Temporal Generalization (Table 5):** Evaluated strictly on the held-out validation cohort partitioned chronologically into **Modern Era ($2020\text{--}2021$, $N = 5$)** and **Historical Era ($2018\text{--}2019$, $N = 3$)**. Both cohorts demonstrate substantial, consistent skill over chance: the modern cohort achieved macro skill ratios of $3.03\times$ (full domain) and $2.43\times$ (resolvable domain), while the historical cohort achieved $1.84\times$ (full domain) and $1.21\times$ (resolvable domain), with $+23.0\%$ and $+35.6\%$ relative PR-AUC gains under observability filtering.

2. **Reconstruction of Supplementary Table S1 to Match Code Implementation:**  
   In response to the audit and Reviewer 2, Supplementary Table S1 has been completely reconstructed to eliminate an outdated additive placeholder ($0.35 G + 0.25 T + 0.20 W + 0.20 D$). Supplementary Table S1 now specifies the exact, authoritative multiplicative Observability formulation implemented in `src/earth_one/flood.py` and `src/earth_one/flood_tristate.py`:
   $$O = S_{\text{scale}} \times W_{\text{water}} \times G_{\text{geom}} \times T_{\text{terrain}} \times D_{\text{validity}}$$
   and details the mathematical formulations, input datasets, physical principles, and missing-data fallbacks for all direct water evidence channels ($S_{\text{SAR}}, S_{\text{opt}}, S_{\text{water}}$) and physical gates ($M_{\text{novelty}}, M_{\text{terrain}}, M_{\text{rain}}$).

3. **Prevalence-Normalized Skill Ratios and Scientific Reframing:**  
   We have rigorously normalized all PR-AUC metrics by their respective random-chance class prevalence baselines:
   - Full domain: macro PR-AUC $= 0.06972$ against $\bar{\pi}_{\text{full}} = 4.43\%$, yielding a macro skill ratio of **$2.59\times$** (range $1.04\times\text{--}9.05\times$).
   - Resolvable domain ($O \ge 0.50$): macro PR-AUC $= 0.09016$ ($+29.3\%$ relative gain) against $\bar{\pi}_{\text{res}} = 13.72\%$, yielding a macro skill ratio of **$1.97\times$** (range $0.31\times\text{--}6.81\times$, with 7 of 8 events exceeding chance, and Colombia EMSR286 exhibiting $0.31\times$ due to $72.53\%$ canyon channel flood prevalence in steep unresolvable terrain).
   - In Table 3 (reliability audit across $1,310,720$ held-out pixels), raw PR-AUC increases $2.3\times$ ($0.0587 \rightarrow 0.1336$), but normalized skill ratios remain virtually invariant ($0.92\times\text{--}1.19\times$, mean $\sim 1.0\times$) across all quintile tiers. This candidly reframes the Observability Index $O$ as an explicit **selective classification and risk-coverage abstention mechanism** (suppressing false alarms by $35.8\%$, from $162,000$ to $104,016$ pixels) rather than an artificial amplifier of intrinsic ranking skill.

4. **Circularity & Physical Variable Sharing Resolution:**  
   We have added a dedicated analysis in Section 2.5 explicitly resolving why DEM and JRC appear in both candidate scoring and observability filtering: $S_{\text{candidate}}$ answers the hydrological question *"Where can standing water pool?"* via gravitational physics ($M_{\text{terrain}}$) and historical novelty ($M_{\text{novelty}}$), whereas $O$ answers the remote sensing question *"Can satellite sensors resolve surface water here without electromagnetic ambiguity?"* via radar look geometry ($T_{\text{terrain}}$), relief roughness ($G_{\text{geom}}$), coastal tidal dynamics ($W_{\text{water}}$), and sub-pixel channel scale ($S_{\text{scale}}$).

5. **Matched-Coverage Baseline Benchmarks (Table 4 Panel B):**  
   We have expanded Table 4 to report retained class prevalence ($\pi$) and normalized skill ratios for all 8 matched-coverage modes at $44.14\%$ coverage ($925,684$ pixels). We demonstrate that while naive single-factor filters (such as slope-only $\le 6.5^\circ$ or score confidence $\ge 0.32$) retain elevated prevalence ($\sim 9-11\%$), their normalized skill ratios collapse ($0.72\times\text{--}0.75\times$) due to massive false positives ($122,000\text{--}142,000$ pixels). Full Observability achieves $104,016$ false positives and a superior skill ratio of $1.97\times$.

6. **Expanded Multi-Scale Statistical Inferences:**  
   We have supplemented the 5-bin audit with: (1) event-level correlation across $N=8$ independent held-out activations (Pearson $r = 0.761, p = 0.028$; Spearman $\rho = 0.786, p = 0.021$); (2) spatial block bootstrap resampling ($B=1,000$ blocks of $32 \times 32$ pixels) confirming positive correlation in $96.4\%$ of realizations; and (3) 3-, 4-, and 10-bin sensitivity tests proving normalized skill invariance across all bin partitions.

7. **Reference Data Provenance, Spatial Resolution & Acquisition Lags (Table S3):**  
   We have added Supplementary Table S3 documenting the exact sensor provenance (Pléiades, WorldView, COSMO-SkyMed, SPOT, aerial orthophotos), native resolutions ($0.15\text{ m}\text{--}3\text{ m}$), and acquisition time lags ($\Delta t \le 12\text{ h}$) for all 11 CEMS activations.

8. **Fully Open Code, Data, and Reproducibility Environment:**  
   All source code, regression tests, and evaluation scripts are openly available on GitHub ([https://github.com/shubham-exe-web/earth-one](https://github.com/shubham-exe-web/earth-one), tag `v2.0.0`). The reproduction commands have been verified and documented using standard Python packaging: `pip install -e .`.

---

"""
    text = text[:p_ex_s] + new_exec_response + text[p_ex_e:]

    # 2. Add Audit Issues F, G, H, I into Audit Reconciliation
    audit_marker = "### Reviewer 1 Comments"
    p_aud_end = text.find(audit_marker)
    assert p_aud_end != -1

    extra_audit = """4. **Audit Issue D: Authoritative Multiplicative Formulation in Supplementary Table S1:**  
   - Supplementary Table S1 has been completely reconstructed to eliminate the legacy additive heuristic formula ($0.35 G + 0.25 T + 0.20 W + 0.20 D$).
   - Table S1 now presents the exact multiplicative formulation $O = S_{\text{scale}} \times W_{\text{water}} \times G_{\text{geom}} \times T_{\text{terrain}} \times D_{\text{validity}}$ and documents the exact mathematical formulas, input bands, and missing-data handlers for all evidence fusion channels ($S_{\text{SAR}}, S_{\text{opt}}, S_{\text{water}}$) and physical gates ($M_{\text{novelty}}, M_{\text{terrain}}, M_{\text{rain}}$).

5. **Audit Issue E: Resolution of Physical Variable Sharing (Circularity) in Section 2.5:**  
   - We added a dedicated subsection in Section 2.5 explaining the physical separation between candidate hydro-dynamic gating (gravitational fluid accumulation) and observational ambiguity gating (electromagnetic imaging distortion, relief roughness, tidal dynamics, and sub-pixel scaling).

6. **Audit Issue F: Multi-Scale Statistical Inferences and Invariance Tests:**  
   - We supplemented the 5-bin calibration analysis in Section 3.2 with event-level correlation ($N=8$, $r = 0.761, p = 0.028$), spatial block bootstrap inference ($B=1,000$ iterations, $32 \times 32$ pixel blocks), and 3-, 4-, and 10-bin sensitivity tests proving normalized skill invariance across all bin stratifications.

7. **Audit Issue G: Matched-Coverage Prevalence and Skill Reporting (Table 4 Panel B):**  
   - We expanded Table 4 Panel B to report class prevalence ($\pi$) and normalized skill ratios ($SR$) for all 8 matched-coverage modes at $44.14\%$ coverage ($925,684$ pixels).

8. **Audit Issue H: Reference Image Provenance and Acquisition Lags (Supplementary Table S3):**  
   - We added Supplementary Table S3 detailing CEMS reference sensor provenance, native resolutions ($0.15\text{ m}\text{--}3\text{ m}$), and acquisition lags ($\Delta t$).

9. **Audit Issue I: Reproduction Command and Packaging Harmonization:**  
   - We verified that the codebase is installed via `pip install -e .` (based on `pyproject.toml`) and updated all reproduction commands accordingly.

---

"""
    # Check if extra_audit already partially inserted
    if "Audit Issue D: Authoritative Multiplicative Formulation" not in text:
        text = text[:p_aud_end] + extra_audit + text[p_aud_end:]

    # Update any pip install -r requirements.txt in the response letter
    text = text.replace("pip install -r requirements.txt", "pip install -e .")

    return text

def main():
    paths = [
        Path("/Users/shubhamsharma/Earth-One/docs/PAGEOPH/RESPONSE_TO_REVIEWERS_PAGEOPH.md"),
        Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/RESPONSE_TO_REVIEWERS_PAGEOPH.md"),
    ]
    for p in paths:
        raw = p.read_text(encoding="utf-8")
        updated = update_response_letter(raw)
        p.write_text(updated, encoding="utf-8")
        print(f"Successfully updated response letter at {p} ({len(updated)} bytes)")

if __name__ == "__main__":
    main()
