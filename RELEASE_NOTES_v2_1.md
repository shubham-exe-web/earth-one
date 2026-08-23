# Earth One v2.1 - Autonomous Alerting

## Goal
Make Earth One operationally autonomous: results, failures and validated findings are delivered to the researcher by email.

## Added
- SMTP alert sender
- failure/success/finding notifications
- attachment support
- dry-run mail mode
- notification policy
- CLI email alert commands

## Security
Credentials are never stored in the codebase. SMTP credentials are supplied through environment variables.

## Scientific guardrail
An email alert is only a delivery mechanism. It does not change the evidence tier of the underlying result.
