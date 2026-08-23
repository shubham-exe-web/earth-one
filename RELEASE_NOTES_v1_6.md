# Earth One v1.6 - Evidence & Validation Engine

## Goal
Prevent interesting satellite patterns from being promoted to scientific findings without explicit evidence quality.

## Added
- reproducibility verification against archived derived products
- independent-reference comparison API
- evidence tiering:
  1. INTERNAL_REPRODUCIBILITY
  2. REAL_DATA_VALIDATED
  3. INDEPENDENT_REFERENCE_VALIDATED
  4. END_TO_END_VALIDATED
- explicit paper-claim gate
- explicit causal-claim prohibition at this stage
- CLI commands for reproducibility and evidence promotion

## Rule
No paper-worthy scientific claim is promoted by software alone.
A candidate needs independent reference validation and end-to-end evidence.
