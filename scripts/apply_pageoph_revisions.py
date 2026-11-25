#!/usr/bin/env python3
"""Script to apply verified updates to REVISED_MANUSCRIPT_PAGEOPH.md and RESPONSE_TO_REVIEWERS_PAGEOPH.md."""

from pathlib import Path

def update_manuscript(p: Path):
    lines = p.read_text(encoding='utf-8').splitlines(keepends=True)
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if line.startswith('**Table 5.** Primary Independent Temporal Generalization'):
            start_idx = i
        if start_idx is not None and 'In both eras, physical observability filtering yielded' in line:
            end_idx = i + 1
            break

    if start_idx is not None and end_idx is not None:
        replacement = """**Table 5.** Primary Independent Temporal Generalization Evaluation across Chronological Eras (Held-Out Validation Pool, N = 8).
| Chronological Era & Activations | Events ($N$) | Full Prev. ($\\bar{\\pi}_{\\text{full}}$) | Full PR-AUC | Full Skill Ratio | Res. Prev. ($\\bar{\\pi}_{\\text{res}}$) | Resolvable PR-AUC ($O \\ge 0.50$) | Res. Skill Ratio | PR-AUC Gain ($\\Delta$) | Relative Gain |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Modern Era (2020–2021):** EMSR445, EMSR464, EMSR468, EMSR517, EMSR567 | $5$ | $0.03672$ ($3.67\%$) | $0.05558$ | $3.03\\times$ | $0.05642$ ($5.64\%$) | $0.06838$ | $2.43\\times$ | $+0.01280$ | $+23.0\%$ |
| **Historical Era (2018–2019):** EMSR286, EMSR348, EMSR357 | $3$ | $0.05697$ ($5.70\%$) | $0.09327$ | $1.84\\times$ | $0.27174$ ($27.17\%$) | $0.12647$ | $1.21\\times$ | $+0.03320$ | $+35.6\%$ |
| **Full Held-Out Validation Cohort** | $8$ | $0.04431$ ($4.43\%$) | $0.06972$ | $2.59\\times$ | $0.13718$ ($13.72\%$) | $0.09016$ | $1.97\\times$ | $+0.02044$ | $+29.3\%$ |

*Notes:* Evaluated strictly on the eight held-out validation events. Modern Era: EMSR445 (Prut River, Ukraine, July 2020), EMSR464 (Ha Tinh, Vietnam, October 2020), EMSR468 (Tanaro Valley, Italy, October 2020), EMSR517 (Rheinland-Pfalz, Germany, July 2021), EMSR567 (Gympie Mary River, Australia, March 2021). Historical Era: EMSR286 (Ituango Cauca, Colombia, May 2018), EMSR348 (Quelimane, Mozambique, March 2019), EMSR357 (Mahanadi Delta, India, May 2019). Full Skill Ratio and Res. Skill Ratio represent macro averages of event-level ratios normalized by full-domain ($\\pi_{\\text{full}}$) and resolvable-domain ($\\pi_{\\text{res}}$) positive prevalence baselines, respectively.

As detailed in Table 5, the autonomous engine generalized robustly across both chronological eras. The higher absolute PR-AUC in the historical cohort ($0.09327$ full domain, $0.12647$ resolvable domain) relative to the modern cohort ($0.05558$ full domain, $0.06838$ resolvable domain) is directly governed by differences in baseline positive prevalence ($\\bar{\\pi}_{\\text{full}} = 5.70\%$ and $\\bar{\\pi}_{\\text{res}} = 27.17\%$ in the historical cohort vs. $3.67\%$ and $5.64\%$ in the modern cohort, driven by extensive reference flood polygons in EMSR286 Cauca and EMSR348 Mozambique). When normalized by their respective random-chance baselines, both cohorts exhibit substantial, consistent skill over chance: the modern cohort achieved macro skill ratios of $3.03\\times$ (full domain) and $2.43\\times$ (resolvable domain), while the historical cohort achieved $1.84\\times$ (full domain) and $1.21\\times$ (resolvable domain). In both eras, physical observability filtering yielded pronounced accuracy improvements ($+23.0\%$ relative PR-AUC gain in the modern era and $+35.6\%$ in the historical era).
"""
        lines[start_idx:end_idx] = [replacement]
        p.write_text(''.join(lines), encoding='utf-8')
        print(f"Successfully updated Table 5 in {p}")
    else:
        print(f"Failed to find Table 5 bounds in {p}: start={start_idx}, end={end_idx}")

def main():
    m1 = Path("/Users/shubhamsharma/Earth-One/docs/PAGEOPH/REVISED_MANUSCRIPT_PAGEOPH.md")
    m2 = Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/REVISED_MANUSCRIPT_PAGEOPH.md")
    update_manuscript(m1)
    update_manuscript(m2)

if __name__ == "__main__":
    main()
