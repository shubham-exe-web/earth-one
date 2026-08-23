# Earth One v2.5.1 - Catalog 406 compatibility fix

The S1 Catalog request now follows the current CDSE documented POST example
more literally:
- Authorization: Bearer <token>
- Content-Type: application/json
- No explicit Accept media type

Reason:
The v2.5.0 worker still received HTTP 406 from `/catalog/v1/search` even after
adding OAuth. A 406 is consistent with content negotiation, so the explicit
Accept header was removed to let the server negotiate its normal JSON response.
