# Earth One v0.1 Architecture Contract

## Module 01: Acquisition

**Input**
- AOI
- temporal window
- collection
- quality constraints

**Output**
- immutable observation record
- STAC asset references
- provenance
- state transition

## Non-negotiable properties

### 1. Idempotency
The same satellite observation must not be treated as a new observation twice.

### 2. Provenance
Every downstream result must be traceable to:
- source collection
- source item ID
- acquisition time
- processing version
- model version
- configuration version

### 3. Quality gates
An observation must carry quality metadata before entering processing.

### 4. Separation of concerns
Discovery, download, preprocessing, inference, validation and reporting are
separate modules.

### 5. Model-agnostic acquisition
The acquisition engine must not assume which AI model will eventually process
the scene.

### 6. Failure recovery
Network/API failures must be retryable without corrupting state.

## Next interface

The next module will consume the acquisition manifest:

`observation manifest`
→ `download/cache`
→ `preprocessing job`

The preprocessing contract will produce a standardized observation cube with:
- CRS
- spatial resolution
- temporal reference
- sensor
- bands/polarizations
- nodata/quality mask
- processing lineage
