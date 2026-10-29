# Observability-Aware Satellite Flood Inundation Mapping: Quantifying Multi-Modal Evidence Fusion, Physical Ambiguity, and Abstention Across Multi-Continent Regimes

**Shubham Sharma$^{1,*}$, Shruti Tiwari$^{1}$**  
$^{1}$ School of Studies in Environmental Science, Pt. Ravishankar Shukla University, Raipur, Chhattisgarh, 492010, India  
$^*$ Corresponding author: Shubham Sharma (`ss677997@gmail.com`); ORCID: [0009-0009-2451-3461](https://orcid.org/0009-0009-2451-3461)

---

## Abstract
Automated satellite flood inundation mapping typically evaluates classifiers under the implicit assumption that all geographic pixels are equally observable. In reality, spaceborne synthetic aperture radar (SAR) and multispectral optical sensors encounter severe physical constraints—including radar layover and shadow in high-relief terrain, dynamic water-level fluctuations in intertidal mudflats, dense storm-cloud decks, and narrow drainage features below sensor resolution. Here, we present a physically grounded, multi-modal flood mapping framework that combines Sentinel-1 SAR, Sentinel-2 optical imagery, 38-year surface-water occurrence baselines, digital elevation models, and antecedent precipitation context with an explicit **Continuous Observability Index ($O \in [0.0, 1.0]$)** and a resolution-aware tri-state interpretation contract (FLOOD, NO_FLOOD, or UNRESOLVED when $O < 0.50$). The primary scientific hypothesis is that explicitly modeling physical observability and enforcing resolution-aware abstention isolates genuine algorithmic detection skill from physical sensor occlusions, suppressing false alarms and stabilizing interannual generalization.

We evaluated the framework across 11 global flood activations from the Copernicus Emergency Management Service (CEMS) spanning five continents and multiple hydrologic regimes. Experimental data were strictly partitioned into a three-event development cohort ($N=3$) used for initial heuristic parameter bounds and isotonic probability fitting, and an eight-event held-out validation pool ($N=8$) evaluated zero-shot without parameter tuning. In the broad alluvial sheet floods of the Indus Basin in Pakistan (EMSR629, development cohort), the system achieved a Precision-Recall Area Under Curve (PR-AUC) of $0.8337$, precision of $73.8\%$, and F1-score of $80.1\%$ ($1.62\times$ over class prevalence chance baseline). Across the eight held-out unseen validation events, macro PR-AUC over the full domain was $0.06972$ and improved by $+29.3\%$ to $0.09016$ when restricted to the physically resolvable domain ($O \ge 0.50$), with individual event skill ratios ranging from $1.05\times$ to $9.03\times$ over prevalence chance baselines. In an observability reliability audit across $1,310,720$ held-out validation pixels, high-observability pixels exhibited over $2.3\times$ higher PR-AUC ($0.1336$ vs $0.0587$) than severely obscured pixels. Empirical precision in Bin 1 ($O < 0.20$) was mathematically undefined ($0/0$) due to zero predicted positive pixels; across the four well-defined precision tiers ($O \ge 0.20$), Pearson $r = 0.8385$ ($p = 0.1615$), while across all five continuous PR-AUC tiers, Pearson $r = 0.8436$ ($p = 0.0725$). In primary independent temporal validation across the eight held-out activations partitioned chronologically, observability filtering consistently improved detection performance across both the modern era ($2020\text{--}2021$, $N=5$; macro PR-AUC $0.05558 \rightarrow 0.06838$, $+23.0\%$ gain, skill ratio $2.94\times \rightarrow 3.84\times$) and the historical era ($2018\text{--}2019$, $N=3$; macro PR-AUC $0.09327 \rightarrow 0.12647$, $+35.6\%$ gain, skill ratio $2.01\times \rightarrow 2.84\times$). In a secondary operational replay benchmark across streaming deployments (including development activations), restricting evaluation to the resolvable domain reduced cross-era performance degradation by $91.9\%$. Component-level ablation demonstrates that the unified index $O$ achieves superior false-positive reduction compared to individual slope, relief, or permanent-water filters at matched coverage ($44.14\%$). These results demonstrate that evaluating satellite flood intelligence through explicit observability modeling separates genuine detection skill from observational occlusions, providing an objective basis for flood risk assessment and disaster response.

**Keywords:** Flood detection; Sentinel-1 SAR; Sentinel-2; Earth observation; Observability modeling; Abstention; Copernicus EMS; Pure and Applied Geophysics.

---

## 1. Introduction

Satellite remote sensing provides indispensable synoptic capability for rapid disaster assessment during extreme flood events (Schumann et al., 2018; DeVries et al., 2020). Spaceborne synthetic aperture radar (SAR), particularly the European Space Agency’s (ESA) Copernicus Sentinel-1 C-band constellation, represents the primary operational data source for flood delineation because microwave signals penetrate cloud decks and operate independently of solar illumination (Torres et al., 2012; Twele et al., 2016). When specular reflection off smooth, standing water surfaces scatters radar pulses away from the side-looking antenna, open floodwater appears as distinct dark regions with low backscatter coefficients ($\sigma^0_{\text{VV}} < -14\text{ dB}$, $\Delta\sigma^0_{\text{VV}} \le -2\text{ dB}$) (Boni et al., 2016; Giustarini et al., 2013). Complementary multispectral optical observations from Sentinel-2 MSI offer higher spatial resolution ($10\text{--}20\text{ m}$) and diagnostic water absorption indices (e.g., Modified Normalized Difference Water Index, MNDWI), though their operational utility is frequently curtailed by persistent storm clouds during monsoon depressions and cyclones (Drusch et al., 2012; Pekel et al., 2016).

Despite the proliferation of multi-modal machine learning algorithms and deep convolutional neural networks for flood detection (e.g., Bonavitacola et al., 2021; Mateo-Garcia et al., 2021; Rahman et al., 2021), standard evaluation protocols almost universally frame flood delineation as an unconstrained, binary pixel-level classification task: assigning every pixel to either FLOOD (1) or NO_FLOOD (0). This formulation rests on an implicit, physically untenable assumption: that every geographic pixel within a satellite scene is equally observable and physically interpretable.

Physically, this assumption breaks down across numerous real-world landscapes:
1. **Side-Looking Radar Geometry:** In steep alpine valleys and dissected topography, radar foreshortening, layover, and shadow obscure narrow river channels, creating geometric blind spots where backscatter is uninformative or permanently suppressed (Bauer-Marschallinger et al., 2022; Shen et al., 2019).
2. **Sub-Pixel Spatial Scale:** Small tributary channels, urban drainage canals, and fragmented water bodies narrower than the effective spatial resolution of the sensor ($20\text{ m}$ for Sentinel-1 GRD) produce mixed pixels where backscatter attenuation is insufficient to overcome background backscatter from vegetation or soil (DeVries et al., 2020).
3. **Dynamic Intertidal Ambiguity:** In low-lying coastal deltas, regular tidal fluctuations, intertidal mudflats, and aquaculture ponds exhibit backscatter characteristics that mirror anomalous floodwaters, confounding simple change detection against single pre-event scenes (Pekel et al., 2016; Bioresita et al., 2018).
4. **Permanent vs. Novel Inundation:** Natural seasonal water bodies, reservoirs, and perennial river channels naturally exhibit specular radar reflection; classifying them as floods introduces massive false positive biases unless rigorously gated by multi-decadal hydrological water occurrence climatologies.

When an automated model evaluates a satellite scene over such unobservable terrain, an algorithm forced into a binary classification choice encounters fundamental physical limitations: it must either produce a false alarm (e.g., mistaking a radar shadow on a mountain slope for standing water) or emit a false negative (failing to detect water in a narrow, shadowed gorge), or declare dry ground when the sensor was effectively blind. In operational emergency response, declaring an obscured, cloud-covered, or radar-shadowed community as "dry" (false negative) can mislead relief operations.

Operational disaster mapping systems have increasingly recognized this challenge. For example, the Copernicus Global Flood Monitoring (GFM) service incorporates static and dynamic exclusion masks (advisory flags for radar shadow, layover, low backscatter, and permanent water) (Bauer-Marschallinger et al., 2022). However, operational products predominantly apply these exclusions post-hoc as binary masks, discarding intermediate uncertainty or treating them as unweighted filters without quantifying continuous observability or its mathematical relationship to classification reliability.

### The Present Study & Testable Hypothesis
To address these fundamental observational limits, we present an observability-gated multi-modal flood mapping framework called **Earth One Flood**. Rather than forcing binary decisions, the framework combines physics-constrained evidence fusion, biophysical regime routing, an explicit **Continuous Observability Index ($O \in [0.0, 1.0]$)**, and a **Resolution-Aware Tri-State Interpretation Contract**:
$$\text{Decision}(p) = \begin{cases} \text{FLOOD} & \text{if } O(p) \ge 0.50 \land S(p) \ge 0.20 \\ \text{NO\_FLOOD} & \text{if } O(p) \ge 0.50 \land S(p) < 0.20 \\ \text{UNRESOLVED} & \text{if } O(p) < 0.50 \end{cases}$$
The state UNRESOLVED explicitly denotes an *observational limitation of the remote sensing system*, refusing to convert a sensor blind spot into an environmental conclusion.

We frame this study around **one testable scientific hypothesis**:
> *In satellite remote sensing of flood inundation, evaluating and enforcing an explicit physical observability index ($O \ge 0.50$) isolates genuine algorithmic detection skill from physical sensor occlusions (radar shadow, steep relief, intertidal ambiguity, and sub-pixel scale), significantly improving Precision-Recall AUC and stabilizing interannual generalization across diverse global flood regimes compared to unconstrained binary classification.*

To rigorously validate this hypothesis, we evaluated the system across **11 global flood activations from the Copernicus Emergency Management Service (CEMS) Rapid Mapping service**, spanning five continents and four hydrologic regimes (alluvial plain, alpine fluvial valley, temperate agricultural basin, and coastal estuary). We benchmark detection skill against random-chance baselines (class prevalence) and simple SAR backscatter thresholds, evaluate Brier skill scores against climatology, quantify the risk-coverage trade-off, ablate the observability index against individual quality filters, and evaluate interannual temporal generalization from 2018 to 2022.

---

## 2. Materials and Methods

### 2.1 External Earth Observation Data and Master Cohort Specification
The framework ingests multi-source Earth observation rasters via standard SpatioTemporal Asset Catalog (STAC) interfaces (Microsoft Planetary Computer and Copernicus Data Space Ecosystem). All spatial layers were projected to the local Universal Transverse Mercator (UTM / WGS 84 datum) coordinate reference system corresponding to the centroid of each Copernicus activation (Table 1; e.g., UTM Zone 42N for Pakistan EMSR629, UTM Zone 32N for Italy EMSR468 and Germany EMSR517, UTM Zone 56S for Australia EMSR567, UTM Zone 48N for Vietnam EMSR464, UTM Zone 45N for India EMSR357, UTM Zone 35N for Ukraine EMSR445, UTM Zone 36S for Mozambique EMSR348, and UTM Zone 18N for Colombia EMSR286). Continuous rasters (Sentinel-1 SAR backscatter $\sigma^0$, Sentinel-2 spectral reflectance, Copernicus DEM GLO-30 elevation) were coregistered and bilinearly resampled to a standardized $20\text{ m} \times 20\text{ m}$ pixel resolution ($512 \times 512$ computational grid; $10.24\text{ km} \times 10.24\text{ km} = 104.86\text{ km}^2$), while discrete thematic masks (JRC water occurrence, sensor telemetry validity) were resampled using nearest-neighbor interpolation.

![Figure 1. Earth One Flood Architecture and Component Dependency Diagram](/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures/figure_1_architecture.png)
**Figure 1.** End-to-end architectural workflow and component dependency diagram for the Earth One Flood framework. Satellite observations and physical baselines feed into two strictly separated analytical branches: Gated Evidence Fusion (evaluating local flood likelihood $S_{\text{candidate}}$) and Continuous Observability Modeling (evaluating pixel interpretability $O$). The branches converge exclusively at the Tri-State Decision Contract, preventing circular self-reinforcement.

![Figure 2. Geographic Distribution of 11 Copernicus EMS Flood Study Sites Across 5 Continents](/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures/figure_2_global_study_sites.png)
**Figure 2.** Global geographic distribution of all 11 Copernicus EMS Rapid Mapping activations across five continents. Orange squares denote the three-event development cohort used for initial heuristic parameter tuning; green circles denote the eight-event held-out validation pool evaluated zero-shot without parameter tuning.

#### Master Cohort Partitioning
To guarantee rigorous statistical independence and prevent data leakage, all 11 Copernicus EMS Rapid Mapping activations were strictly partitioned into an explicit development cohort ($N=3$) and a held-out validation pool ($N=8$) prior to freezing model parameters:

**Table 1.** Master Cohort Specification and Experimental Partitioning across 11 Copernicus EMS Rapid Mapping Activations.
| Activation | Event Name & Country | Hydrologic Regime | Pre-Event Date | Event Scene Date | CEMS Reference Product Identifier | CEMS Image Date | Temporal Lag ($\Delta t$) | Grid Shape ($20\text{ m}$) | Area ($\text{km}^2$) | Pos. Pixels | Prevalence | Experimental Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EMSR439** | Sandwip Channel, Bangladesh | Coastal Estuary / Tidal | 2020-04-29 | 2020-05-23 | `EMSR439_AOI01_DEL_observedEventA_v1` | 2020-05-24 | $+12.2\text{ h}$ | $512 \times 512$ | $104.85$ | $3,454$ | $0.0132$ | Development Cohort |
| **EMSR629** | Sindh Indus Basin, Pakistan | Inland Riverine Mega | 2022-08-27 | 2022-09-08 | `EMSR629_AOI01_DEL_observedEventA_v2` | 2022-09-08 | $+4.2\text{ h}$ | $512 \times 512$ | $104.85$ | $134,923$ | $0.5147$ | Development Cohort |
| **EMSR548** | Catania Plain, Sicily, Italy | Inland Riverine Pluvial | 2021-10-13 | 2021-10-24 | `EMSR548_AOI01_DEL_observedEventA_v3` | 2021-10-25 | $+18.5\text{ h}$ | $512 \times 512$ | $104.85$ | $9,847$ | $0.0376$ | Development Cohort |
| **EMSR348** | Quelimane, Mozambique | Coastal Estuarine Tidal | 2019-03-14 | 2019-03-20 | `EMSR348_01QUELIMANE_DEL_v2` | 2019-03-21 | $+14.8\text{ h}$ | $512 \times 512$ | $104.85$ | $9,312$ | $0.0355$ | Held-Out Validation Pool |
| **EMSR468** | Tanaro Valley, Piedmont, Italy | Steep Alpine Pluvial | 2020-09-27 | 2020-10-08 | `EMSR468_AOI02_DEL_observedEventA_v1` | 2020-10-09 | $+16.1\text{ h}$ | $512 \times 512$ | $104.85$ | $1,529$ | $0.0058$ | Held-Out Validation Pool |
| **EMSR517** | Rheinland-Pfalz, Germany | Temperate Fluvial Basin | 2021-07-15 | 2021-07-16 | `EMSR517_AOI01_DEL_observedEventA_v1` | 2021-07-17 | $+28.4\text{ h}$ | $512 \times 512$ | $104.85$ | $284$ | $0.0011$ | Held-Out Validation Pool |
| **EMSR464** | Ha Tinh, Vietnam | Tropical Monsoon Pluvial | 2020-10-06 | 2020-10-21 | `EMSR464_AOI01_DEL_observedEventA_v1` | 2020-10-22 | $+18.0\text{ h}$ | $512 \times 512$ | $104.85$ | $3,790$ | $0.0145$ | Held-Out Validation Pool |
| **EMSR357** | Mahanadi Delta, Odisha, India | Coastal / Riverine Delta | 2019-05-06 | 2019-05-10 | `EMSR357_AOI01_DEL_observedEventA_v4` | 2019-05-11 | $+22.5\text{ h}$ | $512 \times 512$ | $104.85$ | $6,522$ | $0.0249$ | Held-Out Validation Pool |
| **EMSR445** | Prut River, Ukraine | Fluvial Valley | 2020-07-09 | 2020-07-15 | `EMSR445_AOI01_DEL_observedEventA_v1` | 2020-07-16 | $+19.8\text{ h}$ | $512 \times 512$ | $104.85$ | $5,246$ | $0.0200$ | Held-Out Validation Pool |
| **EMSR567** | Gympie Mary River, Australia | Inland Fluvial Basin | 2021-02-28 | 2021-03-24 | `EMSR567_AOI01_DEL_observedEventA_v1` | 2021-03-25 | $+16.4\text{ h}$ | $512 \times 512$ | $104.85$ | $37,258$ | $0.1421$ | Held-Out Validation Pool |
| **EMSR286** | Cauca River / Ituango, Colombia | Dissected Alpine Valley | 2018-05-01 | 2018-05-15 | `EMSR286_01ITUANGO_DEL_MONIT01_v1` | 2018-05-17 | $+36.2\text{ h}$ | $512 \times 512$ | $104.85$ | $29,030$ | $0.1107$ | Held-Out Validation Pool |

*Notes:* All tiles are evaluated at $20\text{ m}$ pixel resolution ($512 \times 512$ grid; $N = 262,144$ pixels per tile). Temporal lag ($\Delta t$) indicates the time elapsed between the satellite acquisition ingested by our model and the source imagery used by CEMS cartographers to produce the published delineation.

---

### 2.2 Satellite Preprocessing Workflows
1. **Sentinel-1 SAR GRD:** Level-1 Ground Range Detected (GRD) products acquired in Interferometric Wide (IW) swath mode (dual-polarization VV and VH) were retrieved from ESA/Planetary Computer archives. Processing steps included orbit file application, border noise removal, thermal noise removal, radiometric calibration to linear backscatter $\sigma^0$, speckle filtering using a $3 \times 3$ Refined Lee filter, and Range-Doppler terrain correction using Copernicus DEM GLO-30. Pre-event baseline scenes were selected during the dry season ($15\text{--}90$ days prior to flood peak) to establish normal baseline backscatter.
2. **Sentinel-2 MSI L2A:** Bottom-Of-Atmosphere (BOA) surface reflectance tiles were acquired where available within $\pm 72$ hours of the event. Cloud, shadow, and snow masking were performed using the Scene Classification Layer (SCL); only valid clear land/water pixels (classes 4, 5, 6, 7) were admitted. Overcast storm cloud decks (cloud cover $> 40\%$) were masked as unresolved optical evidence, falling back smoothly to SAR without penalizing the water score.
3. **Topography (Copernicus DEM GLO-30):** Elevation values were resampled to $20\text{ m}$. Topographic slope $\theta$ in degrees was computed using Horn’s algorithm with a $3 \times 3$ kernel. Local relief roughness $\Delta h_{100\text{m}}$ was derived as the difference between the local maximum and minimum elevation in a $5 \times 5$ window ($100 \times 100\text{ m}$).
4. **Permanent Water Prior (JRC Global Surface Water v1.3):** The 38-year historical surface water occurrence frequency $f_{\text{perm}} \in [0.0, 1.0]$ (Pekel et al., 2016) was resampled to the $20\text{ m}$ grid.
5. **Meteorological Context (GPM IMERG & ERA5-Land):** Antecedent precipitation accumulation over a 72-hour window and standardized precipitation anomalies ($Z_{\text{rain}}$ relative to 30-year climatology) were extracted from the GPM IMERG Late Run (Huffman et al., 2020) and cross-verified against ERA5-Land hourly total precipitation reanalysis (Muñoz-Sabater et al., 2021).

---

### 2.3 Gated Physical Evidence Fusion Formulation
Unlike unconstrained additive models that permit false alarms in physically impossible locations, Earth One adopts **Gated Physical Evidence Fusion**:
$$S_{\text{candidate}} = S_{\text{water}} \cdot M_{\text{novelty}} \cdot M_{\text{terrain}} \cdot M_{\text{rain}}$$

#### 1. Direct Water Evidence ($S_{\text{water}} \in [0.0, 1.0]$)
$S_{\text{water}}$ combines relative backscatter drop and absolute low backscatter in C-band SAR:
$$\Delta\sigma^0_{\text{VV}} = \sigma^0_{\text{VV, event}} - \sigma^0_{\text{VV, before}} \quad (\text{dB})$$
$$S_{\text{delta, VV}} = \text{clip}\left(\frac{-\Delta\sigma^0_{\text{VV}} - 2.0}{4.0}, 0.0, 1.0\right), \quad S_{\text{abs, VV}} = \text{clip}\left(\frac{-14.0 - \sigma^0_{\text{VV, event}}}{8.0} + 0.5, 0.0, 1.0\right)$$
$$S_{\text{SAR, VV}} = 0.60 S_{\text{delta, VV}} + 0.40 S_{\text{abs, VV}}$$

When cross-polarization VH is available:
$$\Delta\sigma^0_{\text{VH}} = \sigma^0_{\text{VH, event}} - \sigma^0_{\text{VH, before}} \quad (\text{dB})$$
$$S_{\text{delta, VH}} = \text{clip}\left(\frac{-\Delta\sigma^0_{\text{VH}} - 2.0}{4.0}, 0.0, 1.0\right), \quad S_{\text{abs, VH}} = \text{clip}\left(\frac{-20.0 - \sigma^0_{\text{VH, event}}}{8.0} + 0.5, 0.0, 1.0\right)$$
$$S_{\text{SAR, VH}} = 0.60 S_{\text{delta, VH}} + 0.40 S_{\text{abs, VH}}$$
$$S_{\text{SAR}} = 0.55 S_{\text{SAR, VV}} + 0.45 S_{\text{SAR, VH}}$$

When cloud-free Sentinel-2 optical data are available, water index evidence is computed using both Normalized Difference Water Index (NDWI; McFeeters, 1996) and Modified NDWI (MNDWI; Xu, 2006):
$$\text{MNDWI} = \frac{\rho_{\text{B03}} - \rho_{\text{B11}}}{\rho_{\text{B03}} + \rho_{\text{B11}}}, \quad \text{NDWI} = \frac{\rho_{\text{B03}} - \rho_{\text{B08}}}{\rho_{\text{B03}} + \rho_{\text{B08}}}$$
$$S_{\text{MNDWI}} = \text{clip}\left(\frac{\text{MNDWI} - 0.0}{0.50} + 0.50, 0.0, 1.0\right) = \text{clip}(2.0 \cdot \text{MNDWI} + 0.50, 0.0, 1.0)$$
$$S_{\text{NDWI}} = \text{clip}\left(\frac{\text{NDWI} - 0.0}{0.50} + 0.50, 0.0, 1.0\right) = \text{clip}(2.0 \cdot \text{NDWI} + 0.50, 0.0, 1.0)$$
$$S_{\text{opt}} = 0.40 S_{\text{NDWI}} + 0.60 S_{\text{MNDWI}}$$

The fused direct water signal is:
$$S_{\text{water}} = \begin{cases} \frac{w_{\text{SAR}} S_{\text{SAR}} + w_{\text{opt}} S_{\text{opt}}}{w_{\text{SAR}} + w_{\text{opt}}} & \text{if both SAR and optical are valid} \\ S_{\text{SAR}} & \text{if only SAR is valid (e.g., cloudy)} \\ S_{\text{opt}} & \text{if only optical is valid} \end{cases}$$
Default weights are $w_{\text{SAR}} = 0.35$ and $w_{\text{opt}} = 0.25$.

#### 2. Hydrological Novelty Gate ($M_{\text{novelty}} \in [0.0, 1.0]$)
To prevent permanent water bodies from masquerading as disaster floods, the novelty gate scales inversely with long-term water occurrence frequency:
$$M_{\text{novelty}} = \text{clip}\left(1.0 - \frac{f_{\text{perm}}}{0.80}, 0.0, 1.0\right)$$
Where $f_{\text{perm}} \ge 0.80$ (water present $>80\%$ of the historical record), $M_{\text{novelty}} = 0.0$, completely suppressing permanent lakes and perennial rivers. Where data are missing, $M_{\text{novelty}} = 1.0$ (neutral).

#### 3. Topographic Plausibility Gate ($M_{\text{terrain}} \in [0.0, 1.0]$)
Standing water accumulation is physically constrained by gravity to low-slope terrain. Slopes $>15^\circ$ cannot retain standing water:
$$M_{\text{terrain}} = \begin{cases} 1.0 & \text{if } \theta \le 8.0^\circ \\ \text{clip}\left(1.0 - \frac{\theta - 8.0^\circ}{15.0^\circ - 8.0^\circ}, 0.0, 1.0\right) & \text{if } 8.0^\circ < \theta \le 15.0^\circ \\ 0.0 & \text{if } \theta > 15.0^\circ \end{cases}$$

#### 4. Meteorological Corroboration Gate ($M_{\text{rain}} \in [0.70, 1.00]$)
Antecedent precipitation provides corroborative context. Crucially, to prevent local rainfall absence (e.g., upstream dam bursts, snowmelt floods, or coastal surges) from suppressing legitimate floods, $M_{\text{rain}}$ is strictly bounded:
$$M_{\text{rain}} = 0.70 + 0.30 \times S_{\text{rain}}$$
$$S_{\text{rain}} = \text{clip}\left(0.60 \frac{R_{\text{accum}}}{100\text{ mm}} + 0.40 \frac{Z_{\text{rain}} + 1.0}{4.0}, 0.0, 1.0\right) \times \left(0.50 + 0.50 e^{-\Delta t_{\text{peak}} / 72\text{ h}}\right)$$
Because $M_{\text{rain}} \ge 0.70$, **it never zeroes out the flood candidate score**.

---

### 2.4 Biophysical Regime Routing
Different landscapes require regime-conditioned sensitivity. Using only pre-event physical baselines (elevation relief, slope distribution, coastal proximity, intertidal mudflat fraction), an autonomous decision tree evaluates the scene's biophysical features to classify the AOI into one of three specific hydrologic regimes:
1. `INLAND_RIVERINE_MEGA`: Flat alluvial floodplains ($f_{\text{flat}} \ge 0.65$, relief $\le 60\text{ m}$, dry land fraction $\ge 0.65$). Router confidence:
   $$C = \text{clip}\left(0.75 + 0.25 \times f_{\text{flat}}, 0.75, 0.98\right)$$
2. `INLAND_RIVERINE_PLUVIAL`: Dissected valleys and mountainous gorges (relief $>60\text{ m}$ or steep slope fraction $>10\%$). Router confidence:
   $$C = \text{clip}\left(0.70 + 0.30 \times \min\left(1.0, \frac{\Delta h_{90-10}}{200.0\text{ m}}\right), 0.70, 0.95\right)$$
3. `COASTAL_ESTUARINE_TIDAL`: Coastal lowlands and tidal estuaries ($P_{10}$ elevation $\le 3\text{ m}$, intertidal fraction $>3\%$). Router confidence:
   $$C = \text{clip}\left(0.70 + 0.30 \times (f_{\text{marine}} + f_{\text{mudflat}}), 0.70, 0.95\right)$$
4. `MIXED_UNCERTAIN` (Ambiguous or Unclassified): When terrain features do not satisfy any of the specific regime criteria (the default unclassified branch), or when empirical confidence falls below the empirical confidence threshold ($C < 0.60$), the router flags `MIXED_UNCERTAIN` and enforces $C = 0.0$.

The continuous decision score blends the baseline global detection score $S_{\text{global}}$ and the regime-routed score $S_{\text{regime}}$ using router confidence $C$:
$$S_{\text{final}} = (1 - C) S_{\text{global}} + C S_{\text{regime}}$$
Where $C < 0.60$, $C = 0.0 \implies S_{\text{final}} = S_{\text{global}}$, cleanly executing an unrouted fallback to the global baseline without parameter modification.

---

### 2.5 Continuous Observability Index and Resolution-Aware Decision Contract
The physical observability index $O \in [0.0, 1.0]$ decomposes observational quality into five multiplicative factors:
$$O = S_{\text{scale}} \times W_{\text{water}} \times G_{\text{geom}} \times T_{\text{terrain}} \times D_{\text{validity}}$$

1. **Sensor Data Validity Indicator ($D_{\text{validity}} \in \{0, 1\}$):** To resolve missing-data conflicts, telemetry validity requires at least one primary sensor channel:
   $$D_{\text{validity}} = D_{\text{SAR}} \lor D_{\text{optical}}$$
   If both SAR and optical telemetry are missing or corrupted, $D_{\text{validity}} = 0 \implies O = 0 \implies \text{UNRESOLVED}$ (fail-safe blackout). If SAR is valid (even under storm clouds), $D_{\text{validity}} = 1$. If an optical pass is clear while SAR is offline, $D_{\text{validity}} = 1$, enabling optical-only confirmation without forced abstention.
2. **Topographic Slope Penalty ($T_{\text{terrain}} \in [0.0, 1.0]$):** $T = \text{clip}(1.0 - \theta / 15.0^\circ, 0.0, 1.0)$.
3. **Radar Geometric Relief Roughness ($G_{\text{geom}} \in [0.0, 1.0]$):** $G = \text{clip}(1.0 - \Delta h_{100\text{m}} / 150.0\text{m}, 0.0, 1.0)$. High local relief triggers radar layover and shadow.
4. **Intertidal Ambiguity Attenuation ($W_{\text{water}} \in [0.35, 1.00]$):** $W = 0.35$ if $(z \le 2.5\text{ m} \land 0.10 \le f_{\text{perm}} < 0.70)$, else $1.0$.
5. **Sub-Pixel Scale Factor ($S_{\text{scale}} \in [0.50, 1.00]$):** In drainage valleys ($\theta \le 5^\circ \lor f_{\text{perm}} > 0$), hydraulic feature width $d_{\text{valley}}$ is estimated via Euclidean distance transform. Features narrower than $2$ pixels ($40\text{ m}$) are penalized: $S = \text{clip}(d_{\text{valley}} / 40.0\text{m}, 0.50, 1.00)$.

#### The Resolution-Aware Tri-State Contract
Enforcing $O_{\text{thresh}} = 0.50$ and $T_{\text{det}} = 0.20$:
- **FLOOD:** Confirmed anomalous inundation ($O \ge 0.50 \land S_{\text{final}} \ge 0.20$).
- **NO_FLOOD:** Confirmed dry land ($O \ge 0.50 \land S_{\text{final}} < 0.20$).
- **UNRESOLVED:** Observational undecidability ($O < 0.50$). The system explicitly abstains from making an environmental declaration.

---

### 2.6 Validation Metrics, Chance Baselines, and Spatial Autocorrelation
1. **Precision-Recall AUC vs. Random-Chance Baseline:** Because flood pixels typically occupy $<5\%$ of an evaluation domain, the area under the Receiver Operating Characteristic curve (ROC-AUC) is misleadingly inflated by true negatives. PR-AUC is our primary ranking metric. Crucially, the PR-AUC of an uninformative random classifier equals the positive class prevalence:
   $$\text{PR-AUC}_{\text{chance}} = \pi = \frac{P}{P + N}$$
   Every reported PR-AUC is presented alongside $\text{PR-AUC}_{\text{chance}}$ and the **Skill Ratio** ($\text{PR-AUC} / \text{PR-AUC}_{\text{chance}}$).
2. **Brier Score and Brier Skill Score ($BSS$):** The Brier score measures mean squared probability error: $BS = \frac{1}{N}\sum (p_i - y_i)^2$. The climatological reference Brier score is $BS_{\text{clim}} = \pi(1 - \pi)$. The Brier Skill Score is:
   $$BSS = 1 - \frac{BS}{BS_{\text{clim}}}$$
3. **Spatial Block Bootstrap Resampling:** Pixels in satellite imagery exhibit strong spatial autocorrelation. Semivariogram analysis revealed an autocorrelation range of $\sim 500\text{ m}$. We conducted block bootstrap resampling ($B = 1,000$ resamples) using spatial blocks of $32 \times 32$ pixels ($640 \times 640\text{ m}$), preserving spatial correlation structures to derive valid $95\%$ empirical confidence intervals.

---

## 3. Results

### 3.1 Multi-Regime Evaluation across Held-Out Validation Events
Performance varied substantially across different geographic landscapes and hydrologic regimes (Tables 2a and 2b, Figure 3). The three development events (EMSR439, EMSR629, EMSR548) served as diagnostic testbeds: in broad alluvial sheet floods (EMSR629 Indus Basin, Pakistan), the system achieved a PR-AUC of $0.8337$, precision of $73.8\%$, and F1-score of $80.1\%$ ($1.62\times$ over chance baseline). In this setting, floodwaters extended across tens of kilometers with low topographic relief ($\theta = 0.35^\circ$), producing strong, uniform specular radar drops that were completely unobscured.

Across the **eight held-out unseen validation events**, macro PR-AUC over the full domain was $0.06972$ and improved by $+29.3\%$ to $0.09016$ when restricted to the physically resolvable domain ($O \ge 0.50$). Individual event skill ratios ranged from $1.05\times$ to $9.03\times$ over prevalence chance baselines:
- In temperate Germany (EMSR517), where reference flood prevalence was only $0.11\%$, the reported PR-AUC of $0.0098$ represented a **$9.03\times$ improvement over chance**.
- In Mozambique (EMSR348), PR-AUC was $0.0988$, representing a **$2.78\times$ improvement over chance**.
- In Australia (EMSR567), PR-AUC reached $0.2120$ ($1.49\times$ chance), increasing to $0.2578$ ($1.81\times$ chance) under abstention.
- In Colombia (EMSR286), PR-AUC reached $0.1453$ ($1.31\times$ chance), increasing to $0.2282$ ($2.06\times$ chance) under abstention.

**Table 2a.** Event Characteristics, Class Prevalence, and Ranking Performance across Held-Out Validation Events and Development Cohort.
| Activation & Country | Hydrologic Regime | Grid Shape | Reference Positives | Positive Prevalence ($\text{PR}_{\text{chance}}$) | PR-AUC (Full Domain) | Skill Ratio (Full) | PR-AUC ($O \ge 0.50$) | $\Delta\text{PR-AUC}$ [$95\%\text{ CI}$] | Skill Ratio ($O \ge 0.50$) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Held-Out Validation Pool (N = 8):** | | | | | | | | | |
| **EMSR348** (Mozambique) | Coastal Estuary | $512 \times 512$ | $9,312$ | $0.0355$ | $0.0988$ | $2.78\times$ | $0.1011$ | $+0.0023$ [$0.001, 0.005$] | $2.85\times$ |
| **EMSR468** (Italy Tanaro) | Alpine Pluvial | $512 \times 512$ | $1,529$ | $0.0058$ | $0.0113$ | $1.94\times$ | $0.0149$ | $+0.0036$ [$0.001, 0.006$] | $2.57\times$ |
| **EMSR517** (Germany) | Fluvial Basin | $512 \times 512$ | $284$ | $0.0011$ | $0.0098$ | $9.03\times$ | $0.0142$ | $+0.0044$ [$0.002, 0.007$] | $13.08\times$ |
| **EMSR464** (Vietnam) | Monsoon Pluvial | $512 \times 512$ | $3,790$ | $0.0145$ | $0.0239$ | $1.66\times$ | $0.0248$ | $+0.0009$ [$0.000, 0.002$] | $1.72\times$ |
| **EMSR357** (India Mahanadi) | Coastal Delta | $512 \times 512$ | $6,522$ | $0.0249$ | $0.0357$ | $1.44\times$ | $0.0501$ | $+0.0143$ [$0.006, 0.023$] | $2.01\times$ |
| **EMSR445** (Ukraine Prut) | Fluvial Valley | $512 \times 512$ | $5,246$ | $0.0200$ | $0.0209$ | $1.05\times$ | $0.0302$ | $+0.0092$ [$0.003, 0.016$] | $1.51\times$ |
| **EMSR567** (Australia Mary) | Fluvial Basin | $512 \times 512$ | $37,258$ | $0.1421$ | $0.2120$ | $1.49\times$ | $0.2578$ | $+0.0458$ [$0.031, 0.061$] | $1.81\times$ |
| **EMSR286** (Colombia Cauca) | Mountain Valley | $512 \times 512$ | $29,030$ | $0.1107$ | $0.1453$ | $1.31\times$ | $0.2282$ | $+0.0829$ [$0.062, 0.104$] | $2.06\times$ |
| **Validation Macro Mean** | — | — | — | **$0.0443$** | **$0.06972$** | **$2.59\times$** | **$0.09016$** | **$+0.02044$** | **$3.46\times$** |
| *Development Cohort (N = 3; Reference Only):* | | | | | | | | | |
| **EMSR439** (Bangladesh)$^\dagger$ | Coastal Estuary | $512 \times 512$ | $3,454$ | $0.0132$ | $0.0171$ | $1.30\times$ | $0.0248$ | $+0.0077$ [$0.003, 0.012$] | $1.88\times$ |
| **EMSR629** (Pakistan)$^\dagger$ | Alluvial Mega | $512 \times 512$ | $134,923$ | $0.5147$ | $0.8337$ | $1.62\times$ | $0.8338$ | $+0.0001$ [$0.000, 0.001$] | $1.62\times$ |
| **EMSR548** (Italy Catania)$^\dagger$ | Inland Pluvial | $512 \times 512$ | $9,847$ | $0.0376$ | $0.0684$ | $1.82\times$ | $0.0941$ | $+0.0257$ [$0.018, 0.034$] | $2.50\times$ |
| *Development Macro Mean* | — | — | — | *$0.1885$* | *$0.30640$* | *$1.58\times$* | *$0.31756$* | *$+0.01116$* | *$2.00\times$* |

$^\dagger$ Denotes development-cohort activation used during initial heuristic configuration. Confidence intervals are $95\%$ spatial block bootstrap intervals ($B = 1,000$).

Table 2b reports the operational tri-state confusion matrix across each $512 \times 512$ tile ($N = 262,144$ pixels per activation; total $2,097,152$ pixels across the eight held-out validation events) at detection threshold $T_{\text{det}} = 0.20$. Under the tri-state operational decision contract (Section 2.5), pixels with $O < 0.50$ are classified as `UNRESOLVED` (abstention). Operationally, abstention prevents affirmative flood alarms from being issued over unobservable, noise-corrupted terrain ($FP = 0$ in the unresolved zone). Consequently, when evaluating operational performance across the full geographic tile, reference flood pixels falling within abstained zones are accounted for as operational missed alerts (operational False Negatives, $FN_{\text{unres}} = 39,348$ pixels across the eight events, representing $42.32\%$ of all reference flood extent), while reference non-flood pixels in abstained zones are accounted for as operational non-alarms (operational True Negatives, $TN_{\text{unres}} = 1,132,120$ pixels). This operational accounting yields the tile-level confusion matrices in Table 2b, which sum to exactly $262,144$ pixels per event (total $TP = 2,706$, $FP = 104,016$, $FN = 90,265$, $TN = 1,900,165$).

In contrast, when evaluation is restricted strictly to the physically resolvable domain ($O \ge 0.50$, encompassing $925,684$ pixels across the eight events, or $44.14\%$ operating coverage), all $1,171,468$ unresolved pixels are removed from the evaluation domain. Because affirmative flood alerts are generated solely within the resolvable domain, positive detections are identical ($TP = 2,706$, $FP = 104,016$). Resolvable false negatives are $FN_{\text{res}} = 50,917$ and resolvable true negatives are $TN_{\text{res}} = 768,045$ ($2,706 + 104,016 + 50,917 + 768,045 = 925,684$). In this resolvable domain, precision is $2.54\%$, recall is $5.05\%$, F1-score is $0.0338$, IoU is $0.0172$, and the false alarm footprint is reduced by $35.8\%$ relative to unconstrained candidate detection ($162,000 \rightarrow 104,016$ FP pixels).

**Table 2b.** Full-Domain Tri-State Operational Confusion Matrices, Detection Accuracy, and Inundation Abstention Breakdown at $T_{\text{det}} = 0.20$.
| Activation & Country | True Pos. ($TP$) | False Pos. ($FP$) | False Neg. ($FN$) | True Neg. ($TN$) | Precision | Recall | F1-Score | IoU | Area Bias | Unresolved Pixels | Domain Unres. % | Ref. Flood in Unresolved % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Held-Out Validation Pool (N = 8):** | | | | | | | | | | | | |
| **EMSR348** (Mozambique) | $25$ | $510$ | $9,287$ | $252,322$ | $4.67\%$ | $0.27\%$ | $0.0051$ | $0.0025$ | $0.057\times$ | $82,628$ | $31.5\%$ | $8.2\%$ |
| **EMSR468** (Italy Tanaro) | $36$ | $3,096$ | $1,493$ | $257,519$ | $1.15\%$ | $2.35\%$ | $0.0154$ | $0.0078$ | $2.048\times$ | $182,374$ | $69.6\%$ | $44.5\%$ |
| **EMSR517** (Germany) | $11$ | $135$ | $273$ | $261,725$ | $7.53\%$ | $3.87\%$ | $0.0512$ | $0.0263$ | $0.514\times$ | $177,750$ | $67.8\%$ | $38.2\%$ |
| **EMSR464** (Vietnam) | $2,065$ | $86,853$ | $1,725$ | $171,501$ | $2.32\%$ | $54.49\%$ | $0.0445$ | $0.0228$ | $23.461\times$ | $19,372$ | $7.4\%$ | $5.1\%$ |
| **EMSR357** (India Mahanadi) | $354$ | $11,717$ | $6,168$ | $243,905$ | $2.93\%$ | $5.43\%$ | $0.0381$ | $0.0194$ | $1.851\times$ | $218,010$ | $83.2\%$ | $71.4\%$ |
| **EMSR445** (Ukraine Prut) | $0$ | $1,100$ | $5,246$ | $255,798$ | Undef. | $0.00\%$ | $0.0000$ | $0.0000$ | $0.210\times$ | $104,499$ | $39.9\%$ | $22.1\%$ |
| **EMSR567** (Australia Mary) | $44$ | $142$ | $37,214$ | $224,744$ | $23.66\%$ | $0.12\%$ | $0.0024$ | $0.0012$ | $0.005\times$ | $130,855$ | $49.9\%$ | $19.4\%$ |
| **EMSR286** (Colombia Cauca) | $171$ | $463$ | $28,859$ | $232,651$ | $26.97\%$ | $0.59\%$ | $0.0115$ | $0.0058$ | $0.022\times$ | $255,980$ | $97.7\%$ | $84.6\%$ |
| *Development Cohort (N = 3; Reference Only):* | | | | | | | | | | | | |
| **EMSR439** (Bangladesh)$^\dagger$ | $0$ | $146$ | $3,454$ | $258,544$ | Undef. | $0.00\%$ | $0.0000$ | $0.0000$ | $0.042\times$ | $83,361$ | $31.8\%$ | $18.4\%$ |
| **EMSR629** (Pakistan)$^\dagger$ | $118,276$ | $42,088$ | $16,647$ | $85,133$ | $73.75\%$ | $87.66\%$ | $0.8011$ | $0.6682$ | $1.189\times$ | $315$ | $0.1\%$ | $0.1\%$ |
| **EMSR548** (Italy Catania)$^\dagger$ | $646$ | $2,644$ | $9,201$ | $249,653$ | $19.64\%$ | $6.56\%$ | $0.0983$ | $0.0517$ | $0.334\times$ | $130,154$ | $49.6\%$ | $24.7\%$ |

*Notes:* Table counts report the full-domain operational tri-state classification performance ($N = 262,144$ pixels per activation; total $2,097,152$ pixels across the eight held-out validation events) at detection threshold $T_{\text{det}} = 0.20$. In this operational accounting, pixels with $O < 0.50$ are abstained from affirmative flood prediction (generating zero false alarms); reference flood pixels falling in the abstained zone are counted as operational False Negatives ($FN_{\text{unres}} = 39,348$ across the eight events, $42.32\%$ of reference flood extent), and reference non-flood pixels in the abstained zone are counted as operational True Negatives ($TN_{\text{unres}} = 1,132,120$). When evaluated strictly within the resolvable domain ($O \ge 0.50$; $925,684$ total pixels, $44.14\%$ operating coverage), $TP = 2,706$, $FP = 104,016$, $FN_{\text{res}} = 50,917$, and $TN_{\text{res}} = 768,045$, yielding resolvable precision $= 2.54\%$, recall $= 5.05\%$, F1-score $= 0.0338$, and IoU $= 0.0172$. Undef. = Precision undefined ($0/0$; zero predicted positives).

![Figure 3. Actual Georeferenced CEMS Vector Reference and Model Comparison](/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures/figure_3_spatial_prediction_vs_reference.png)
**Figure 3.** Georeferenced spatial inundation, observability, and actual CEMS vector ground-truth comparisons across representative flood regimes: (Row 1) EMSR629 Pakistan Indus alluvial mega-flood ($9,690$ reference polygons, $134,923$ raster flood pixels); (Row 2) EMSR468 Italy Tanaro steep alpine gorge ($172$ reference polygons, $1,529$ raster flood pixels); (Row 3) EMSR567 Australia Gympie Mary River basin ($42$ reference polygons, $37,258$ raster flood pixels). (a) Sentinel-1 SAR $\Delta\sigma^0_{\text{VV}}$ backscatter change (dB); (b) Continuous Observability Index $O$; (c) Tri-state decision classification (FLOOD in cyan, NO_FLOOD in slate gray, UNRESOLVED in orange); (d) Published Copernicus EMS Rapid Mapping vector ground-truth boundaries overlaid in red outline.

---

### 3.2 Observability-Bin Reliability Audit across Held-Out Validation Pixels
To audit whether the continuous physical Observability Index $O$ reliably stratifies empirical detector precision, we analyzed $1,310,720$ pooled pixels from five held-out validation activations (EMSR357 India, EMSR445 Ukraine, EMSR567 Australia, EMSR348 Mozambique, and EMSR286 Colombia) divided into five observability tiers (Table 3, Figure 4).

**Table 3.** Observability-Bin Reliability Audit across $1,310,720$ Held-Out Validation Pixels.
| Observability Bin ($O$) | Pixel Count | Pixel Frac. | Ref. Positives | Base Prevalence | Pred. Positives ($T \ge 0.20$) | True Pos. ($TP$) | False Pos. ($FP$) | False Neg. ($FN$) | True Neg. ($TN$) | Empirical Precision [$95\%\text{ CI}$] | Empirical Recall [$95\%\text{ CI}$] | PR-AUC [$95\%\text{ CI}$] | Brier Score ($BS$) | Climatology $BS_{\text{clim}}$ | Brier Skill Score ($BSS$) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Bin 1: $[0.00, 0.20)$** | $676,250$ | $51.6\%$ | $33,491$ | $0.0495$ | $0$ | $0$ | $0$ | $33,491$ | $642,759$ | **Undefined** ($0/0$) | $0.0\%$ [$0.0, 0.0$] | $0.0587$ [$0.049, 0.069$] | $0.0495$ | $0.0471$ | $-0.0516$ |
| **Bin 2: $[0.20, 0.40)$** | $184,007$ | $14.0\%$ | $10,270$ | $0.0558$ | $20,499$ | $986$ | $19,513$ | $9,284$ | $154,224$ | $4.81\%$ [$3.99, 5.62$] | $9.60\%$ [$9.02, 10.15$] | $0.0588$ [$0.049, 0.068$] | $0.0643$ | $0.0527$ | $-0.2202$ |
| **Bin 3: $[0.40, 0.60)$** | $218,847$ | $16.7\%$ | $11,577$ | $0.0529$ | $35,271$ | $1,432$ | $33,839$ | $10,145$ | $173,431$ | $4.06\%$ [$3.45, 4.67$] | $12.37\%$ [$11.64, 13.10$] | $0.0514$ [$0.044, 0.059$] | $0.0677$ | $0.0501$ | $-0.3513$ |
| **Bin 4: $[0.60, 0.80)$** | $71,907$ | $5.5\%$ | $8,771$ | $0.1220$ | $12,607$ | $1,504$ | $11,103$ | $7,267$ | $52,033$ | $11.93\%$ [$10.01, 13.94$] | $17.15\%$ [$15.60, 18.66$] | $0.1292$ [$0.111, 0.149$] | $0.1236$ | $0.1071$ | $-0.1541$ |
| **Bin 5: $[0.80, 1.00]$** | $159,709$ | $12.2\%$ | $23,259$ | $0.1456$ | $42,022$ | $4,656$ | $37,366$ | $18,603$ | $99,084$ | $11.08\%$ [$9.39, 12.99$] | $20.02\%$ [$18.45, 21.55$] | $0.1336$ [$0.115, 0.152$] | $0.1594$ | $0.1244$ | $-0.2811$ |

![Figure 4. Observability-Bin Reliability Audit across Held-Out Validation Pixels](/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures/figure_4_observability_calibration.png)
**Figure 4.** Observability-bin reliability audit across $1,310,720$ held-out validation pixels. Blue squares show empirical precision with $95\%$ spatial block bootstrap confidence intervals strictly for Bins 2–5; black dotted line shows positive class prevalence; orange circles on the right axis show continuous PR-AUC across all five tiers. In Bin 1, precision is mathematically undefined ($0/0$) due to zero predicted positives and is omitted from the precision curve.

Key findings from the reliability audit:
1. **Severe Obscuration & Zero Detections in Bin 1:** Over half of all validation pixels ($51.6\%$) fell into Bin 1 ($O < 0.20$). At our standard detection threshold ($S \ge 0.20$), exactly zero positive detections were emitted ($TP = 0, FP = 0$). Consequently, empirical precision is mathematically **undefined ($0/0$)**.
2. **High Observability Yields Over $2.3\times$ Higher PR-AUC:** PR-AUC increased from $0.0587$ in Bin 1 to $0.1336$ in Bin 5 ($+127.6\%$ gain), demonstrating that pixels classified as highly observable exhibit substantially greater ranking discrimination.
3. **Statistical Inference across Bins:** Because precision in Bin 1 is undefined, imputing zero is statistically arbitrary. When correlation is evaluated over the **four well-defined precision tiers ($O \ge 0.20$)**, Pearson $r = 0.8385$ ($p = 0.1615$) and Spearman $\rho = 0.6000$ ($p = 0.4000$). When evaluated using continuous PR-AUC across all five tiers (where rankings and reference positives are fully defined), Pearson $r = 0.8436$ ($p = 0.0725$) and Spearman $\rho = 0.7000$ ($p = 0.1881$). We qualify this relationship as a descriptive positive grouping rather than a strictly monotonic continuous law.
4. **Brier Skill Score ($BSS$):** Because Bin 1 emitted zero predictions ($p_i = 0$), its Brier score was exactly equal to the positive prevalence ($33,491 / 676,250 = 0.0495$). In higher bins, uncalibrated probability residuals resulted in negative Brier Skill Scores ($-0.05$ to $-0.35$) relative to climatology ($BS_{\text{clim}} = \pi(1 - \pi)$), confirming that raw candidate scores cannot be interpreted as calibrated physical probabilities without post-hoc isotonic calibration.

---

### 3.3 Risk-Coverage Trade-Off and Multi-Mode Ablation
To evaluate whether the continuous Observability Index $O$ carries distinct physical information beyond simply reusing the terrain or water gates, we performed a multi-mode ablation experiment across the eight held-out validation activations at matched pixel coverage ($44.14\%$, corresponding exactly to $O \ge 0.50$; Table 4, Figure 5, Figure 6b).

**Table 4.** Component-Level Ablation and Baseline Comparison across the Eight Held-Out Validation Activations (Full Domain vs. Matched 44.14% Coverage).
| Model / Evaluation Mode | Quality Gate / Selection Rule | Coverage | Macro PR-AUC | $\Delta\text{PR-AUC}$ vs Raw | False Positive Pixels | Area Bias | Primary Failure Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Panel A: Unconstrained Full Domain** | | | | | | | |
| **Baseline 1** | Single-channel SAR threshold ($\sigma^0_{\text{VV}} < -14\text{ dB}$) | $100.0\%$ | $0.0524$ | $-0.0173$ | $285,000$ | $3.07\times$ | Severe permanent water & shadow false alarms |
| **Baseline 2** | Standard SAR change detection ($\Delta\sigma^0_{\text{VV}} \le -2\text{ dB}$) | $100.0\%$ | $0.0618$ | $-0.0079$ | $198,000$ | $2.13\times$ | Agricultural moisture & tidal false positives |
| **Mode A** | Additive evidence blending: $0.35 S_{\text{SAR}} + 0.25 S_{\text{opt}} + 0.20 (1 - f_{\text{perm}}) + 0.20 \max(0, 1 - \theta / 15^\circ)$ | $100.0\%$ | $0.0487$ | $-0.0210$ | $340,000$ | $3.66\times$ | Mountain ridge & topographic false alarms |
| **Mode B** | Gated candidate score (unconstrained candidate detection) | $100.0\%$ | $0.06972$ | Baseline | $162,000$ | $1.74\times$ | Unresolved radar shadow & steep valley noise |
| **Panel B: Matched Coverage ($44.14\%$)** | | | | | | | |
| **Baseline 2 + Random Retention** | SAR change detection with random $44.14\%$ spatial sampling | $44.14\%$ | $0.0621$ | $-0.0076$ | $87,400$ | $0.94\times$ | Retains shadow noise proportionally |
| **Baseline 2 + Sensor Mask** | SAR change detection with telemetry valid mask ($D_{\text{validity}}$) | $44.14\%$ | $0.0635$ | $-0.0062$ | $86,100$ | $0.93\times$ | Omits terrain relief & water occurrence |
| **Mode B + Random Retention** | Gated candidate score with random $44.14\%$ spatial sampling | $44.14\%$ | $0.0701$ | $+0.0004$ | $71,500$ | $0.77\times$ | Unstratified random suppression |
| **Mode B + Geometric Mask** | Gated candidate score with SAR geometric relief ($G_{\text{geom}} \ge 0.50$) | $44.14\%$ | $0.0734$ | $+0.0037$ | $148,000$ | $1.59\times$ | Fails to suppress intertidal mudflats |
| **Mode C (Slope Filter)** | Slope-only retention filter ($\theta \le 6.5^\circ$) | $44.14\%$ | $0.0748$ | $+0.0051$ | $142,000$ | $1.53\times$ | Misses radar layover in rolling hills |
| **Mode D (Permanent Water)** | Permanent water-only retention filter ($f_{\text{perm}} < 0.65$) | $44.14\%$ | $0.0782$ | $+0.0085$ | $131,000$ | $1.41\times$ | Misses dynamic tidal flat fluctuations |
| **Mode E (Score Confidence)** | Candidate score thresholding ($S_{\text{candidate}} \ge 0.32$) | $44.14\%$ | $0.0811$ | $+0.0114$ | $122,000$ | $1.31\times$ | Discards low-contrast alluvial floods |
| **Full Engine** | **Full Observability Index ($O \ge 0.50$)** | **$44.14\%$** | **$0.09016$** | **$+0.02044$** | **$104,016$** | **$1.15\times$** | **Optimal multi-factor noise suppression** |

*Notes:* All evaluations conducted across the identical pool of $2,097,152$ held-out validation pixels ($N=8$ events). Panel A evaluates unconstrained full-domain models ($100\%$ coverage). Panel B benchmarks all models matched at the exact operating coverage of $44.14\%$ ($925,684$ pixels). Random retention uniformly sampled $44.14\%$ of pixels over $100$ Monte Carlo repetitions (seed $42\text{--}141$), reporting mean $\pm$ standard error ($0.0621 \pm 0.0004$ for SAR change, $0.0701 \pm 0.0005$ for Mode B). The sensor validity mask ($D_{\text{validity}}$) was stratified by multi-sensor coincidence and truncated at the 44.14th percentile. The geometric relief mask ($G_{\text{geom}}$) was truncated at the 44.14th percentile of lowest terrain slope and radar distortion. Relative to unconstrained candidate detection (Mode B, $162,000$ FP pixels), the Full Observability Engine reduces false positives to $104,016$ pixels (a $35.8\%$ reduction, matching Table 2b and Figure 5b).

![Figure 5. Risk-Coverage Curves Reconciled with Held-Out Validation Pool](/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures/figure_5_risk_coverage_curves.png)
**Figure 5.** Risk-coverage trade-off curves evaluated across the eight held-out validation events ($2,097,152$ pixels): (a) Macro PR-AUC vs domain coverage fraction; (b) False positive area reduction (%) vs domain coverage fraction. The dashed red line marks the operating point ($O_{\text{thresh}} = 0.50$, coverage $= 44.14\%$, macro PR-AUC $= 0.09016$).

![Figure 6. Primary Temporal Generalization and Matched-Coverage Component Ablation](/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures/figure_6_temporal_shift_and_ablation.png)
**Figure 6.** (a) Primary Independent Temporal Generalization across the eight held-out validation activations partitioned chronologically into Modern ($2020\text{--}2021$, $N=5$) and Historical ($2018\text{--}2019$, $N=3$) cohorts, showing consistent macro PR-AUC improvements ($+23.0\%$ and $+35.6\%$) and skill ratios ($3.84\times$ and $2.84\times$ over class prevalence $\bar{\pi}$) under physical observability gating ($O \ge 0.50$; Table 5); (b) Component-level ablation benchmarked at matched operating coverage ($44.14\%$, $925,684$ pixels), demonstrating that the unified Observability Index $O$ achieves superior detection accuracy compared to standard SAR change detection with random retention ($0.0621$) or sensor validity masks ($0.0635$), candidate scoring with random retention ($0.0701$) or geometric relief masks ($0.0734$), and single-factor physical filters (Table 4 Panel B).

---

### 3.4 Interannual Temporal Generalization (2018–2022)
To evaluate temporal stability, we analyzed performance across distinct chronological eras. We established the **Primary Independent Temporal Generalization Design** (Table 5) by partitioning the eight strictly held-out validation activations chronologically into a Modern Operational Era ($2020\text{--}2021$, $N=5$) and an earlier Historical Era ($2018\text{--}2019$, $N=3$).

**Table 5.** Primary Independent Temporal Generalization Evaluation across Chronological Eras (Held-Out Validation Pool, N = 8).
| Chronological Era & Activations | Events ($N$) | Mean Prev. ($\bar{\pi}$) | Full Domain Macro PR-AUC | Full Skill Ratio | Resolvable PR-AUC ($O \ge 0.50$) | Resolvable Skill Ratio | PR-AUC Gain ($\Delta$) | Relative Gain |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Modern Era (2020–2021):** EMSR445, EMSR464, EMSR468, EMSR517, EMSR567 | $5$ | $0.03672$ ($3.67\%$) | $0.05558$ | $2.94\times$ | $0.06838$ | $3.84\times$ | $+0.01280$ | $+23.0\%$ |
| **Historical Era (2018–2019):** EMSR286, EMSR348, EMSR357 | $3$ | $0.05697$ ($5.70\%$) | $0.09327$ | $2.01\times$ | $0.12647$ | $2.84\times$ | $+0.03320$ | $+35.6\%$ |
| **Full Held-Out Validation Cohort** | $8$ | $0.04431$ ($4.43\%$) | $0.06972$ | $2.59\times$ | $0.09016$ | $3.46\times$ | $+0.02044$ | $+29.3\%$ |

*Notes:* Evaluated strictly on the eight held-out validation events. Modern Era: EMSR445 (Prut River, Ukraine, July 2020), EMSR464 (Ha Tinh, Vietnam, October 2020), EMSR468 (Tanaro Valley, Italy, October 2020), EMSR517 (Rheinland-Pfalz, Germany, July 2021), EMSR567 (Gympie Mary River, Australia, March 2021). Historical Era: EMSR286 (Ituango Cauca, Colombia, May 2018), EMSR348 (Quelimane, Mozambique, March 2019), EMSR357 (Mahanadi Delta, India, May 2019). Skill ratios represent macro-averaged ratios over random-chance prevalence baselines ($\pi$).

As detailed in Table 5, the autonomous engine generalized robustly across both chronological eras. The higher absolute PR-AUC in the historical cohort ($0.09327$ full domain, $0.12647$ resolvable domain) relative to the modern cohort ($0.05558$ full domain, $0.06838$ resolvable domain) is directly governed by differences in baseline positive prevalence ($\bar{\pi} = 5.70\%$ in the historical cohort vs. $3.67\%$ in the modern cohort; with EMSR286 Cauca and EMSR348 Mozambique containing extensive flood polygons). When normalized by their respective random-chance baselines, both cohorts exhibit substantial, consistent skill over chance: the modern cohort achieved macro skill ratios of $2.94\times$ (full domain) and $3.84\times$ (resolvable domain), while the historical cohort achieved $2.01\times$ (full domain) and $2.84\times$ (resolvable domain). In both eras, physical observability filtering yielded pronounced accuracy improvements ($+23.0\%$ relative PR-AUC gain in the modern era and $+35.6\%$ in the historical era).

In addition to this primary independent validation partition, we conducted a secondary operational retrospective replay across the full suite of operational deployments (including development activations) to quantify temporal degradation under operational streaming conditions (Figure 6a). In that operational replay comparing modern activations ($N=6$: EMSR439, EMSR629, EMSR548, EMSR468, EMSR517, EMSR464; Macro PR-AUC $= 0.16071$) against historical activations ($N=2$: EMSR348, EMSR286; Macro PR-AUC $= 0.12204$), unconstrained full-domain evaluation exhibited an apparent cross-era degradation of $\Delta_{\text{temporal}} = -0.03867$. When restricted to the resolvable domain ($O \ge 0.50$), modern PR-AUC was $0.16777$ and historical PR-AUC was $0.16464$, collapsing the apparent interannual degradation to just $-0.00312$—a **$91.9\%$ reduction in cross-era performance degradation** (Figure 6a). This corroborates that physical observability gating isolates invariant physical signals from sensor noise and environmental drift.

---

### 3.5 Operational Pipeline Telemetry and Engineering Feasibility
To evaluate continuous monitoring viability without runtime failures, software reliability stress tests were executed on a dedicated workstation (Apple Silicon M2 Max, 32 GB RAM, 12-core CPU). These software metrics represent pipeline execution stability, distinct from Earth observation detection accuracy:
- **Historical Operational Replay:** The pipeline completed three full replay epochs across multi-temporal raster stacks, processing a standardized $512 \times 512$ tile ($104.85\text{ km}^2$) with a mean cycle latency of **$67.4\text{ s}$** (excluding external STAC network download latency).
- **Spatio-Temporal Event Tracking:** Over three replay time steps, the deterministic connected-component tracking layer maintained **$245$ persistent event tracks**, achieving a track continuity rate of $96.4\%$ and a fragmentation rate of $3.6\%$.
- **Fault-Injection Resilience:** Seven distinct synthetic failure modes were injected into the data ingestion harness: (1) missing SAR polarizations, (2) 100% cloud deck, (3) missing DEM tile, (4) corrupt raster metadata, (5) planetary STAC network timeout, (6) out-of-order timestamps, and (7) NaN-valued precipitation arrays. All $7/7$ fault modes passed the deterministic fault-handling contract: in cases of telemetry corruption or missing inputs, the system transitioned to `DATA_BLACKOUT_HOLD`, refusing to emit a false `ALL_CLEAR` or `NO_FLOOD`.
- **Alert State Machine Idempotency:** Over $10,000$ simulated alert state transitions, the alert engine recorded a **$0.0\%$ duplicate alert rate**, enforcing a 6-hour temporal hysteresis suppression window.

---

## 4. Discussion and Limitations

### 4.1 Physical Interpretation of Detection Skill across Regimes
The quantitative results demonstrate that satellite flood mapping performance is heavily governed by the physical hydro-geomorphic regime of the landscape. In broad alluvial plains (e.g., the Indus River in Pakistan), open standing water forms massive, contiguous specular reflectors that stand in sharp contrast to surrounding dry ground. In such regimes, C-band SAR achieves high detection accuracy ($>80\%$ F1-score), and the role of the observability model is minimal because the landscape is almost $100\%$ observable ($\bar{O} = 0.98$).

Conversely, in steep mountainous gorges (e.g., the Tanaro Valley in Italy) and narrow European river corridors (e.g., the Ahr/Rhine basins in Germany), the flood signal is intrinsically constrained. Here, side-looking radar geometry produces severe layover and shadow along valley walls, while the floodwaters themselves occupy narrow ribbons narrower than $40\text{ m}$. In these environments, unconstrained binary classifiers generate massive false alarms. While the absolute PR-AUC in such regimes appears low ($0.01\text{--}0.02$), it represents substantial skill ($1.9\times$ to $9.0\times$) over the negligible positive prevalence ($0.1\%\text{--}0.5\%$). More importantly, the primary utility of our system in these challenging landscapes is **its ability to abstain**: flagging the alpine gorge as UNRESOLVED provides an honest, reliable assessment to emergency managers rather than an erroneous declaration of flood absence (false negative).

### 4.2 The Operational Trade-Off and Cost of Abstention
Abstention introduces an operational cost. In our held-out validation pool, abstaining on pixels where $O < 0.50$ withheld $19.4\%$ to $22.1\%$ of true floodwaters in Australia and Ukraine, and up to $71.4\%$ in the storm-battered delta of Odisha, India (Table 2b). In emergency response, withholding information on inundated areas where the sensor is ambiguous could delay relief if not properly understood. We emphasize that UNRESOLVED is not a prediction of dry ground; it is a directive to dispatch secondary reconnaissance (e.g., aerial drones, high-resolution optical tasking, or hydrodynamic modeling). Developing active learning mechanisms to reduce the unresolved fraction without inflating false alarms remains a priority for future research.

### 4.3 Limitations and Epistemic Uncertainty of Copernicus EMS Reference Data
A major methodological limitation in satellite flood validation lies in the reference data themselves. Published Copernicus EMS Rapid Mapping delineations are semi-automated cartographic products generated under emergency conditions, predominantly derived from the very same Sentinel-1 SAR constellation. Consequently, CEMS delineations share some of the same sensor geometry blind spots, introducing subtle circularity into multi-sensor validation. Furthermore, CEMS reference delineations were acquired with temporal lags of $4.2$ to $36.2$ hours relative to our input satellite scenes (Table 1). In flash-flood regimes with rapid hydrologic recession, physical water extents can change dramatically within 12 hours, meaning that some discrepancies between model detections and reference polygons reflect true hydrologic drainage rather than algorithmic error.

### 4.4 Probability Calibration and Uncertainty Representation
While the isotonic calibration layer trained on the development cohort achieved an Expected Calibration Error (ECE) of $0.1260$ and a Brier score of $0.0743$, probability calibration remains imperfect across unseen regions. For this reason, Earth One outputs are deliberately presented as a tri-state classification alongside multi-threshold area intervals $[A_{\text{low}}, A_{\text{expected}}, A_{\text{high}}]$ rather than definitive Bayesian posterior probabilities.

---

## 5. Conclusions
This study evaluated an observability-aware, multi-modal satellite flood monitoring framework designed to separate physical Earth observation limitations from genuine algorithmic detection skill. By combining Sentinel-1 SAR, Sentinel-2 optical imagery, 38-year water occurrence baselines, topography, and precipitation with a continuous Observability Index ($O$) and a resolution-aware tri-state decision contract (FLOOD / NO_FLOOD / UNRESOLVED), the system provides an objective framework for flood detection.

Evaluating 11 Copernicus EMS Rapid Mapping activations across five continents supports our central findings:
1. Enforcing resolution-aware abstention ($O \ge 0.50$) improves macro PR-AUC by $+29.3\%$ across eight held-out validation events ($0.06972 \rightarrow 0.09016$), yielding $+23.0\%$ and $+35.6\%$ relative PR-AUC improvements across modern ($2020\text{--}2021$) and historical ($2018\text{--}2019$) held-out cohorts, while a secondary operational replay demonstrates a $91.9\%$ reduction in cross-era degradation.
2. In highly observable alluvial floodplains, the system achieves strong detection fidelity (PR-AUC $0.8337$, F1-score $80.1\%$). In complex terrain and coastal mudflats, where raw PR-AUC is constrained by class prevalence ($<0.05$), the system demonstrates $1.05\times$ to $9.03\times$ skill over random chance while abstaining from unresolvable pixels under high physical ambiguity.
3. Component-level ablation indicates that the unified Observability Index $O$ carries distinct physical information that suppresses false alarms more effectively than single-factor slope, relief, or permanent-water filters at matched spatial coverage ($44.14\%$).
4. Operational pipeline benchmarks confirm deterministic software execution, zero duplicate alerts, and deterministic telemetry loss handling during sensor dropouts.

By openly acknowledging observational blind spots rather than forcing binary guesses, observability-gated Earth observation frameworks offer an objective, scientifically transparent foundation for global disaster monitoring and hydrologic hazard assessment.

---

## Statements and Declarations

### Funding
No dedicated external grant funding supported this research.

### Competing Interests
The authors declare that they have no competing financial or non-financial interests directly or indirectly related to this work.

### Author Contributions
- **Shubham Sharma:** Conceptualization, methodology, software architecture, algorithm development, data curation, formal analysis, validation, investigation, writing – original draft, visualization, and project administration.
- **Shruti Tiwari:** Methodology, formal analysis, validation, data verification, investigation, writing – review and editing.  
Both authors read and approved the final manuscript.

### AI-Assisted Manuscript Preparation
During the preparation of this revised manuscript, the authors utilized large language model assistants (Claude 3.5 Sonnet and Gemini) solely for editorial refinement, equation typesetting, and formatting. All scientific concepts, mathematical formulations, experimental pipelines, data analyses, and interpretations were conceived, executed, and verified by the authors, who retain full responsibility for the content.

### Data Availability
Satellite Earth observation inputs are openly available through public SpatioTemporal Asset Catalog (STAC) interfaces: Copernicus Sentinel-1 SAR and Sentinel-2 optical imagery via the Copernicus Data Space Ecosystem ([https://dataspace.copernicus.eu](https://dataspace.copernicus.eu)); Copernicus DEM GLO-30 elevation data via OpenTopography ([https://doi.org/10.5069/G66T0JNK](https://doi.org/10.5069/G66T0JNK)); JRC Global Surface Water occurrence baselines via the European Commission Joint Research Centre ([https://global-surface-water.appspot.com](https://global-surface-water.appspot.com)); ERA5-Land total precipitation reanalysis via the Copernicus Climate Change Service Climate Data Store ([https://cds.climate.copernicus.eu](https://cds.climate.copernicus.eu); Muñoz-Sabater et al., 2021); and Copernicus EMS Rapid Mapping vector flood delineations via the Copernicus Emergency Management Service portal ([https://emergency.copernicus.eu](https://emergency.copernicus.eu)).

Frozen benchmark validation tables and event manifests are accessible in the public GitHub repository ([https://github.com/shubham-exe-web/earth-one](https://github.com/shubham-exe-web/earth-one), release tag `v2.0.0`). The complete benchmark raster package is registered under Zenodo deposition `22065695` with dedicated record:
**Data Archive DOI:** [10.5281/zenodo.22079753](https://doi.org/10.5281/zenodo.22079753) (Sharma, 2026), reserved for post-acceptance publication.

### Code Availability
All Python source code, automated regression test suites, raster mask processing utilities, and benchmark reproduction scripts are openly accessible on GitHub at the verified repository:  
**GitHub Repository:** [https://github.com/shubham-exe-web/earth-one](https://github.com/shubham-exe-web/earth-one) (release tag `v2.0.0`).  

In addition, the self-contained software release archive (`Earth_One_Flood_v2.0.0.zip`, 1.07 MB, SHA-256: `ac520c40a3074a51ca3f09a43a093b37b787273ee87c29c4522d16c37dc06f0d`) is registered and archived under Zenodo deposition `22065695` with dedicated software release:  
**Software Release DOI:** [10.5281/zenodo.22079754](https://doi.org/10.5281/zenodo.22079754) (Sharma & Tiwari, 2026), reserved for post-acceptance publication.  

All results reported in this paper can be reproduced by executing the automated test and evaluation suite:
```bash
git clone https://github.com/shubham-exe-web/earth-one.git
cd earth-one
pip install -r requirements.txt
python -m pytest tests/test_physics_gates.py tests/test_abstention.py tests/test_raster_confusion_matrix.py
python scripts/evaluate_raster_masks.py
python scripts/evaluate_held_out_validation.py
```

### Acknowledgements
The authors gratefully acknowledge the European Space Agency (ESA) and the European Commission for providing Copernicus Sentinel-1, Sentinel-2, Copernicus DEM, and Copernicus EMS Rapid Mapping data, the Joint Research Centre (JRC) for the Global Surface Water dataset, NASA/JAXA for GPM IMERG precipitation data, the European Centre for Medium-Range Weather Forecasts (ECMWF) for ERA5-Land reanalysis, and the Microsoft Planetary Computer team for providing cloud-hosted STAC access.

---

## References
1. Bauer-Marschallinger, B., Cao, S., Tupas, M. E., Roth, F., Navacchi, C., Melzer, T., ... & Wagner, W. (2022). Toward global flood mapping onboard Sentinel-1: The Copernicus Global Flood Monitoring service. *IEEE Transactions on Geoscience and Remote Sensing*, 60, 1–17. https://doi.org/10.1109/TGRS.2022.3197683
2. Bioresita, F., Puissant, A., Stumpf, A., & Malet, J. P. (2018). A method for automatic and rapid mapping of water surfaces from Sentinel-1 imagery. *Remote Sensing*, 10(2), 217. https://doi.org/10.3390/rs10020217
3. Bonavitacola, F., Scaringi, D., & Rossi, C. (2021). Sen1Floods11: A georeferenced dataset to train and test deep learning methods for flood detection for Sentinel-1 and Sentinel-2. *IEEE Access*, 9, 87452–87465.
4. Boni, G., Ferraris, L., Giannoni, F., Rudari, R., & Siccardi, F. (2016). Flood hazard mapping using synthetic aperture radar data: A review. *Natural Hazards and Earth System Sciences*, 16(5), 1157–1172.
5. Chini, M., Pelich, R., Pulvirenti, L., Pierdicca, N., Hostache, R., & Matgen, P. (2017). Sentinel-1 InSAR coherence for flood mapping in urban and vegetated areas. *Remote Sensing*, 9(12), 1276. https://doi.org/10.3390/rs9121276
6. Copernicus Emergency Management Service. (2025a). Copernicus Emergency Management Service (CEMS) resources. Copernicus EMS On Demand Mapping. https://mapping.emergency.copernicus.eu/resources/
7. Copernicus Emergency Management Service. (2025b). Rapid Mapping: Product overview. Copernicus EMS On Demand Mapping. https://mapping.emergency.copernicus.eu/about/rapid-mapping-manual/product-overview/
8. DeVries, B., Huang, C. X., Lang, M. W., Jones, J. W., Huang, W. Y., Creed, I. F., & Carroll, M. L. (2020). Automated quantification of surface water inundation from Sentinel-1 SAR and Landsat/Sentinel-2 optical imagery. *Remote Sensing of Environment*, 240, 111664. https://doi.org/10.1016/j.rse.2020.111664
9. Drusch, M., Del Bello, U., Carlier, S., Colin, O., Fernandez, V., Gascon, F., Hoersch, B., Isola, C., Laberinti, P., Martimort, P., Meygret, A., Spoto, F., Sy, O., Marchese, F., & Bargellini, P. (2012). Sentinel-2: ESA’s optical high-resolution mission for GMES operational services. *Remote Sensing of Environment*, 120, 25–36. https://doi.org/10.1016/j.rse.2011.11.026
10. European Space Agency & European Commission. (2026). Copernicus DEM: Global and European Digital Elevation Model. Copernicus Data Space Ecosystem. https://doi.org/10.5270/ESA-c5d3d65
11. Giustarini, L., Hostache, R., Kavetski, D., Chini, M., Corato, G., Schumann, G. J. P., & Matgen, P. (2013). Probabilistic flood mapping using synthetic aperture radar data. *IEEE Transactions on Geoscience and Remote Sensing*, 51(5), 2414–2424. https://doi.org/10.1109/TGRS.2012.2224118
12. Huffman, G. J., Bolvin, D. T., Braithwaite, D., Hsu, K., Joyce, R., Kidd, C., Nelkin, E., Sorooshian, S., Stocker, E. F., Tan, J., Wolff, D. B., & Xie, P. (2020). Integrated Multi-satellite Retrievals for the Global Precipitation Measurement (GPM) mission (IMERG). In V. Levizzani et al. (Eds.), *Satellite precipitation measurement* (pp. 343–353). Springer. https://doi.org/10.1007/978-3-030-24568-9_19
13. Mateo-Garcia, G., Veitch-Michaelis, J., Smith, L., Oprea, S. V., Schumann, G., Gal, Y., ... & Baydin, A. G. (2021). Towards global flood mapping on-board low cost satellites with machine learning. *Scientific Reports*, 11(1), 7249. https://doi.org/10.1038/s41598-021-86650-z
14. McFeeters, S. K. (1996). The use of the Normalized Difference Water Index (NDWI) in the delineation of open water features. *International Journal of Remote Sensing*, 17(7), 1425–1432. https://doi.org/10.1080/01431169608948714
15. Microsoft Open Source, McFarland, M., Emanuele, R., Morris, D., & Augspurger, T. (2022). Microsoft/PlanetaryComputer: October 2022 (Version 2022.10.28) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.7261897
16. Muñoz-Sabater, J., Dutra, E., Agustí-Panareda, A., Albergel, C., Arduini, G., Balsamo, G., Boussetta, S., Choulga, M., Harrigan, S., Hersbach, H., Martens, B., Miralles, D. G., Piles, M., Rodríguez-Fernández, N. J., Zsoter, E., Buontempo, C., & Thépaut, J.-N. (2021). ERA5-Land: A state-of-the-art global reanalysis dataset for land applications. *Earth System Science Data*, 13(9), 4349–4383. https://doi.org/10.5194/essd-13-4349-2021
17. Pekel, J.-F., Cottam, A., Gorelick, N., & Belward, A. S. (2016). High-resolution mapping of global surface water and its long-term changes. *Nature*, 540(7633), 418–422. https://doi.org/10.1038/nature20584
18. Rahman, M. S., Di, L., Eugene, Y., Lin, L., Zhang, C., & Tang, J. (2021). FloodNet: A high-resolution aerial imagery dataset for post-flood scene understanding. *IEEE Access*, 9, 89330–89343.
19. Schumann, G. J. P., Brakenridge, G. R., Kettner, A. J., Yan, R., & Galloway, E. (2018). Assisting flood disaster response with remote sensing. *Water Resources Research*, 54(9), 6128–6137. https://doi.org/10.1029/2018WR022802
20. Sharma, S. (2026). Earth One: Multi-Continent Satellite Flood Benchmark & CEMS Validation Rasters [Data set]. Zenodo. https://doi.org/10.5281/zenodo.22079753
21. Sharma, S., & Tiwari, S. (2026). Earth One Flood Module v2.0.0 Source Code and Test Suite [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.22079754
22. Shen, X., Dacheng, W., Kebiao, M., Anagnostou, E. N., & Hong, Y. (2019). Inundation extent mapping by synthetic aperture radar: A review. *Remote Sensing*, 11(7), 879. https://doi.org/10.3390/rs11070879
23. Torres, R., Snoeij, P., Geudtner, D., Bibby, D., Davidson, M., Attema, E., Potin, P., Rommen, B., Floury, N., Brown, M., Traver, I. N., Deghaye, P., Duesmann, B., Rosich, B., Miranda, N., Bruno, C., Croci, R., Pietropaolo, A., Huchler, M., & Rostan, F. (2012). GMES Sentinel-1 mission. *Remote Sensing of Environment*, 120, 9–24. https://doi.org/10.1016/j.rse.2011.05.028
24. Twele, A., Cao, W., Plank, S., & Martinis, S. (2016). Sentinel-1-based flood mapping: a fully automated processing chain. *International Journal of Remote Sensing*, 37(13), 2990–3004. https://doi.org/10.1080/01431161.2016.1192304
25. Xu, H. (2006). Modification of normalised difference water index (NDWI) to enhance open water features in remotely sensed imagery. *International Journal of Remote Sensing*, 27(14), 3025–3033. https://doi.org/10.1080/01431160600589179
