# Earth One v2.4.3

Runtime environment loading fix:
- Direct Sentinel-1 and Sentinel-2 CLI workers now load `~/.config/earth_one/earth_one.env`.
- SMTP alert sender also loads the local env file.
- Autonomous cycle loads the env file before dispatching jobs.

This fixes direct-worker failures where `earth-one config-status` reported configured
credentials but `earth-one s2-auto-process` could not see them because the CLI
process had not loaded the local env file.
