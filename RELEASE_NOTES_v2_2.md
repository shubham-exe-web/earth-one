# Earth One v2.2 - Autonomous Worker Pipeline

## Goal
Connect the execution orchestrator to real sensor workers and the email delivery layer.

## Added
- Sentinel-1 live worker adapter using the existing CDSE autonomous engine
- Sentinel-2 real-input worker adapter with strict refusal to fabricate missing inputs
- autonomous cycle command
- execution result persistence
- optional email delivery at the end of a cycle
- worker registration/fail-closed routing

## Important
The Sentinel-2 global worker still expects a real input handoff. It does not silently invent or synthesize a scene. A full CDSE Sentinel-2 acquisition adapter remains a separate integration point.

The Sentinel-1 worker is fully wired to the existing CDSE autonomous engine and inherits its provenance and raster QC gates.
