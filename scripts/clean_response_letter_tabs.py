#!/usr/bin/env python3
"""Script to apply verified updates to RESPONSE_TO_REVIEWERS_PAGEOPH.md with proper raw strings."""

from pathlib import Path

def clean_and_update(text: str) -> str:
    # First replace any accidental tab-escaped LaTeX in response letter
    text = text.replace('\text', r'\text')
    text = text.replace('\times', r'\times')
    text = text.replace('\pi', r'\pi')
    text = text.replace('\tau', r'\tau')
    text = text.replace('\theta', r'\theta')
    text = text.replace('\Delta', r'\Delta')
    text = text.replace('\rho', r'\rho')
    text = text.replace('\le', r'\le')
    text = text.replace('\ge', r'\ge')

    return text

def main():
    paths = [
        Path("/Users/shubhamsharma/Earth-One/docs/PAGEOPH/RESPONSE_TO_REVIEWERS_PAGEOPH.md"),
        Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/RESPONSE_TO_REVIEWERS_PAGEOPH.md"),
    ]
    for p in paths:
        raw = p.read_text(encoding="utf-8")
        fixed = clean_and_update(raw)
        p.write_text(fixed, encoding="utf-8")
        print(f"Cleaned {p}")

if __name__ == "__main__":
    main()
