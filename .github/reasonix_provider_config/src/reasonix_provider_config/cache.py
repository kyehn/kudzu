"""File-based caching for API responses.

Stores raw data under /tmp/reasonix-provider-sync/ with a SHA-256 URL hash as filename.
If the cache file exists, reads it; otherwise downloads and saves it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import httpx

# User explicitly requested /tmp for caching raw data
CACHE_DIR = Path("/tmp/reasonix-provider-sync")  # noqa: S108


def _ensure_cache_dir() -> None:
    """Create cache directory if it doesn't exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(url: str) -> Path:
    """Return the cache file path for a given URL."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return CACHE_DIR / url_hash


def cache_get(url: str) -> bytes | None:
    """Return cached data for *url*, or ``None`` if not cached."""
    path = _cache_path(url)
    if path.is_file():
        return path.read_bytes()
    return None


def cache_put(url: str, data: bytes) -> None:
    """Store *data* for *url* in the cache."""
    _ensure_cache_dir()
    path = _cache_path(url)
    path.write_bytes(data)


def _parse_json(data: bytes) -> dict:
    """Parse JSON bytes to dict, exit on failure."""
    try:
        parsed = json.loads(data)
    except ValueError as exc:
        msg = f"Error: failed to parse JSON: {exc}\n"
        sys.stderr.write(msg)
        sys.exit(1)
    if not isinstance(parsed, dict):
        sys.stderr.write("Error: expected JSON object at root\n")
        sys.exit(1)
    return parsed


def cached_json(url: str) -> dict:
    """Load JSON data from cache or download it.

    If a cached file exists in /tmp/reasonix-provider-sync, read and return it.
    Otherwise download from *url*, cache the raw bytes, and return parsed JSON.

    Exits with code 1 on failure.
    """
    cached = cache_get(url)
    if cached is not None:
        return _parse_json(cached)

    try:
        resp = httpx.get(url, follow_redirects=True, timeout=60.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        sys.stderr.write(f"Error: failed to fetch {url}: {exc}\n")
        sys.exit(1)

    raw = resp.content
    cache_put(url, raw)
    return _parse_json(raw)
