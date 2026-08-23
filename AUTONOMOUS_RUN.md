# Earth One v2.2 autonomous run

## Local secrets
S1:
CDSE_CLIENT_ID / CDSE_CLIENT_SECRET

Email:
EARTH_ONE_SMTP_HOST
EARTH_ONE_SMTP_PORT
EARTH_ONE_SMTP_USERNAME
EARTH_ONE_SMTP_PASSWORD
EARTH_ONE_ALERT_FROM
EARTH_ONE_ALERT_TO

## Run a planning cycle
```bash
earth-one autonomous-cycle \
  --jobs Earth_One_GLOBAL_EXECUTION_PLAN_v2_0.json \
  --ledger state/execution.json \
  --output-root data/results \
  --result-json reports/cycle.json \
  --dry-run
```

## Run live
Remove `--dry-run` and add `--send-email`.

The system will skip already successful jobs, retry transient failures, persist results,
and send a completion/failure email.
