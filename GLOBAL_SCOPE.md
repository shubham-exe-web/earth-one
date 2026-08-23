# Earth One v1.8 global scope foundation

Korba/HAMFO-01 is now a test scope, not a processing assumption.

The global layer introduces:
- explicit `Scope` objects
- deterministic geographic tiling
- stable tile IDs
- stable job IDs
- sensor-independent orchestration
- restartable sharding
- machine-readable job manifests

The sensor processors remain unchanged. A global job produces a tile-level work
item that can be routed to Sentinel-1, Sentinel-2, Landsat or future sensors.

The 5°x5° tile size is an orchestration default, not a scientific grid choice.
Sensor processing may use its own internal spatial resolution and tiling.
