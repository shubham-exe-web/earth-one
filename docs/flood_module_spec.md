# 🌊 Earth One Flood Module 2: Scientific Core & Architecture Specification

## 1. Overview
The Earth One Flood Module provides autonomous, multimodal remote-sensing detection, spatio-temporal tracking, independent validation, and operational alerting for global flood and inundation events.

```text
                    🌊 EARTH ONE FLOOD MODULE
                              │
          ┌───────────────────┼───────────────────┐
          ↓                   ↓                   ↓
       Detection          Validation          Operations
          │                   │                   │
     SAR + optical      independent refs      scheduling
     + water baseline   event/object metrics   tracking
     + rainfall        spatial/temporal       alerting
     + terrain         generalization         fault handling
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ↓
                     Flood Event Record
                              ↓
                    Earth One Alert Engine
                              ↓
                     Environmental Ledger
                              ↓
                  Carbon/GHG Impact Layer
```

---

## 2. Five Multimodal Evidence Channels

### Channel A: Sentinel-1 SAR Change
- Inundated open water acts as a specular reflector, sharply attenuating backscatter intensity relative to baseline dry surfaces.
- Evaluates:
  $$\Delta\text{VV}_{\text{dB}} = 10\log_{10}\left(\frac{\sigma^0_{VV, \text{event}}}{\sigma^0_{VV, \text{baseline}}}\right), \quad \Delta\text{VH}_{\text{dB}} = 10\log_{10}\left(\frac{\sigma^0_{VH, \text{event}}}{\sigma^0_{VH, \text{baseline}}}\right)$$
- Normalizes backscatter decrease and absolute low-backscatter ceilings into $S_{\text{SAR}} \in [0, 1]$.

### Channel B: Sentinel-2 Optical Water Evidence
- Where optical cloud cover allows, evaluates:
  $$\text{NDWI} = \frac{B03 - B08}{B03 + B08}, \quad \text{MNDWI} = \frac{B03 - B11}{B03 + B11}$$
- Scene Classification Layer (SCL) masks clouds/cirrus as unobserved/masked rather than non-flood.

### Channel C: Water-Baseline Novelty
- Prevents false alarms over permanent waterbodies (rivers, lakes, reservoirs, permanent wetlands):
  $$\text{FloodNovelty} = \text{EventWater} \cap \neg \text{NormalWater}$$
  $$S_{\text{novelty}} = \text{clip}\left(1.0 - \frac{\text{Freq}_{\text{permanent}}}{\text{MaxFreq}_{\text{permanent}}}, 0.0, 1.0\right)$$

### Channel D: Meteorological Rainfall Context
- Computes rainfall accumulation prior ($mm$), standardized precipitation anomaly ($\sigma$), and temporal decay from precipitation peak to provide meteorological context (not ground truth):
  $$S_{\text{rain}} \in [0, 1]$$

### Channel E: Terrain & Hydrologic Plausibility
- Physics-informed constraint: Standing flood water accumulates in low-slope terrain ($\text{slope} \le 8^\circ$). Steep mountain slopes ($>15^\circ$) have runoff rather than ponding:
  $$S_{\text{terrain}} \in [0, 1]$$

---

## 3. Dynamic Evidence Fusion & Event Integration
- Dynamic normalization across available channels:
  $$S_{\text{flood}} = \frac{\sum_{i \in \text{available}} w_i S_i}{\sum_{i \in \text{available}} w_i}$$
- Transparent score raster segmented into standard `EventRecord` instances (`events.py`) and ingested into `tracking.py` and `alerting.py`.

---

## 4. Test Verification
- All 10 dedicated flood tests passing.
- 88/88 full repository regression tests passing (100% green).
