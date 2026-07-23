"""Shared filename sanitization for uploaded files."""

from __future__ import annotations

import re
from pathlib import Path

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str, fallback: str = "upload") -> str:
    """Return a filesystem-safe version of an uploaded filename.

    Args:
        name: The original, possibly untrusted, filename.
        fallback: Returned when sanitization strips the name down to nothing.

    Returns:
        A filename containing only ASCII letters, digits, dots, underscores
        and hyphens.
    """
    base = Path(name).name
    cleaned = _FILENAME_SAFE.sub("_", base).strip("._")
    return cleaned or fallback
