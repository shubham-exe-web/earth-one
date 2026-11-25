from pathlib import Path

ROOT = Path("/Users/shubhamsharma/Earth-One")
BRAIN = Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f")

MANUSCRIPT_REPO = ROOT / "docs" / "PAGEOPH" / "REVISED_MANUSCRIPT_PAGEOPH.md"
MANUSCRIPT_BRAIN = BRAIN / "REVISED_MANUSCRIPT_PAGEOPH.md"
RESPONSE_REPO = ROOT / "docs" / "PAGEOPH" / "RESPONSE_TO_REVIEWERS_PAGEOPH.md"
RESPONSE_BRAIN = BRAIN / "RESPONSE_TO_REVIEWERS_PAGEOPH.md"

with open(MANUSCRIPT_REPO, "r", encoding="utf-8") as f:
    m = f.read()

# 1. Pre-event baseline window
m = m.replace(
    "Pre-event baseline scenes were selected during the dry season ($15\\text{--}90$ days prior to flood peak) to establish normal baseline backscatter.",
    "Pre-event baseline observations were selected from the immediately preceding repeat-pass orbit of identical relative track and geometry (typically 6 to 24 days prior to flood onset, matching Sentinel-1's nominal orbital cycle) to minimize seasonal backscatter drift, with long-term dry-season baselines (15–90 days) utilized for climatological permanent water calibration."
)

# 2. SCL classes strictly 4, 5, 6
m = m.replace(
    "only valid clear land/water pixels (classes 4, 5, 6, 7) were admitted.",
    "strictly valid clear surface pixels (classes 4 [vegetation], 5 [bare soil], and 6 [water]) were admitted. SCL class 7 is designated as UNCLASSIFIED and treated as ambiguous alongside classes 3, 8, 9, 10, and 11."
)

# 3. Table 2a validation summary row
old_t2a_row = "| **Validation Macro Mean** | — | **$0.0443$** | **$0.06972$** | **$2.59\\times$** | **$115,710$** | **$0.1372$** | **$0.09016$** | **$+0.02044$** | **$1.97\\times$** |"
new_t2a_row = "| **Validation Macro Mean** | — | **$0.0443$** | **$0.06972$** | **$2.59\\times$ (macro) / $1.57\\times$ (pool)** | **$115,710$** | **$0.1372$** | **$0.09016$** | **$+0.02044$** | **$1.97\\times$ (macro) / $0.66\\times$ (pool)** |"
m = m.replace(old_t2a_row, new_t2a_row)

# 4. Table 5 dual skill ratios
old_t5_table = """| Chronological Era & Activations | Events ($N$) | Full Prev. ($\\bar{\\pi}_{\\text{full}}$) | Full PR-AUC | Full Skill Ratio | Res. Prev. ($\\bar{\\pi}_{\\text{res}}$) | Resolvable PR-AUC ($O \\ge 0.50$) | Res. Skill Ratio | PR-AUC Gain ($\\Delta$) | Relative Gain |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Modern Era (2020–2021):** EMSR445, EMSR464, EMSR468, EMSR517, EMSR567 | $5$ | $0.03672$ ($3.67\\%$) | $0.05558$ | $3.03\\times$ | $0.05642$ ($5.64\\%$) | $0.06838$ | $2.43\\times$ | $+0.01280$ | $+23.0\\%$ |
| **Historical Era (2018–2019):** EMSR286, EMSR348, EMSR357 | $3$ | $0.05697$ ($5.70\\%$) | $0.09327$ | $1.84\\times$ | $0.27174$ ($27.17\\%$) | $0.12647$ | $1.21\\times$ | $+0.03320$ | $+35.6\\%$ |
| **Full Held-Out Validation Cohort** | $8$ | $0.04431$ ($4.43\\%$) | $0.06972$ | $2.59\\times$ | $0.13718$ ($13.72\\%$) | $0.09016$ | $1.97\\times$ | $+0.02044$ | $+29.3\\%$ |"""

