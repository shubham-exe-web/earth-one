# Earth One v0.1 — Autonomous EO Data Acquisition Engine

## Objective

This is the first executable component of Earth One.

The v0.1 objective is **not** to build the entire Earth intelligence platform at once.
It is to establish an idempotent, auditable, machine-driven Earth-observation ingestion
layer that can:

1. discover new Sentinel-1 GRD and Sentinel-2 L2A observations,
2. filter them by AOI, time, and quality,
3. record complete provenance/metadata,
4. maintain a local state database so the same observation is not processed twice,
5. produce a deterministic acquisition manifest for downstream preprocessing,
6. remain ready for automatic scheduling and model routing.

The first scientific loop will later consume these observations for:

Sentinel-1 + Sentinel-2
→ preprocessing
→ vegetation/forest mapping
→ change detection
→ wildfire detection
→ burned-area estimation
→ biomass/carbon-loss estimation
→ uncertainty
→ historical comparison
→ prediction.

## Why STAC first?

The Copernicus Data Space Ecosystem provides a current STAC catalogue at:

`https://stac.dataspace.copernicus.eu/v1/`

The STAC catalogue supports standardized discovery and includes Sentinel-1 GRD
and Sentinel-2 Level-2A collections. This engine therefore separates:

**discovery** from **download** from **processing**.

That separation is deliberate. Earth One should not download large scenes blindly.
It should first determine what data exists and what the processing pipeline actually needs.

## Current design

### Data sources

Primary v0.1 sources:

- Sentinel-2 Level-2A: optical/multispectral
- Sentinel-1 GRD: SAR

Secondary sources are intentionally not hard-wired into v0.1 yet.

NASA CMR is retained as the second-stage federation/discovery interface for NASA
datasets when Earth One expands beyond Copernicus.

### State

SQLite stores:

- STAC item ID
- collection
- acquisition datetime
- discovery time
- bbox
- cloud cover when available
- asset metadata
- processing status
- error state

This makes acquisition idempotent and auditable.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` only when authenticated data access is required.

## First test: public metadata discovery

The STAC catalogue can be queried for metadata without downloading imagery.

Example:

```bash
python -m earth_one.cli discover \
  --collection sentinel-2-l2a \
  --bbox 80.0,20.0,82.0,22.0 \
  --start 2026-07-01 \
  --end 2026-07-07 \
  --max-cloud 30 \
  --limit 20
```

For Sentinel-1:

```bash
python -m earth_one.cli discover \
  --collection sentinel-1-grd \
  --bbox 80.0,20.0,82.0,22.0 \
  --start 2026-07-01 \
  --end 2026-07-07 \
  --limit 20
```

## Important

This first version deliberately does **not** pretend that an autonomous system
already exists. It establishes the first reliable subsystem and its contracts.

The next modules will be:

1. preprocessing engine,
2. observation harmonization/data cube,
3. model router,
4. change/event engine,
5. carbon intelligence engine,
6. uncertainty/validation engine,
7. forecasting engine,
8. autonomous orchestration,
9. Earth One database/API,
10. alert/report layer.

