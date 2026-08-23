# Earth One v2.5.2 - Sentinel-1 Evalscript formatting fix

Fixed the Gate-2 startup crash in the S1 Process worker.

Root cause:
- The JavaScript Evalscript was created with Python `str.format()`.
- Native JavaScript braces were interpreted as Python format fields.
- This raised `ValueError: unexpected '{' in field name` before the Process
  API request was sent.

Fix:
- Construct the dynamic fragments (`inputs`, `nbands`, `returns`) first.
- Use a Python f-string for the Evalscript.
- Escape native JavaScript braces as `{{` and `}}` inside the f-string.
- Add a regression test to prevent reintroduction of the `.format()` trap.

No CDSE request semantics were changed.
