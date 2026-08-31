#!/usr/bin/env python3
"""Acquire and cache authentic Sentinel-2 Level-2A GeoTIFF bands for 7 weekly timesteps during the 2020 Iowa Flash Drought."""

import json
import urllib.request
import urllib.parse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer

WEEKLY_STAC_ITEMS = [
    ("t-28", "2020-07-18", "S2B_MSIL2A_20200718T170849_R112_T15TUG_20200816T162454", "week_1_20200718"),
    ("t-21", "2020-07-28", "S2B_MSIL2A_20200728T170849_R112_T15TUG_20200817T225448", "week_2_20200728"),
    ("t-14", "2020-08-04", "S2B_MSIL2A_20200804T165849_R069_T15TUG_20200816T044118", "week_3_20200804"),
    ("t-7",  "2020-08-09", "S2A_MSIL2A_20200809T165901_R069_T15TUG_20200815T144028", "week_4_20200809"),
    ("t0",   "2020-08-17", "S2B_MSIL2A_20200817T170849_R112_T15TUG_20200818T162632", "week_5_20200817"),
    ("t+7",  "2020-08-19", "S2A_MSIL2A_20200819T165901_R069_T15TUG_20200908T092655", "week_6_20200819"),
    ("t+14", "2020-08-27", "S2B_MSIL2A_20200827T170849_R112_T15TUG_20200907T082752", "week_7_20200827"),
]

BBOX_IOWA = (-94.25, 41.95, -94.15, 42.05)
TARGET_SHAPE = (111, 86)
TARGET_CRS = "EPSG:32615"
BANDS = ["B02", "B04", "B05", "B08", "B11", "SCL"]


def get_signed_asset_url(href: str) -> str:
    sign_url = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href=" + urllib.parse.quote(href, safe="")
    req = urllib.request.Request(sign_url, headers={"User-Agent": "Earth-One-Research/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))["href"]


def main():
    repo = Path(__file__).resolve().parents[1]
    out_base = repo / "data" / "drought_raw" / "phase31_weekly_iowa_2020"
    out_base.mkdir(parents=True, exist_ok=True)

    trans = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    min_x, min_y = trans.transform(BBOX_IOWA[0], BBOX_IOWA[1])
    max_x, max_y = trans.transform(BBOX_IOWA[2], BBOX_IOWA[3])
    min_x = np.floor(min_x / 100.0) * 100.0
    min_y = np.floor(min_y / 100.0) * 100.0
    max_x = np.ceil(max_x / 100.0) * 100.0
    max_y = np.ceil(max_y / 100.0) * 100.0
    transform = rasterio.transform.from_bounds(min_x, min_y, max_x, max_y, TARGET_SHAPE[1], TARGET_SHAPE[0])

    print("=" * 80)
    print("ACQUIRING 7 WEEKLY SENTINEL-2 GRANULES OVER CENTRAL IOWA (JULY-AUG 2020)")
    print("=" * 80)

    for step, date_str, item_id, folder_name in WEEKLY_STAC_ITEMS:
        step_dir = out_base / folder_name
        step_dir.mkdir(parents=True, exist_ok=True)

        meta_file = step_dir / "stac_item.json"
        if not meta_file.exists():
            item_url = f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/{item_id}"
            req = urllib.request.Request(item_url, headers={"User-Agent": "Earth-One-Research/1.0"})
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                item_json = json.loads(resp.read().decode("utf-8"))
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(item_json, f, indent=2)
        else:
            with open(meta_file, "r", encoding="utf-8") as f:
                item_json = json.load(f)

        print(f"\n[+] Processing {step} ({date_str}) -> STAC ID: {item_id}")
        assets = item_json["assets"]

        for band in BANDS:
            tif_name = f"s2_{band.lower()}.tif"
            out_tif = step_dir / tif_name
            if out_tif.exists() and out_tif.stat().st_size > 1000:
                continue

            asset_k = next((k for k in assets if k.upper() == band.upper()), None)
            if not asset_k:
                print(f"  [!] Missing asset key {band}")
                continue

            raw_href = assets[asset_k]["href"]
            signed_href = get_signed_asset_url(raw_href)

            with rasterio.open(signed_href) as src:
                b_crs = src.crs.to_string() if src.crs else TARGET_CRS
                if b_crs != TARGET_CRS:
                    t_b = Transformer.from_crs("EPSG:4326", b_crs, always_xy=True)
                    bx_min, by_min = t_b.transform(BBOX_IOWA[0], BBOX_IOWA[1])
                    bx_max, by_max = t_b.transform(BBOX_IOWA[2], BBOX_IOWA[3])
                else:
                    bx_min, by_min, bx_max, by_max = min_x, min_y, max_x, max_y

                win = from_bounds(bx_min, by_min, bx_max, by_max, src.transform)
                resamp = rasterio.enums.Resampling.nearest if band == "SCL" else rasterio.enums.Resampling.bilinear
                arr = src.read(1, window=win, out_shape=TARGET_SHAPE, resampling=resamp)

                dtype = rasterio.uint8 if band == "SCL" else rasterio.uint16
                with rasterio.open(
                    out_tif,
                    "w",
                    driver="GTiff",
                    height=TARGET_SHAPE[0],
                    width=TARGET_SHAPE[1],
                    count=1,
                    dtype=dtype,
                    crs=TARGET_CRS,
                    transform=transform,
                ) as dst:
                    dst.write(arr.astype(dtype), 1)

            print(f"  * Cached {band} -> {out_tif.name} (shape {arr.shape})")

    print("\n[+] All 7 Weekly Granules Successfully Acquired and Cached!")


if __name__ == "__main__":
    main()
