# Earth One v1.8 - Global Orchestration Foundation

## Goal
Make geographic scale a configuration/orchestration concern so the same Earth One
processing stack can operate from one 10x10 km test AOI to global monitoring.

## Added
- Scope abstraction
- deterministic geographic tiling
- stable tile IDs
- stable job IDs
- restartable job sharding
- sensor-independent job manifests
- global scope representation

## Scientific guardrail
The tile grid is an orchestration layer. It is not automatically the scientific
analysis grid. Sensor-specific analysis continues to determine appropriate
resolution and resampling.
