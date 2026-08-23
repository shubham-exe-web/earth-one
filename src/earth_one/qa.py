from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


@dataclass
class FileQA:
    exists: bool
    bytes: int
    sha256: str | None
    readable: bool


def inspect_file(path: Path) -> FileQA:
    if not path.exists():
        return FileQA(False, 0, None, False)

    digest = hashlib.sha256()
    size = 0

    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        readable = True
    except OSError:
        readable = False

    return FileQA(
        exists=True,
        bytes=size,
        sha256=digest.hexdigest() if readable else None,
        readable=readable,
    )


def assert_nonempty(path: Path) -> None:
    qa = inspect_file(path)
    if not qa.exists:
        raise FileNotFoundError(path)
    if not qa.readable:
        raise IOError(f"File cannot be read: {path}")
    if qa.bytes == 0:
        raise ValueError(f"File is empty: {path}")
