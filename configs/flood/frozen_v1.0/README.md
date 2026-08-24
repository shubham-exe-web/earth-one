# Earth One Flood Module 2: Frozen Configuration Parameters (v1.0)

This directory contains the frozen, immutable configuration files governing the physics decision engine, autonomous regime routing, continuous observability index, and alert lifecycle state machine for Earth One Flood Module 2.

## Files
- `evidence_fusion_config.json`: Physical thresholds for SAR backscatter drop, optical MNDWI, JRC novelty ceiling, and terrain plausibility.
- `regime_router_config.json`: Biophysical boundaries and parameters for Alluvial Mega-River, Pluvial Gorge, and Coastal Estuary regimes.
- `observability_index_config.json`: Mathematical weights and parameters for $O = S \cdot W \cdot G \cdot T \cdot D$.
- `alert_state_machine_config.json`: State machine transition rules and blackout safety hold parameters.
