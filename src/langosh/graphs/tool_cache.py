"""On-disk cache for the tool catalog.

One cache file per agents-repo. Key is a hash of the agents-path so
switching between repos doesn't clobber catalogs.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_CACHE_DIR = Path(os.path.expanduser("~/.langosh/tools_cache"))


def _cache_file(agents_path: Path) -> Path:
    digest = hashlib.sha256(str(agents_path.resolve()).encode()).hexdigest()[:16]
    return _CACHE_DIR / f"{digest}.json"


def read_cache(agents_path: Path) -> list[dict] | None:
    """Return the cached catalog for `agents_path`, or None if missing/invalid."""
    path = _cache_file(agents_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, list):
        return None
    return data


def write_cache(agents_path: Path, catalog: list[dict]) -> None:
    """Persist the catalog for `agents_path`."""
    path = _cache_file(agents_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))


def invalidate(agents_path: Path) -> None:
    """Delete the cache for `agents_path` (no-op if missing)."""
    path = _cache_file(agents_path)
    if path.is_file():
        path.unlink()
