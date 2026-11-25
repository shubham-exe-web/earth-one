#!/usr/bin/env python3
"""Script to apply verified updates to RESPONSE_TO_REVIEWERS_PAGEOPH.md."""

from pathlib import Path

def update_response(p: Path):
    text = p.read_text(encoding='utf-8')

    # Audit Issue B: Figure 6 update
    old_b = "skill ratio $2.94\\times \\rightarrow 3.84\\times$) and Historical ($2018\\text{--}2019$, $N=3$; PR-AUC $0.09327 \\rightarrow 0.12647$, $+35.6\%$ gain, skill ratio $2.01\\times \\rightarrow 2.84\\times$)"
    new_b = "skill ratio $3.03\\times \\rightarrow 2.43\\times$) and Historical ($2018\\text{--}2019$, $N=3$; PR-AUC $0.09327 \\rightarrow 0.12647$, $+35.6\%$ gain, skill ratio $1.84\\times \\rightarrow 1.21\\times$)"
    if old_b in text:
        text = text.replace(old_b, new_b)
        print("Updated Audit Issue B in response letter.")

    # Reviewer 2 Comment 1
    old_r2_c1 = "In low-prevalence regimes such as Germany (EMSR517, prevalence $= 0.11\%$), our model achieves $0.0098$ PR-AUC, which is **$9.03\\times$ higher than random chance**."
    new_r2_c1 = "In low-prevalence regimes such as Germany (EMSR517, prevalence $= 0.11\%$), our model achieves $0.0098$ PR-AUC, which is **$9.05\\times$ higher than random chance** ($6.81\\times$ in the resolvable domain)."
    if old_r2_c1 in text:
        text = text.replace(old_r2_c1, new_r2_c1)
        print("Updated Reviewer 2 Comment 1 in response letter.")

    # Reviewer 2 Comment 3
    old_r2_c3 = "We report prevalence, sample sizes, and normalized skill ratios in both full and resolvable domains. Using $1,000$ spatial block bootstrap resamples ($32 \\times 32$ pixels, $640 \\times 640\\text{ m}$), we report $95\%$ confidence intervals for $\\Delta\\text{PR-AUC}$ across all events."
    new_r2_c3 = "We report prevalence, sample sizes, and normalized skill ratios in both full and resolvable domains. Crucially, resolvable-domain skill ratios are normalized by the resolvable-domain positive prevalence $\\pi_{\\text{res}} = P_{\\text{res}} / N_{\\text{res}}$ (yielding a macro validation skill ratio of $1.97\\times$, with 7 of 8 events exceeding chance; Colombia Cauca achieves $0.31\\times$ due to high localized river channel prevalence of $72.53\%$ in the narrow un-abstained canyon). Using $1,000$ spatial block bootstrap resamples ($32 \\times 32$ pixels, $640 \\times 640\\text{ m}$), we report $95\%$ confidence intervals for $\\Delta\\text{PR-AUC}$ across all events."
    if old_r2_c3 in text:
        text = text.replace(old_r2_c3, new_r2_c3)
        print("Updated Reviewer 2 Comment 3 in response letter.")

    # Reviewer 2 Comment 4
    old_r2_c4 = "- In Bin 1 ($O < 0.20$), zero predicted positives were emitted at $T_{\\text{det}} = 0.20$; empirical precision is mathematically **Undefined ($0/0$)** and is omitted from the precision curve."
    new_r2_c4 = """- In Table 3, we now report bin-specific class prevalence $\\pi_i$ and normalized skill ratios ($1.19\\times, 1.05\\times, 0.97\\times, 1.06\\times, 0.92\\times$), demonstrating that the primary physical mechanism of the Observability Index $O$ is selective classification and abstention (suppressing false alarms by $35.8\%$) rather than creating artificial ranking skill in unobservable terrain.
- In Bin 1 ($O < 0.20$), zero predicted positives were emitted at $T_{\\text{det}} = 0.20$; empirical precision is mathematically **Undefined ($0/0$)** and is omitted from the precision curve."""
    if old_r2_c4 in text:
        text = text.replace(old_r2_c4, new_r2_c4)
        print("Updated Reviewer 2 Comment 4 in response letter.")

    p.write_text(text, encoding='utf-8')
    print(f"Saved: {p}")

def main():
    r1 = Path("/Users/shubhamsharma/Earth-One/docs/PAGEOPH/RESPONSE_TO_REVIEWERS_PAGEOPH.md")
    r2 = Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/RESPONSE_TO_REVIEWERS_PAGEOPH.md")
    update_response(r1)
    update_response(r2)

if __name__ == "__main__":
    main()
