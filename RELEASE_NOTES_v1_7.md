# Earth One v1.7 - Independent Reference Discovery

## Goal
Add a genuine independent reference stream so candidate Sentinel-2/Sentinel-1 signals can be tested against an independent sensor family.

## Primary reference
Landsat Collection 2 Level-2 Surface Reflectance via a public Planetary Computer STAC endpoint.

## Why Landsat
USGS describes Collection 2 Level-2 Surface Reflectance as global, analysis-ready, 30 m data designed for land-surface change analysis. The Level-2 products also include quality-assessment information.

## Important limitation
The current execution environment has no outbound access to the Planetary Computer API, so the live discovery step is not executed here. The software is tested locally; the real discovery/retrieval must run in the user's networked environment.

## Scientific rule
A discovered Landsat scene is not itself a validation result. Validation occurs only after the actual independent data are retrieved, QA-filtered, spatially aligned, and compared with the Earth One candidate signal.
