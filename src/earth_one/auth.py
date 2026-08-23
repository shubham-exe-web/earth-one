from __future__ import annotations

import os
import time
import requests


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


class CDSETokenProvider:
    """Lazy OAuth2 client-credentials token provider for CDSE."""

    def __init__(self, client_id=None, client_secret=None, timeout=60):
        self.client_id = client_id or os.getenv("CDSE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CDSE_CLIENT_SECRET")
        self.timeout = timeout
        self._token = None
        self._expires_at = 0.0

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    def get_token(self) -> str:
        if not self.configured:
            raise RuntimeError(
                "CDSE credentials are not configured. Set CDSE_CLIENT_ID and "
                "CDSE_CLIENT_SECRET in the environment or .env file."
            )

        now = time.time()
        if self._token and now < self._expires_at - 60:
            return self._token

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        self._token = payload["access_token"]
        self._expires_at = now + int(payload.get("expires_in", 300))
        return self._token
