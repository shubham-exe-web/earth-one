# Earth One v2.3 - Full Autonomous Sensor Acquisition

Sentinel-2 L2A is now connected to CDSE STAC discovery and Process API processing.
The adapter selects a real scene, filters the Process API to that product ID,
requests AOI-sized B02/B03/B04/B08 + SCL + dataMask, captures provenance, and
rejects empty/invalid outputs.

The cycle report is attached to completion/failure emails.

CDSE documents the Sentinel-2 L2A Process API as `sentinel-2-l2a`, supports cloud
filtering, AOI-sized responses, and scene metadata through the scenes object.
