# Earth One execution contract

A sensor adapter is considered production-capable only when it implements:

1. discovery/selection
2. acquisition or server-side processing
3. output provenance
4. output data QC
5. explicit `success=True`
6. deterministic failure reporting

The orchestrator supplies retries/checkpoints/isolation. Sensor adapters supply
scientific execution.
