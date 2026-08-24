from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject


@dataclass(frozen=True)
class WaterBaselineSpec:
    source: str = 'JRC_GSW'
    dataset_version: str = 'GSW_1984_2024'
    permanent_water_frequency: float = 0.80
    resampling: str = 'bilinear'


@dataclass(frozen=True)
class ReferenceManifest:
    schema: str
    role: str
    source: str
    dataset: str
    input_path: str
    target_grid: dict[str, Any]
    processing: dict[str, Any]
    integrity_hash: str


@dataclass(frozen=True)
class FloodReferenceEvent:
    reference_id: str
    source: str
    activation_id: str | None
    event_date: str | None
    source_file: str
    feature_count: int


def _hash_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def normalize_water_occurrence(
    occurrence: np.ndarray,
    nodata: float | int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(occurrence, dtype=np.float32)
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != float(nodata)
    valid &= (arr >= 0.0) & (arr <= 100.0)
    frequency = np.zeros_like(arr, dtype=np.float32)
    frequency[valid] = np.clip(arr[valid] / 100.0, 0.0, 1.0)
    return frequency, valid


def read_water_baseline_to_grid(
    occurrence_path: str | Path,
    target_profile: dict[str, Any],
    *,
    resampling: Resampling = Resampling.bilinear,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    occurrence_path = Path(occurrence_path)
    with rasterio.open(occurrence_path) as src:
        raw = src.read(1).astype(np.float32)
        destination = np.full(
            (target_profile['height'], target_profile['width']),
            np.nan,
            dtype=np.float32,
        )
        reproject(
            source=raw,
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=target_profile['transform'],
            dst_crs=target_profile['crs'],
            src_nodata=src.nodata,
            dst_nodata=np.nan,
            resampling=resampling,
        )

    frequency, valid = normalize_water_occurrence(destination, nodata=np.nan)
    meta = {
        'source': 'JRC_GSW',
        'dataset': 'Global Surface Water 1984-2024',
        'source_path': str(occurrence_path),
        'target_grid': {
            'width': int(target_profile['width']),
            'height': int(target_profile['height']),
            'crs': str(target_profile['crs']),
            'transform': tuple(target_profile['transform']),
        },
        'resampling': resampling.name,
        'nodata_policy': 'invalid',
    }
    return frequency, valid, meta


def permanent_water_mask(
    occurrence_frequency: np.ndarray,
    valid_mask: np.ndarray,
    *,
    threshold: float = 0.80,
) -> np.ndarray:
    frequency = np.asarray(occurrence_frequency, dtype=np.float32)
    valid = np.asarray(valid_mask, dtype=bool)
    return valid & np.isfinite(frequency) & (frequency >= float(threshold))


def build_novelty_multiplier(
    occurrence_frequency: np.ndarray,
    valid_mask: np.ndarray,
    *,
    permanent_threshold: float = 0.80,
) -> np.ndarray:
    frequency = np.asarray(occurrence_frequency, dtype=np.float32)
    valid = np.asarray(valid_mask, dtype=bool)
    multiplier = np.full(frequency.shape, np.nan, dtype=np.float32)
    multiplier[valid] = np.clip(
        1.0 - frequency[valid] / max(1e-6, permanent_threshold),
        0.0,
        1.0,
    )
    return multiplier


def write_water_baseline_manifest(
    output: str | Path,
    occurrence_path: str | Path,
    target_profile: dict[str, Any],
    spec: WaterBaselineSpec | None = None,
) -> ReferenceManifest:
    spec = spec or WaterBaselineSpec()
    payload = {
        'schema': 'earth_one_flood_water_baseline_v1.0',
        'role': 'baseline_prior',
        'source': spec.source,
        'dataset': spec.dataset_version,
        'input_path': str(Path(occurrence_path).resolve()),
        'target_grid': {
            'width': int(target_profile['width']),
            'height': int(target_profile['height']),
            'crs': str(target_profile['crs']),
            'transform': tuple(target_profile['transform']),
        },
        'processing': asdict(spec),
    }
    manifest = ReferenceManifest(
        schema=payload['schema'],
        role=payload['role'],
        source=payload['source'],
        dataset=payload['dataset'],
        input_path=payload['input_path'],
        target_grid=payload['target_grid'],
        processing=payload['processing'],
        integrity_hash=_hash_json(payload),
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(manifest), indent=2), encoding='utf-8')
    return manifest


def rasterize_reference_geometries(
    geometries: Iterable[dict[str, Any]],
    target_profile: dict[str, Any],
) -> np.ndarray:
    return rasterize(
        [(geom, 1) for geom in geometries],
        out_shape=(target_profile['height'], target_profile['width']),
        transform=target_profile['transform'],
        fill=0,
        dtype='uint8',
        all_touched=False,
    ).astype(bool)


def load_geojson_reference(
    geojson_path: str | Path,
    target_profile: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    path = Path(geojson_path)
    doc = json.loads(path.read_text(encoding='utf-8'))
    features = doc.get('features', [])
    geometries = [
        feature.get('geometry')
        for feature in features
        if isinstance(feature, dict) and feature.get('geometry')
    ]
    mask = rasterize_reference_geometries(geometries, target_profile)
    return mask, {
        'role': 'independent_event_reference',
        'source': 'Copernicus_EMS',
        'input_file': str(path),
        'feature_count': len(geometries),
        'reference_type': 'published_flood_delineation',
    }


def load_vector_reference(
    vector_path: str | Path,
    target_profile: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    path = Path(vector_path)
    if path.suffix.lower() in {".geojson", ".json"}:
        return load_geojson_reference(path, target_profile)

    try:
        import shapefile
        geometries = []
        with shapefile.Reader(str(path)) as sf:
            for s in sf.shapes():
                if s.__geo_interface__:
                    geometries.append(s.__geo_interface__)
        mask = rasterize_reference_geometries(geometries, target_profile)
        return mask, {
            "role": "independent_event_reference",
            "source": "Copernicus_EMS",
            "input_file": str(path),
            "feature_count": len(geometries),
            "reference_type": "published_flood_delineation",
        }
    except Exception:
        try:
            import fiona
            geometries = []
            feature_count = 0
            with fiona.open(path) as src:
                for feature in src:
                    feature_count += 1
                    geom = feature.get("geometry")
                    if geom:
                        geometries.append(geom)
            mask = rasterize_reference_geometries(geometries, target_profile)
            return mask, {
                "role": "independent_event_reference",
                "source": "Copernicus_EMS",
                "input_file": str(path),
                "feature_count": feature_count,
                "reference_type": "published_flood_delineation",
            }
        except ImportError as exc:
            raise RuntimeError(
                "pyshp or fiona is required for Shapefile references. Install pyshp or fiona."
            ) from exc

def describe_reference_source(
    *,
    source: str,
    activation_id: str | None,
    source_file: str | Path,
    event_date: str | None,
    feature_count: int,
) -> FloodReferenceEvent:
    payload = {
        'source': source,
        'activation_id': activation_id,
        'source_file': str(Path(source_file).resolve()),
        'event_date': event_date,
    }
    return FloodReferenceEvent(
        reference_id=_hash_json(payload)[:20],
        source=source,
        activation_id=activation_id,
        event_date=event_date,
        source_file=str(Path(source_file).resolve()),
        feature_count=int(feature_count),
    )