new_t5_table = """| Chronological Era & Activations | Events ($N$) | Full Prev. ($\\bar{\\pi}_{\\text{full}}$) | Full PR-AUC | Full Pool SR | Full Macro SR | Res. Prev. ($\\bar{\\pi}_{\\text{res}}$) | Resolvable PR-AUC ($O \\ge 0.50$) | Res. Pool SR | Res. Macro SR | Relative Gain |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Modern Era (2020–2021):** EMSR445, EMSR464, EMSR468, EMSR517, EMSR567 | $5$ | $0.03672$ ($3.67\\%$) | $0.05558$ | $1.51\\times$ | $3.03\\times$ | $0.05642$ ($5.64\\%$) | $0.06838$ | $1.21\\times$ | $2.43\\times$ | $+23.0\\%$ |
| **Historical Era (2018–2019):** EMSR286, EMSR348, EMSR357 | $3$ | $0.05697$ ($5.70\\%$) | $0.09327$ | $1.64\\times$ | $1.84\\times$ | $0.27174$ ($27.17\\%$) | $0.12647$ | $0.47\\times$ | $1.21\\times$ | $+35.6\\%$ |
| **Full Held-Out Validation Cohort** | $8$ | $0.04431$ ($4.43\\%$) | $0.06972$ | $1.57\\times$ | $2.59\\times$ | $0.13718$ ($13.72\\%$) | $0.09016$ | $0.66\\times$ | $1.97\\times$ | $+29.3\\%$ |"""

m = m.replace(old_t5_table, new_t5_table)

# 5. Table 4 Panel C: Reconcile pooled skill ratios
m = m.replace(
    "| **$O_{\\text{no-scale}}$** | Leave out spatial scale degradation factor ($O = W \\cdot G \\cdot T \\cdot D$) | $44.14\\%$ | $11.45\\%$ | $0.0824$ | $0.72\\times$ | $1.54\\times$ | $+0.0127$ | $118,500$ | $1.27\\times$ | Retains unresolvable narrow mountain channels |",
    "| **$O_{\\text{no-scale}}$** | Leave out spatial scale degradation factor ($O = W \\cdot G \\cdot T \\cdot D$) | $44.14\\%$ | $11.45\\%$ | $0.0824$ | $0.60\\times$ | $1.54\\times$ | $+0.0127$ | $118,500$ | $1.27\\times$ | Retains unresolvable narrow mountain channels |"
)
m = m.replace(
    "| **$O_{\\text{no-water}}$** | Leave out intertidal ambiguity factor ($O = S \\cdot G \\cdot T \\cdot D$) | $44.14\\%$ | $12.18\\%$ | $0.0795$ | $0.65\\times$ | $1.42\\times$ | $+0.0098$ | $126,800$ | $1.36\\times$ | Retains coastal tidal mudflat variations |",
    "| **$O_{\\text{no-water}}$** | Leave out intertidal ambiguity factor ($O = S \\cdot G \\cdot T \\cdot D$) | $44.14\\%$ | $12.18\\%$ | $0.0795$ | $0.58\\times$ | $1.42\\times$ | $+0.0098$ | $126,800$ | $1.36\\times$ | Retains coastal tidal mudflat variations |"
)
m = m.replace(
    "| **$O_{\\text{no-geom}}$** | Leave out radar relief roughness factor ($O = S \\cdot W \\cdot T \\cdot D$) | $44.14\\%$ | $10.62\\%$ | $0.0763$ | $0.72\\times$ | $1.28\\times$ | $+0.0066$ | $135,200$ | $1.45\\times$ | Retains radar shadow in dissected terrain |",
    "| **$O_{\\text{no-geom}}$** | Leave out radar relief roughness factor ($O = S \\cdot W \\cdot T \\cdot D$) | $44.14\\%$ | $10.62\\%$ | $0.0763$ | $0.56\\times$ | $1.28\\times$ | $+0.0066$ | $135,200$ | $1.45\\times$ | Retains radar shadow in dissected terrain |"
)
m = m.replace(
    "| **$O_{\\text{no-slope}}$** | Leave out slope observability penalty ($O = S \\cdot W \\cdot G \\cdot D$) | $44.14\\%$ | $9.85\\%$ | $0.0738$ | $0.75\\times$ | $1.15\\times$ | $+0.0041$ | $144,600$ | $1.55\\times$ | Retains steep mountain slopes ($\\theta > 15^\\circ$) |",
    "| **$O_{\\text{no-slope}}$** | Leave out slope observability penalty ($O = S \\cdot W \\cdot G \\cdot D$) | $44.14\\%$ | $9.85\\%$ | $0.0738$ | $0.54\\times$ | $1.15\\times$ | $+0.0041$ | $144,600$ | $1.55\\times$ | Retains steep mountain slopes ($\\theta > 15^\\circ$) |"
)
m = m.replace(
    "| **$O_{\\text{no-validity}}$** | Leave out telemetry validity indicator ($O = S \\cdot W \\cdot G \\cdot T$) | $44.14\\%$ | $12.80\\%$ | $0.0847$ | $0.66\\times$ | $1.68\\times$ | $+0.0150$ | $112,300$ | $1.21\\times$ | Retains sensor edge artifacts & nodata boundaries |",
    "| **$O_{\\text{no-validity}}$** | Leave out telemetry validity indicator ($O = S \\cdot W \\cdot G \\cdot T$) | $44.14\\%$ | $12.80\\%$ | $0.0847$ | $0.62\\times$ | $1.68\\times$ | $+0.0150$ | $112,300$ | $1.21\\times$ | Retains sensor edge artifacts & nodata boundaries |"
)

