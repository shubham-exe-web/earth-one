# Earth One v2.3 autonomous operating contract

1. Incremental scheduler creates only new jobs.
2. Execution orchestrator runs them with checkpointing and retries.
3. Sentinel-1 and Sentinel-2 workers discover real observations from CDSE.
4. Each worker processes only its AOI and enforces a data QC gate.
5. Provenance is recorded for every accepted output.
6. The execution report is generated automatically.
7. The researcher is notified by email.
8. Failed jobs remain failed/retryable; they are never promoted as success.

The system is designed to run continuously on a networked host. No manual scene
selection or QGIS operation is required.
