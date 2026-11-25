import zipfile
import hashlib
from pathlib import Path

ROOT = Path("/Users/shubhamsharma/Earth-One")
OUT_ZIP = ROOT / "data" / "zenodo_package" / "Earth_One_Flood_v2.2.0.zip"

files_to_pack = [
    # Source code
    "src/earth_one/__init__.py",
    "src/earth_one/flood.py",
    "src/earth_one/flood_tristate.py",
    "src/earth_one/flood_ablation.py",
    "src/earth_one/flood_calibration.py",
    "src/earth_one/flood_observability_calibration.py",
    "src/earth_one/flood_observability_validation.py",
    "src/earth_one/flood_spatial_generalization.py",
    "src/earth_one/flood_temporal_generalization.py",
    "src/earth_one/flood_replay.py",
    # Evaluation scripts
    "scripts/evaluate_held_out_validation.py",
    "scripts/run_loco_ablation.py",
    "scripts/run_statistical_tests.py",
    "scripts/evaluate_raster_masks.py",
    # Tests
    "tests/test_physics_gates.py",
    "tests/test_abstention.py",
    "tests/test_raster_confusion_matrix.py",
    # Results Ledgers
    "results/flood_v1.0/frozen_cohort_manifest.json",
    "results/flood_v1.0/ablation_results.json",
    "results/flood_v1.0/observability_calibration.json",
    "results/flood_v1.0/spatial_generalization_results.json",
    "results/flood_v1.0/observability_validation.json",
    # Config & docs
    "README.md",
    "REPRODUCE.md",
    "LICENSE",
    "pyproject.toml",
    "docs/FLOOD_REPRODUCTION.md",
    "docs/FLOOD_VALIDATION.md"
]

# Add benchmark rasters
raster_dir = ROOT / "data" / "flood_benchmark_rasters"
for r in raster_dir.glob("*.npz"):
    files_to_pack.append(str(r.relative_to(ROOT)))

print(f"Packaging {len(files_to_pack)} files into {OUT_ZIP}...")
with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files_to_pack:
        full_path = ROOT / f
        if full_path.exists():
            z.write(full_path, arcname=f"earth-one-v2.2.0/{f}")
        else:
            print(f"Warning: {f} not found!")

# Calculate file size and SHA256
zip_bytes = OUT_ZIP.read_bytes()
zip_size_mb = len(zip_bytes) / (1024 * 1024)
zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()

print(f"Archive built successfully!")
print(f"  Path: {OUT_ZIP}")
print(f"  Size: {zip_size_mb:.2f} MB ({len(zip_bytes):,} bytes)")
print(f"  SHA-256: {zip_sha256}")

# Update manuscript with actual SHA-256
manuscript_path = ROOT / "docs" / "PAGEOPH" / "REVISED_MANUSCRIPT_PAGEOPH.md"
brain_manuscript_path = Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/REVISED_MANUSCRIPT_PAGEOPH.md")

with open(manuscript_path, "r", encoding="utf-8") as f:
    text = f.read()

import re
text = re.sub(
    r"Earth_One_Flood_v\d+\.\d+\.\d+\.zip, [0-9.]+ MB, SHA-256: `[a-f0-9]+`",
    f"Earth_One_Flood_v2.2.0.zip, {zip_size_mb:.2f} MB, SHA-256: `{zip_sha256}`",
    text
)

with open(manuscript_path, "w", encoding="utf-8") as f:
    f.write(text)
with open(brain_manuscript_path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"Updated manuscript Data Availability with verified ZIP SHA-256: {zip_sha256}")
