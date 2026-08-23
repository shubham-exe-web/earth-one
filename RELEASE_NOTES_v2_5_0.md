# Earth One v2.5.0 - Sentinel-1 Catalog authentication fix

Root cause:
- The S1 discovery worker called POST /catalog/v1/search before obtaining an
  OAuth access token.
- The live Catalog API requires OAuth authentication.

Fix:
- S1 discovery now obtains a CDSE token before Catalog search.
- Sends Authorization: Bearer <token>.
- Sends explicit JSON Content-Type and Accept headers.
- Leaves the validated S2 subsystem unchanged.
