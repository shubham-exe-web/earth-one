# Earth One Flood Module 2: Upstream Authoritative Data Sources & Provenance

This document details the authoritative satellite constellations, digital elevation models, hydrological baselines, meteorological products, and ground-truth delineation datasets integrated into Earth One Flood Module 2.

## 1. Upstream Satellite Data Products

| Data Layer | Constellation / Instrument | Source / Provider | Spatial Resolution | Bands / Polarizations Used |
|---|---|---|---|---|
| Synthetic Aperture Radar (SAR) | Copernicus Sentinel-1A / 1B (C-band SAR) | ESA / Microsoft Planetary Computer | 10–20 m (GRD) | VV (Co-pol), VH (Cross-pol) |
| Multi-Spectral Optical | Copernicus Sentinel-2A / 2B (MSI L2A) | ESA / Microsoft Planetary Computer | 10–20 m (BOA Reflectance) | B03 (Green), B11 (SWIR-1) |
| Digital Elevation Model | Copernicus DEM GLO-30 | Copernicus / Planetary Computer | 30 m | Elevation (m), Derived Slope (deg) |
| Surface Water Occurrence | JRC Global Surface Water (GSW) v1.3 | European Commission JRC | 30 m | Occurrence Frequency (%) |
| Precipitation Context | GPM IMERG Final Daily v06B & ERA5-Land | NASA / ECMWF Copernicus CDS | 0.1° / 9 km | Daily Accumulation (mm), Anomaly (std) |

---

## 2. Independent Ground-Truth Validation Packages

Ground-truth validation polygons are retrieved directly from official Copernicus Emergency Management Service (CEMS) Rapid Mapping activations:

| Activation ID | Event Name & Location | Flood Regime | Year | Validated Polygons | CEMS Delineation Product |
|---|---|---|---|---|---|
| **EMSR629** | Sindh Indus Basin, Pakistan | `INLAND_RIVERINE_MEGA` | 2022 | 9,690 polys | `EMSR629_AOI01_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR439** | Sandwip Channel, Bangladesh | `COASTAL_ESTUARINE_TIDAL` | 2020 | 55 polys | `EMSR439_AOI01_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR548** | Catania Plain, Sicily, Italy | `INLAND_RIVERINE_PLUVIAL` | 2021 | 394 polys | `EMSR548_AOI01_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR348** | Quelimane, Zambezia, Mozambique | `COASTAL_ESTUARINE_TIDAL` | 2019 | 249 polys | `EMSR348_01QUELIMANE_DEL_v2_observed_event_a` |
| **EMSR468** | Tanaro Valley, Piedmont, Italy | `INLAND_RIVERINE_PLUVIAL` | 2020 | 172 polys | `EMSR468_AOI02_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR517** | Rheinland-Pfalz, Germany | `INLAND_RIVERINE_PLUVIAL` | 2021 | 8 polys | `EMSR517_AOI01_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR464** | Ha Tinh, Vietnam | `COASTAL_ESTUARINE_TIDAL` | 2020 | 300 polys | `EMSR464_AOI01_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR286** | Ituango Dam / Cauca River, Colombia | `INLAND_RIVERINE_PLUVIAL` | 2018 | 18 polys | `EMSR286_01ITUANGODAM_DEL_MONIT01_v1` |
| **EMSR567** | Gympie Mary River, Queensland, Australia | `INLAND_RIVERINE_PLUVIAL` | 2021 | 42 polys | `EMSR567_AOI01_DEL_PRODUCT_r1_RTP01_v1` |
| **EMSR357** | Mahanadi Delta, Odisha, India | `COASTAL_ESTUARINE_TIDAL` | 2019 | 4,237 polys | `EMSR357_AOI01_DEL_PRODUCT_r1_VECTORS_v4` |
| **EMSR445** | Prut River Valley, Chernivtsi, Ukraine | `INLAND_RIVERINE_PLUVIAL` | 2020 | 647 polys | `EMSR445_AOI01_DEL_PRODUCT_r1_RTP01_v1` |

---

## 3. Data Query & Retrieval Contract

All STAC items, CEMS shapefiles, and meteorological anomalies are cryptographically verified via SHA-256 digests. Raw satellite data is queried dynamically using signed URLs without local hardcoded copies.
