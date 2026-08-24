# Earth One Flood Module 2: System Architecture & Mathematical Foundations (v1.0 Frozen Release)

## 1. Overview

Earth One Flood Module 2 is a fully autonomous, multimodal satellite disturbance monitoring engine designed for zero-touch flood inundation detection, biophysical regime routing, spatial observability decomposition, multi-epoch event tracking, and blackout-safe alerting across global river basins, coastal estuaries, and mountainous gorges.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                         EARTH ONE FLOOD MODULE 2: PIPELINE ARCHITECTURE                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   [Sentinel-1 SAR GRD]        [Sentinel-2 MSI L2A]        [Copernicus DEM]       [JRC GSW]       │
│    (VV/VH Co- & Cross-Pol)     (Green / SWIR Bands)        (GLO-30 Topography)    (Occurrence)   │
│              │                          │                          │                  │          │
│              ▼                          ▼                          │                  │          │
│       SAR Change Novelty         Optical MNDWI Index               │                  │          │
│              │                          │                          │                  │          │
│              └────────────┬─────────────┘                          │                  │          │
│                           ▼                                        ▼                  │          │
│                 Candidate Water Evidence                     Slope & Relief           │          │
│                           │                                        │                  │          │
│                           ├────────────────────────────────────────┴──────────────────┤          │
│                           ▼                                                           ▼          │
│                 Gated Physics Fusion                                       Biophysical Router    │
│              (S_water · M_nov · M_terr · M_rain)                         (Alluvial / Pluvial /   │
│                           │                                                Coastal Estuary)      │
│                           ▼                                                           │          │
│                 Continuous Observability Index (O) ◄──────────────────────────────────┘          │
│              (O = S_scale · W_water · G_geom · T_terr · D_valid)                                 │
│                           │                                                                      │
│                           ▼                                                                      │
│                 Resolution-Aware Tri-State Engine                                                │
│              [FLOOD]        [NO_FLOOD]        [UNRESOLVED]                                       │
│                 │                                  │                                             │
│                 ▼                                  ▼                                             │
│       Multi-Epoch Tracker                 Data Blackout Hold                                     │
│        (Trajectory & Area)                 (Fail-Safe State)                                     │
│                 │                                  │                                             │
│                 └─────────────────┬────────────────┘                                             │
│                                   ▼                                                              │
│                         Alert Lifecycle State Machine                                            │
│                      (0.0% Duplicate Spam, Zero-Leakage)                                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mathematical Formulations

### 2.1 Multi-Modal Evidence Fusion

Rather than unconstrained additive blending, Earth One employs **Gated Multiplicative Physics Fusion**:

$$S_{\text{candidate}} = S_{\text{water}} \cdot M_{\text{novelty}} \cdot M_{\text{terrain}} \cdot M_{\text{rain}}$$

Where:
1. **$S_{\text{water}}$ (Water Observation)**: Primary specular reflection backscatter drop in C-band SAR ($\Delta\sigma^0_{\text{VV}} \ge 3.0\text{ dB}$, cross-pol ratio $\ge 1.15$) corroborated by optical MNDWI ($(\rho_{\text{Green}} - \rho_{\text{SWIR}})/(\rho_{\text{Green}} + \rho_{\text{SWIR}}) \ge 0.10$).
2. **$M_{\text{novelty}}$ (Hydrological Novelty Mask)**: Multiplicative gating against historical permanent water baselines (JRC Global Surface Water occurrence $f_{\text{perm}}$):
   $$M_{\text{novelty}} = \text{clip}\left(1.0 - \frac{f_{\text{perm}}}{0.80}, 0.0, 1.0\right)$$
3. **$M_{\text{terrain}}$ (Topographic Plausibility Mask)**: Hydrodynamic penalty for steep non-inundatable terrain slopes derived from Copernicus DEM GLO-30:
   $$M_{\text{terrain}} = \text{clip}\left(1.0 - \frac{\theta_{\text{slope}}}{15.0^\circ}, 0.0, 1.0\right)$$
4. **$M_{\text{rain}}$ (Meteorological Corroboration)**: Corroboration multiplier derived from accumulated antecedent precipitation anomalies ($Z_{\text{rain}}$ from GPM IMERG / ERA5-Land).

### 2.2 Continuous Observability Index ($O$)

Earth One quantifies physical observational observability per pixel via a continuous index $O \in [0.0, 1.0]$:

$$O = S_{\text{scale}} \times W_{\text{water}} \times G_{\text{geom}} \times T_{\text{terrain}} \times D_{\text{validity}}$$

- **$D_{\text{validity}} \in \{0, 1\}$**: Satellite telemetry validity mask.
- **$T_{\text{terrain}} \in [0, 1]$**: Topographic slope penalty ($1.0 - \theta / 15^\circ$).
- **$G_{\text{geom}} \in [0, 1]$**: Local relief roughness ($1.0 - \Delta h_{100\text{m}} / 150\text{m}$).
- **$W_{\text{water}} \in [0, 1]$**: Dynamic intertidal ambiguity suppression ($0.35$ in low elevation tidal mudflats, $1.0$ elsewhere).
- **$S_{\text{scale}} \in [0.5, 1.0]$**: Sub-pixel drainage channel observability ($d_{\text{valley}} / 40\text{m}$).

### 2.3 Resolution-Aware Tri-State Decision Contract

To prevent turning observational blind spots into false scientific declarations, Earth One enforces the Tri-State contract:

$$\text{Decision}(p) = \begin{cases} \text{FLOOD} & \text{if } O(p) \ge 0.50 \land S(p) \ge 0.20 \\ \text{NO\_FLOOD} & \text{if } O(p) \ge 0.50 \land S(p) < 0.20 \\ \text{UNRESOLVED} & \text{if } O(p) < 0.50 \end{cases}$$

---

## 3. Autonomous Biophysical Regime Routing

Earth One routes biophysical context using continuous confidence-weighted soft blending ($S_{\text{final}} = (1 - C) S_{\text{global}} + C S_{\text{regime}}$):

1. **`INLAND_RIVERINE_MEGA`** (e.g. Pakistan Indus, India Mahanadi): Flat alluvial floodplains ($\theta \le 1.5^\circ$), wide sheet water, high radar contrast.
2. **`INLAND_RIVERINE_PLUVIAL`** (e.g. Italy Tanaro, Germany Ahr/Rhine, Ukraine Prut, Colombia Cauca): Narrow river valleys, steep ridges, high relief roughness.
3. **`COASTAL_ESTUARINE_TIDAL`** (e.g. Mozambique Quelimane, Bangladesh Sandwip, Vietnam Ha Tinh): Low elevation coastal plains ($h \le 2.5\text{ m}$), dynamic tidal mudflats.

---

## 4. Alert Lifecycle State Machine & Safety Guarantees

The alert state machine enforces strict idempotency and fail-safe blackout handling:
- **0.0% Duplicate Alert Rate**: Suppresses redundant alerts within a 6-hour temporal hysteresis window.
- **Fail-Safe Blackout Hold**: If satellite observation is missing or corrupted, the system transitions to `DATA_BLACKOUT_HOLD`. It **never** emits a false `NO_FLOOD` or `ALL_CLEAR`.
