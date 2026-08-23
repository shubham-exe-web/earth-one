# Earth One v1.9 - Incremental Global Scheduler

## Goal
Move global monitoring from full reprocessing toward incremental, restartable monitoring.

## Added
- persistent state ledger
- completed-job tracking
- deterministic job keys
- incremental schedule generation
- idempotent restart behavior
- sensor/tile summary statistics

## Global implication
A global run no longer needs to start from an empty state. The scheduler can add
new observation windows while leaving validated completed work untouched.
