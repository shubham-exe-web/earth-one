# Earth One v2.4.1

Dependency correction:
- Added `pyproj>=3.6,<4` to the production dependency list.

Reason:
`earth_one.tracking` imports `pyproj.Transformer`, so the previous package
could install successfully but fail at CLI startup with:
`ModuleNotFoundError: No module named 'pyproj'`.

No application logic was changed.
