# Earth One v1.2 Release Notes

## Theme
**Provenance-gated Sentinel-1 production**

## Why this release exists
During the first real HAMFO-01 Sentinel-1 attempt, manual GIS clipping produced GeoTIFFs with correct metadata but all-zero pixel values. v1.2 converts that lesson into a permanent production control.

## Changes
1. Process API now requests image + userdata metadata in a multipart response.
2. Exact selected product ID must appear in returned scene provenance.
3. Sentinel-1 processing explicitly requests IW, orbit direction, and polarization.
4. Gamma0 terrain processing uses orthorectification and `COPERNICUS_30`.
5. Multiband QC validates all science bands and rejects empty, constant, non-finite, and all-zero outputs.
6. Invalid outputs are deleted before the pipeline continues.
7. S1 test suite expanded to five tests; all five pass in the release environment.

## Not yet claimed
The live CDSE end-to-end run has not been executed in this build environment. Software tests passing is not equivalent to real-world acquisition validation.
