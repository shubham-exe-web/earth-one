# Earth One v2.5.3 - S1 Process payload enum normalization

Fix:
- Normalize Sentinel-1 `orbitDirection` to uppercase before sending to the
  Process API.

Important:
- `orthorectify` remains a JSON string (`"true"`/`"false"`), not a Python
  boolean. Current CDSE S1GRD Process API examples explicitly use the string
  form for this processing field.
