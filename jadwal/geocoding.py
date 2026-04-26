"""Geocoding support for jadwal-sholat.

Resolves city/place names to (lat, lng, IANA timezone) using the Open-Meteo
free geocoding API (no key required). Results are cached on disk so subsequent
lookups for the same city are fully offline.

Environment variables:
  JADWAL_GEOCODER         open-meteo (default) | none
  JADWAL_GEOCODE_TIMEOUT  HTTP timeout in seconds (default: 5)
  JADWAL_CACHE_DIR        Override cache directory
  JADWAL_USER_AGENT       HTTP User-Agent header
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from jadwal import __version__


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    tz: str
    label: str
    source: str  # "open-meteo" or "cache"


def _cache_dir() -> Path:
    override = os.environ.get("JADWAL_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "jadwal"


def _cache_path() -> Path:
    return _cache_dir() / "geocode.json"


def _load_cache() -> dict:
    path = _cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(data: dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _normalize_key(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def _open_meteo_lookup(name: str) -> GeocodeResult | None:
    """Call the Open-Meteo geocoding API. Returns None if no result found.

    Raises httpx.HTTPError on network / server failures — callers decide how
    to surface the error.
    """
    timeout = float(os.environ.get("JADWAL_GEOCODE_TIMEOUT", "5"))
    user_agent = os.environ.get("JADWAL_USER_AGENT", f"jadwal-sholat/{__version__}")

    params = {"name": name, "count": 1, "language": "en", "format": "json"}
    with httpx.Client(timeout=timeout, headers={"User-Agent": user_agent}) as client:
        response = client.get(
            "https://geocoding-api.open-meteo.com/v1/search", params=params
        )
        response.raise_for_status()
        data = response.json()

    results = data.get("results")
    if not results:
        return None

    r = results[0]
    tz = r.get("timezone")
    if not tz:
        return None

    parts = [r.get("name", "")]
    if r.get("admin1"):
        parts.append(r["admin1"])
    if r.get("country"):
        parts.append(r["country"])
    label = ", ".join(p for p in parts if p)

    return GeocodeResult(
        lat=float(r["latitude"]),
        lng=float(r["longitude"]),
        tz=tz,
        label=label,
        source="open-meteo",
    )


def resolve_city(name: str, *, refresh: bool = False) -> GeocodeResult:
    """Resolve a city/place name to coordinates and IANA timezone.

    Checks the on-disk cache first (unless refresh=True). Calls the configured
    geocoding provider on a cache miss. Persists the result to cache.

    Raises:
        ValueError: city cannot be resolved (empty result or provider disabled).
        httpx.HTTPError: network or server failure — callers should catch and
            translate to an appropriate user-facing error.
    """
    provider = os.environ.get("JADWAL_GEOCODER", "open-meteo").lower()
    if provider == "none":
        raise ValueError(
            f"Unknown city '{name}'. "
            "Remote geocoding is disabled (JADWAL_GEOCODER=none). "
            "Pass --lat and --lng explicitly."
        )

    key = _normalize_key(name)
    cache = _load_cache()

    if not refresh and key in cache:
        entry = cache[key]
        return GeocodeResult(
            lat=entry["lat"],
            lng=entry["lng"],
            tz=entry["tz"],
            label=entry["label"],
            source="cache",
        )

    if provider == "open-meteo":
        result = _open_meteo_lookup(name)
    else:
        raise ValueError(f"Unknown geocoder provider: '{provider}'.")

    if result is None:
        raise ValueError(
            f"Could not resolve city '{name}'. "
            "Try a different spelling, or pass --lat and --lng explicitly."
        )

    cache[key] = {
        "lat": result.lat,
        "lng": result.lng,
        "tz": result.tz,
        "label": result.label,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(cache)
    return result
