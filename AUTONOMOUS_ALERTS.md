# Earth One autonomous alert contract

Earth One should email the researcher for:
1. execution failures that require attention
2. completed monitoring cycles
3. validated candidate findings
4. independent-reference validation results
5. system-level health failures

Email is a notification layer only; the authoritative result remains the machine-readable evidence/provenance record.

Set locally:
```bash
export EARTH_ONE_SMTP_HOST='...'
export EARTH_ONE_SMTP_PORT='465'
export EARTH_ONE_SMTP_USERNAME='...'
export EARTH_ONE_SMTP_PASSWORD='...'
export EARTH_ONE_ALERT_FROM='...'
export EARTH_ONE_ALERT_TO='...'
```

Never place these values in git, configuration files committed to the repository, or chat.