# 6. Correct false-positive claim in Table 4 note
old_t4_claim = "The complete unified engine ($O_{\\text{full}}$) achieves the lowest false positive count ($104,016$ pixels, a $35.8\\%$ reduction vs unconstrained candidate detection)"
new_t4_claim = "The complete unified engine ($O_{\\text{full}}$) reduces false positives by $35.8\\%$ vs unconstrained candidate detection ($162,000 \\rightarrow 104,016$ pixels) and suppresses more false alarms than all component-ablated variants (which inflate false alarms by $+8.0\\%\\text{--}+39.0\\%$)"
m = m.replace(old_t4_claim, new_t4_claim)

# 7. Write out updated manuscript
with open(MANUSCRIPT_REPO, "w", encoding="utf-8") as f:
    f.write(m)
with open(MANUSCRIPT_BRAIN, "w", encoding="utf-8") as f:
    f.write(m)

print(f"Applied all Version 8 updates to REVISED_MANUSCRIPT_PAGEOPH.md ({len(m)} bytes).")

# 8. Update Response to Reviewers with matching Table 4 Panel C pooled ratios
with open(RESPONSE_REPO, "r", encoding="utf-8") as f:
    r = f.read()

r = r.replace("$O_{\\text{no-scale}}$: PR-AUC $= 0.0824, SR_{\\text{pool}} = 0.72\\times$", "$O_{\\text{no-scale}}$: PR-AUC $= 0.0824, SR_{\\text{pool}} = 0.60\\times$")
r = r.replace("$O_{\\text{no-water}}$: PR-AUC $= 0.0795, SR_{\\text{pool}} = 0.65\\times$", "$O_{\\text{no-water}}$: PR-AUC $= 0.0795, SR_{\\text{pool}} = 0.58\\times$")
r = r.replace("$O_{\\text{no-geom}}$: PR-AUC $= 0.0763, SR_{\\text{pool}} = 0.72\\times$", "$O_{\\text{no-geom}}$: PR-AUC $= 0.0763, SR_{\\text{pool}} = 0.56\\times$")
r = r.replace("$O_{\\text{no-slope}}$: PR-AUC $= 0.0738, SR_{\\text{pool}} = 0.75\\times$", "$O_{\\text{no-slope}}$: PR-AUC $= 0.0738, SR_{\\text{pool}} = 0.54\\times$")
r = r.replace("$O_{\\text{no-validity}}$: PR-AUC $= 0.0847, SR_{\\text{pool}} = 0.66\\times$", "$O_{\\text{no-validity}}$: PR-AUC $= 0.0847, SR_{\\text{pool}} = 0.62\\times$")

with open(RESPONSE_REPO, "w", encoding="utf-8") as f:
    f.write(r)
with open(RESPONSE_BRAIN, "w", encoding="utf-8") as f:
    f.write(r)

print(f"Applied all Version 8 updates to RESPONSE_TO_REVIEWERS_PAGEOPH.md ({len(r)} bytes).")
