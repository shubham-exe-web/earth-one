from __future__ import annotations

import hashlib
from pathlib import Path
import requests

from .auth import CDSETokenProvider


class DownloadManager:
    """
    Authenticated, resumable-ish HTTP downloader.

    It deliberately writes to *.part first and renames only after a successful
    response. A failed download therefore cannot masquerade as a valid product.
    """

    def __init__(self, token_provider: CDSETokenProvider, timeout=120, chunk_size=1024 * 1024):
        self.tokens = token_provider
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.session = requests.Session()

    def download(self, url: str, destination: Path, overwrite=False) -> dict:
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists() and not overwrite:
            return {
                "status": "exists",
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination),
            }

        token = self.tokens.get_token()
        headers = {"Authorization": f"Bearer {token}"}

        partial = destination.with_suffix(destination.suffix + ".part")

        with self.session.get(
            url,
            headers=headers,
            stream=True,
            timeout=self.timeout,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()

            with partial.open("wb") as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)

        partial.replace(destination)

        return {
            "status": "downloaded",
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        }


def sha256(path: Path, chunk_size=1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
