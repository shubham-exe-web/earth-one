#!/usr/bin/env python3
"""Zenodo Synchronization Script for Earth One v2.0.0 Frozen Release.

Automates the creation, file upload, metadata updating, and publication
of the v2.0.0 release version under the existing Zenodo DOI lineage (Concept DOI: 10.5281/zenodo.22065695).

Usage:
    python scripts/publish_zenodo_v2.py --token <ZENODO_ACCESS_TOKEN>
    or set ZENODO_TOKEN environment variable.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

CONCEPT_DEPOSITION_ID = "22065695"
ARCHIVE_PATH = Path("dist/zenodo/Earth_One_Flood_v2.0.0.zip")
GITHUB_RELEASE_URL = "https://github.com/shubham-exe-web/earth-one/releases/tag/v2.0.0"
GITHUB_REPO_URL = "https://github.com/shubham-exe-web/earth-one"


def compute_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Publish Earth One v2.0.0 to Zenodo")
    parser.add_argument("--token", default=os.environ.get("ZENODO_TOKEN") or os.environ.get("ZENODO_API_TOKEN"), help="Zenodo personal access token")
    parser.add_argument("--deposition-id", default=CONCEPT_DEPOSITION_ID, help="Existing deposition / record ID to version")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without publishing")
    args = parser.parse_args()

    if not ARCHIVE_PATH.exists():
        print(f"Error: Archive not found at {ARCHIVE_PATH}. Run package script first.", file=sys.stderr)
        sys.exit(1)

    sha256_digest = compute_sha256(ARCHIVE_PATH)
    file_size_kb = ARCHIVE_PATH.stat().st_size / 1024.0

    print("=" * 80)
    print("  EARTH ONE v2.0.0 ZENODO SYNCHRONIZATION RUNNER")
    print("=" * 80)
    print(f"Archive File:     {ARCHIVE_PATH}")
    print(f"File Size:        {file_size_kb:.1f} KB")
    print(f"SHA-256 Digest:   {sha256_digest}")
    print(f"Target Concept:   10.5281/zenodo.{args.deposition_id}")
    print(f"GitHub Release:   {GITHUB_RELEASE_URL}")
    print("-" * 80)

    metadata = {
        "metadata": {
            "title": "Earth One: Autonomous Multimodal Environmental Disturbance Monitoring & Flood Module 2",
            "upload_type": "software",
            "description": (
                "<p><strong>Earth One v2.0.0 Frozen Research Release</strong>.</p>"
                "<p>Earth One is a unified, autonomous, multimodal Earth-observation disturbance monitoring engine "
                "providing zero-touch detection, biophysical regime routing, continuous physical observability quantification, "
                "multi-epoch event tracking, and blackout-safe alerting across global ecosystems.</p>"
                "<p>This release integrates <strong>Wildfire Module 1</strong> (Experiments 1–3) and <strong>Flood Module 2</strong> "
                "(Blocks 1–6F), validated across 11 global Copernicus EMS activations spanning 5 continents.</p>"
                "<ul>"
                "<li><strong>Repository & Code:</strong> GitHub v2.0.0 (<a href=\"https://github.com/shubham-exe-web/earth-one\">shubham-exe-web/earth-one</a>)</li>"
                "<li><strong>Tests Passing:</strong> 119 / 119 (100% green)</li>"
                "<li><strong>SHA-256:</strong> <code>" + sha256_digest + "</code></li>"
                "</ul>"
            ),
            "creators": [
                {
                    "name": "Sharma, Shubham",
                    "affiliation": "Earth One Collaboration"
                }
            ],
            "version": "2.0.0",
            "publication_date": "2026-08-24",
            "access_right": "open",
            "license": "Apache-2.0",
            "keywords": [
                "satellite remote sensing",
                "multimodal earth observation",
                "flood inundation detection",
                "synthetic aperture radar",
                "sentinel-1",
                "sentinel-2",
                "observability index",
                "autonomous environmental monitoring"
            ],
            "related_identifiers": [
                {
                    "identifier": GITHUB_RELEASE_URL,
                    "relation": "isSupplementTo",
                    "resource_type": "software"
                },
                {
                    "identifier": GITHUB_REPO_URL,
                    "relation": "isDocumentedBy",
                    "resource_type": "software"
                }
            ]
        }
    }

    if args.dry_run or not args.token:
        print("\n[DRY RUN / NO TOKEN] Metadata payload generated successfully:")
        print(json.dumps(metadata, indent=2))
        print("\nTo execute live publication, run:")
        print(f"  python scripts/publish_zenodo_v2.py --token <YOUR_ZENODO_TOKEN>")
        return

    # Live Zenodo Execution
    token = args.token
    base_url = "https://zenodo.org/api/deposit/depositions"

    # Step 1: Create New Version
    print(f"\n[1/4] Creating new version from deposition {args.deposition_id}...")
    req_ver = urllib.request.Request(
        f"{base_url}/{args.deposition_id}/actions/newversion?access_token={token}",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req_ver) as resp:
        ver_data = json.loads(resp.read().decode("utf-8"))
        latest_draft_url = ver_data["links"]["latest_draft"]
        new_dep_id = latest_draft_url.split("/")[-1]
        print(f"      Created new draft deposition ID: {new_dep_id}")

    # Step 2: Clean Existing Draft Files and Upload Fresh v2.0.0 Archive
    print(f"\n[2/4] Preparing file storage for {ARCHIVE_PATH.name}...")
    req_dep = urllib.request.Request(f"{base_url}/{new_dep_id}?access_token={token}")
    with urllib.request.urlopen(req_dep) as resp:
        dep_data = json.loads(resp.read().decode("utf-8"))
        bucket_url = dep_data["links"].get("bucket")
        existing_files = dep_data.get("files", [])

    for ef in existing_files:
        ef_id = ef["id"]
        ef_name = ef["filename"]
        print(f"      Removing prior version file: {ef_name}...")
        del_req = urllib.request.Request(f"{base_url}/{new_dep_id}/files/{ef_id}?access_token={token}", method="DELETE")
        try:
            with urllib.request.urlopen(del_req):
                pass
        except Exception as e:
            print(f"      Note: file cleanup notice: {e}")

    print(f"      Uploading fresh archive ({ARCHIVE_PATH.stat().st_size / 1024:.1f} KB)...")
    if bucket_url:
        with open(ARCHIVE_PATH, "rb") as f_data:
            req_up = urllib.request.Request(
                f"{bucket_url}/{ARCHIVE_PATH.name}?access_token={token}",
                data=f_data.read(),
                headers={"Content-Type": "application/octet-stream"},
                method="PUT"
            )
            with urllib.request.urlopen(req_up) as resp:
                print(f"      Upload completed successfully (Status: {resp.status}).")
    else:
        # Fallback to standard multipart deposition files endpoint
        import urllib.parse
        with open(ARCHIVE_PATH, "rb") as f_data:
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            body = (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"name\"\r\n\r\n{ARCHIVE_PATH.name}\r\n"
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"file\"; filename=\"{ARCHIVE_PATH.name}\"\r\n"
                f"Content-Type: application/zip\r\n\r\n"
            ).encode("utf-8") + f_data.read() + f"\r\n--{boundary}--\r\n".encode("utf-8")

            req_up = urllib.request.Request(
                f"{base_url}/{new_dep_id}/files?access_token={token}",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST"
            )
            with urllib.request.urlopen(req_up) as resp:
                print(f"      Upload completed successfully (Status: {resp.status}).")

    # Step 3: Update Metadata
    print(f"\n[3/4] Updating metadata for version 2.0.0...")
    req_meta = urllib.request.Request(
        f"{base_url}/{new_dep_id}?access_token={token}",
        data=json.dumps(metadata).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req_meta) as resp:
        print("      Metadata updated successfully.")

    # Step 4: Publish
    print(f"\n[4/4] Publishing version 2.0.0 on Zenodo...")
    req_pub = urllib.request.Request(
        f"{base_url}/{new_dep_id}/actions/publish?access_token={token}",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req_pub) as resp:
        pub_data = json.loads(resp.read().decode("utf-8"))
        doi = pub_data.get("doi")
        concept_doi = pub_data.get("conceptdoi")
        record_url = pub_data.get("links", {}).get("record_html")
        print("=" * 80)
        print("  PUBLICATION SUCCESSFUL!")
        print(f"  Version DOI:  {doi}")
        print(f"  Concept DOI:  {concept_doi}")
        print(f"  Record URL:   {record_url}")
        print("=" * 80)


if __name__ == "__main__":
    main()
