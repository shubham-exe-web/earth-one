# Earth One v1.3 live Sentinel-1 run

## 1. Install
```bash
pip install -e .
```

## 2. Set credentials locally
Do not paste the secret into chat.
```bash
export CDSE_CLIENT_ID='...'
export CDSE_CLIENT_SECRET='...'
```

## 3. Preflight
```bash
earth-one s1-preflight --output data/processed/HAMFO01_S1_preflight.json
```

## 4. Dry-run scene selection
```bash
earth-one s1-auto-pair \
  --bbox 82.5916,22.7751,82.6884,22.8649 \
  --before-start 2025-01-01 \
  --before-end 2025-01-31 \
  --after-start 2026-01-01 \
  --after-end 2026-01-31 \
  --relative-orbit 19 \
  --output-dir data/processed/HAMFO01_S1_JAN25_JAN26 \
  --dry-run
```

## 5. Production run
Remove `--dry-run` only after reviewing the machine-selected pair.
