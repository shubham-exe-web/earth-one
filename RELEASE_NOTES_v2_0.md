# Earth One v2.0 - Execution Orchestrator

## Goal
Turn the v1.9 global job manifest into a restartable execution system.

## Added
- execution ledger
- job lifecycle states
- bounded retries
- checkpoint persistence
- resume without re-executing successful jobs
- dry-run planning
- explicit `success=True` worker contract
- hard rejection of unknown/non-registered workers

## Critical scientific rule
The orchestrator will never mark a job successful merely because a worker returned
without exception. A worker must explicitly return `success=True` and the sensor
adapter must perform its own data-quality gate.

The v2.0 CLI intentionally ships without a fake live worker adapter. This is
deliberate: unknown sensor work is rejected rather than reported as successful.
