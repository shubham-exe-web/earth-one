# Earth One v2.4 autonomous deployment

## One-time setup
On the machine that has network access:

```bash
./setup_earth_one.sh
```

This creates a local virtual environment and a private environment file under:
`~/.config/earth_one/earth_one.env`

Then install the macOS background service:

```bash
./install_mac_service.sh
```

The service runs automatically every 6 hours, resumes from the persistent execution
ledger, processes only new work, and emails the configured alert recipient.

## Important
The user must supply valid CDSE credentials and SMTP/app-password credentials once.
After that, there should be no manual satellite-scene operation.

## Manual diagnostic
```bash
.venv/bin/earth-one config-status
.venv/bin/earth-one service-run   --jobs Earth_One_GLOBAL_EXECUTION_PLAN_v2_0.json   --ledger state/execution.json   --output-root data/results   --result-dir reports   --interval-seconds 21600   --send-email   --once
```
