
from __future__ import annotations

"""Earth One runtime configuration.

Loads a local env file outside the project by default:
~/.config/earth_one/earth_one.env

The file is never written by the runtime unless configured by the setup CLI.
"""

from pathlib import Path
import os


DEFAULT_ENV_FILE = Path.home() / ".config" / "earth_one" / "earth_one.env"


def load_env_file(path: str | Path | None = None) -> Path | None:
    p = Path(path).expanduser() if path else DEFAULT_ENV_FILE
    if not p.exists():
        return None

    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if ((value.startswith("'") and value.endswith("'")) or
                (value.startswith('"') and value.endswith('"'))):
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return p


def env_status() -> dict[str, bool]:
    keys = [
        "CDSE_CLIENT_ID",
        "CDSE_CLIENT_SECRET",
        "EARTH_ONE_SMTP_HOST",
        "EARTH_ONE_SMTP_USERNAME",
        "EARTH_ONE_SMTP_PASSWORD",
        "EARTH_ONE_ALERT_FROM",
        "EARTH_ONE_ALERT_TO",
    ]
    return {k: bool(os.getenv(k)) for k in keys}
