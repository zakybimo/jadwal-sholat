# Technical Documentation

Deep-dive reference for the `jadwal-sholat` codebase — architecture, data flow, module contracts, calculation engine, and extension points.

---

## Project overview

`jadwal-sholat` is a Python package that computes Islamic prayer times and exposes them through two interfaces: a terminal CLI and a FastAPI HTTP API. Both interfaces are thin wrappers around a shared pure-logic core. The same `get_schedule()` function powers both.

```
User
 ├── jadwal CLI  (jadwal/cli.py)    ← renders with Rich
 ├── HTTP client (jadwal/api.py)    ← responds with JSON / Pydantic
 └── Python code (import jadwal)    ← uses PrayerSchedule dataclass

                      │
                      ▼
              jadwal/core.py
       resolve_location()           ← preset lookup + geocoder fallback
       resolve_method()
       get_schedule()               ← single source of truth
       get_next_prayer()

                      │
            ┌─────────┴─────────┐
            ▼                   ▼
       adhanpy             jadwal/geocoding.py
  (solar calculations)    (city name → lat/lng/tz)
                               │
                         Open-Meteo API
                         + on-disk cache
```

**Key design invariant:** The CLI and the API never duplicate logic. All prayer-time computation, location resolution, and method normalization lives in `core.py`. Adding a feature means touching `core.py` first, then surfacing it in `cli.py` and `api.py`.

---

## Repository layout

```
jadwal-sholat/
├── jadwal/
│   ├── __init__.py      Public re-exports (PrayerSchedule, get_schedule, …)
│   ├── core.py          All logic — pure functions, no I/O beyond geocoding
│   ├── geocoding.py     City name → (lat, lng, tz) via Open-Meteo + disk cache
│   ├── cli.py           Typer CLI — calls core, renders with Rich
│   └── api.py           FastAPI app — calls core, returns Pydantic models
├── tests/
│   ├── test_core.py         Unit tests for resolve_location, get_schedule, get_next_prayer
│   ├── test_api.py          Integration tests via FastAPI TestClient
│   └── test_geocoding.py    Unit tests for geocoding module (httpx mocked)
├── examples/
│   └── library_usage.py Standalone runnable example
├── Dockerfile           Multi-stage build → production image
├── pyproject.toml       Package metadata, dependencies, tool config
└── .github/workflows/ci.yml   CI: lint + test on Python 3.10/3.11/3.12
```

---

## Module reference

### `jadwal/core.py`

The business logic layer. No framework imports. Testable in isolation. The only I/O is a lazy import of `jadwal.geocoding` when a non-preset city is encountered.

#### Constants

**`CITY_COORDINATES: dict[str, tuple[float, float, str]]`**

Maps a normalized city key (lowercase, underscores) to `(latitude, longitude, IANA_timezone)`. This is the only place preset city data is defined — both the CLI's `jadwal cities` command and the API's `GET /v1/cities` endpoint read from this dict.

```python
CITY_COORDINATES = {
    "jakarta": (-6.2088, 106.8456, "Asia/Jakarta"),
    "kuala_lumpur": (3.1390, 101.6869, "Asia/Kuala_Lumpur"),
    ...
}
```

Adding a city here automatically exposes it in both interfaces and makes it available offline.

**`METHOD_ALIASES: dict[str, CalculationMethod]`**

Maps user-friendly lowercase strings to `adhanpy.calculation.CalculationMethod` enum values.

```python
METHOD_ALIASES = {
    "kemenag":   CalculationMethod.SINGAPORE,   # 20°/18° — see below
    "indonesia": CalculationMethod.SINGAPORE,
    "mwl":       CalculationMethod.MUSLIM_WORLD_LEAGUE,
    "egyptian":  CalculationMethod.EGYPTIAN,
    ...
}
```

`kemenag` and `indonesia` map to `SINGAPORE` because `adhanpy`'s Singapore method (Fajr 20°, Isha 18°) matches the actual Kemenag RI twilight angles — not MWL (18°/17°). In addition, `get_schedule()` automatically applies a **+2 minute ihtiyat** (safety margin, احتياط) to every prayer start and a **−2 minute** adjustment to Sunrise for these two methods, matching the official Indonesian government prayer schedule published by Kemenag RI.

---

#### `PrayerSchedule` dataclass

The canonical data transfer object for a single day's prayer times.

```python
@dataclass
class PrayerSchedule:
    date: str        # ISO format, e.g. "2026-04-26"
    location: str    # Display label, e.g. "Jakarta" or "-6.2088,106.8456"
    latitude: float
    longitude: float
    timezone: str    # IANA tz, e.g. "Asia/Jakarta"
    method: str      # The alias string the user passed, e.g. "kemenag"
    fajr: str        # "HH:MM" in the location's local timezone
    sunrise: str
    dhuhr: str
    asr: str
    maghrib: str
    isha: str
```

All times are **strings in `HH:MM` format, already converted to the location's local timezone**. The UTC-to-local conversion happens inside `get_schedule()` and callers never need to handle UTC datetimes.

`sunrise` is included even though it is not a prayer. UI layers (CLI and API consumers) are responsible for marking it visually distinct.

`to_dict()` returns `dataclasses.asdict(self)` — the dict mirrors the Pydantic response model in `api.py` exactly.

`as_list()` returns an ordered `list[tuple[str, str]]` of `(prayer_name, time_string)` pairs — used by the CLI renderer.

---

#### `resolve_location(city, lat, lng, timezone, *, refresh=False) → (lat, lng, tz, label)`

Validates and normalizes location inputs.

**Resolution order (first match wins):**

1. Explicit `lat`/`lng` — used as-is; no city lookup or network call occurs.
2. `city` matches a key in `CITY_COORDINATES` — preset coordinates used; no network call.
3. `city` not found locally → `geocoding.resolve_city(city, refresh=refresh)` is called. The result is cached on disk for future offline use.
4. Geocoder returns nothing → raises `ValueError`.

**Normalization:** city keys are lowercased and spaces/hyphens are converted to underscores before lookup, so `"Kuala Lumpur"`, `"kuala-lumpur"`, and `"kuala_lumpur"` all resolve identically.

**Returns:** `(float, float, str, str)` — latitude, longitude, resolved IANA timezone, display label.

**Raises:**
- `ValueError` — city could not be resolved, or no location provided.
- `httpx.HTTPError` — geocoding network failure; callers catch and translate to user-facing messages.

**`refresh`** (keyword-only, default `False`): when `True`, bypasses the on-disk geocode cache and forces a fresh API call.

---

#### `resolve_method(method: str) → CalculationMethod`

Normalizes a method string the same way (lowercase, underscores) and returns the corresponding `CalculationMethod` enum value.

**Raises:** `ValueError` listing all valid aliases if the input is unrecognized.

---

#### `get_schedule(...) → PrayerSchedule`

Main entry point. Keyword-only arguments:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `city` | `str \| None` | `None` | City name — preset key or any place name |
| `lat` | `float \| None` | `None` | Latitude |
| `lng` | `float \| None` | `None` | Longitude |
| `timezone` | `str \| None` | `None` | IANA timezone override |
| `target_date` | `date \| None` | `None` | Date to calculate (defaults to today) |
| `method` | `str` | `"kemenag"` | Calculation method alias |
| `madhab` | `str` | `"shafi"` | `"shafi"` or `"hanafi"` |
| `refresh` | `bool` | `False` | Force re-fetch from geocoder, bypassing cache |

Internally:

1. Calls `resolve_location()` (with `refresh`) and `resolve_method()` to validate and normalize inputs.
2. Constructs an `adhanpy.calculation.CalculationParameters` object using the resolved `CalculationMethod`.
3. Sets `params.madhab` to `Madhab.HANAFI` or `Madhab.SHAFI` based on the `madhab` argument.
4. Calls `adhanpy.PrayerTimes(coords, datetime_utc, calculation_parameters=params)`.
5. Converts each UTC `datetime` from `adhanpy` to the location's timezone using `zoneinfo.ZoneInfo`.
6. Formats each time as `"HH:MM"` and returns a `PrayerSchedule`.

---

#### `get_next_prayer(schedule, now=None) → dict`

Given a computed `PrayerSchedule`, returns the next upcoming prayer relative to `now` (defaults to `datetime.now(tz)` in the schedule's timezone).

Iterates the five daily prayers (Fajr, Dhuhr, Asr, Maghrib, Isha — Sunrise is skipped) and returns the first one strictly after `now`.

Return shape:

```python
# Prayer found
{"name": "Maghrib", "time": "17:48", "in_minutes": 42, "human": "in 42m"}

# All prayers passed — next is tomorrow's Fajr
{"name": "Fajr", "time": "04:42", "in_minutes": None, "human": "tomorrow", "tomorrow": True}
```

`in_minutes` is `None` in the "tomorrow" case. Callers must handle this.

---

### `jadwal/geocoding.py`

Resolves city/place names to `(lat, lng, IANA timezone)` using the Open-Meteo free geocoding API. Results are cached on disk so subsequent lookups are fully offline.

#### `GeocodeResult` dataclass

```python
@dataclass
class GeocodeResult:
    lat: float
    lng: float
    tz: str       # IANA timezone, e.g. "Asia/Jakarta"
    label: str    # Display name, e.g. "Banda Aceh, Aceh, Indonesia"
    source: str   # "open-meteo" or "cache"
```

#### Cache

- **Location:** `~/.cache/jadwal/geocode.json` (Linux/macOS), `%LOCALAPPDATA%\jadwal\geocode.json` (Windows), or `$JADWAL_CACHE_DIR/geocode.json`.
- **Schema:** `{ "<normalized_key>": { "lat", "lng", "tz", "label", "fetched_at" } }`
- **Key normalization:** same as `resolve_location` — lowercase, spaces/hyphens → underscores. `"Banda Aceh"`, `"banda aceh"`, and `"banda-aceh"` all share one cache entry.
- **Expiry:** entries do not expire by default. Pass `refresh=True` to force a re-fetch.
- **Atomic writes:** `_save_cache()` writes to a temporary file then calls `os.replace()` so a crash mid-write never corrupts the cache.

#### `resolve_city(name, *, refresh=False) → GeocodeResult`

Main entry point for geocoding. Checks the cache first (unless `refresh=True`), then calls the configured provider.

**Raises:**
- `ValueError` — city not found (empty API result), or geocoding is disabled (`JADWAL_GEOCODER=none`), or unknown provider configured.
- `httpx.HTTPError` — network or server failure. Intentionally propagated so the CLI and API layers can translate it to appropriate user-facing messages (CLI prints in red; API returns HTTP 502).

#### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JADWAL_GEOCODER` | `open-meteo` | Provider to use. `none` disables remote geocoding entirely. |
| `JADWAL_GEOCODE_TIMEOUT` | `5` | HTTP timeout in seconds |
| `JADWAL_CACHE_DIR` | platform default | Override cache directory |
| `JADWAL_USER_AGENT` | `jadwal-sholat/<version>` | HTTP User-Agent header (required by some APIs) |

---

### `jadwal/api.py`

FastAPI application. Imports only from `jadwal.core` (plus `httpx` for error handling). Handles HTTP concerns — request parsing, response serialization, error translation — but contains no prayer-time or geocoding logic.

#### Pydantic models

- **`PrayerTimesResponse`** — mirrors `PrayerSchedule` field-for-field. If you add a field to `PrayerSchedule`, add it here too.
- **`NextPrayerResponse`** — mirrors the `get_next_prayer()` return dict.
- **`CityEntry`** — shape of each item in the `GET /v1/cities` list.

#### Error handling pattern

| Exception | HTTP status | Cause |
|-----------|-------------|-------|
| `ValueError` | 400 | Unknown city/method, invalid date, geocoder returned no result |
| `httpx.HTTPError` | 502 | Geocoding API unreachable or timed out |

The CLI follows the same pattern: `ValueError` prints in red and exits with code 1; `httpx.HTTPError` prints "Geocoding service unavailable" and exits with code 1.

#### `refresh` query parameter

Both `/v1/times` and `/v1/next` accept `?refresh=true` which is forwarded to `get_schedule(refresh=True)` and ultimately to `resolve_city(refresh=True)`. This forces a fresh geocoding API call even if the city is cached.

#### CORS

Wide-open by default (`allow_origins=["*"]`). This is intentional for self-hosters who embed the API in a local dashboard or browser extension. Restrict via environment config in production deployments.

---

### `jadwal/cli.py`

Typer application. Five subcommands (`today`, `now`, `on`, `cities`, `lookup`).

`today`, `now`, and `on` share a `_common_options()` helper that calls `get_schedule()` and surfaces both `ValueError` (bad input) and `httpx.HTTPError` (geocoding failure) as styled error messages.

`_render_schedule()` builds a Rich `Table`. Sunrise rows are dimmed/italicized to visually distinguish them from actual prayer times.

`--json` flag on `today` and `on` calls `schedule.to_dict()` and prints via `console.print_json()` — useful for piping into `jq`.

`--refresh-cache` flag on `today`, `now`, and `on` passes `refresh=True` through to `get_schedule()`.

`lookup` command calls `geocoding.resolve_city()` directly and prints the `GeocodeResult` fields. Useful for debugging ambiguous city names.

---

### `jadwal/__init__.py`

Re-exports the public API surface:

```python
from jadwal.core import PrayerSchedule, get_schedule, get_next_prayer, CITY_COORDINATES
__version__ = "0.1.0"
```

This lets callers do `from jadwal import get_schedule` without needing to know the internal module structure.

---

## Calculation engine

Prayer times depend on the position of the Sun relative to the observer. `jadwal-sholat` delegates all astronomy to `adhanpy` (a Python port of the widely-used JavaScript `adhan` library by Batoul Apps).

### How `adhanpy` computes prayer times

For each prayer, `adhanpy` performs the following steps:

1. **Solar noon (Dhuhr):** Computed as the moment the Sun crosses the observer's meridian using the Solar Transit formula. All other times derive from this anchor.

2. **Fajr and Isha (twilight angles):** Calculated by finding the time when the Sun is at a specific angle below the horizon. The angle is defined by the calculation method. For example, MWL uses 18° for Fajr and 17° for Isha — meaning Fajr begins when the Sun is 18° below the horizon in the morning.

3. **Sunrise and Maghrib:** Sunrise is when the upper limb of the Sun appears above the horizon (~0.833° below due to atmospheric refraction). Maghrib is defined as sunset, the same moment mirrored in the evening.

4. **Asr:** Determined by shadow length. Under the Shafi school, Asr begins when an object's shadow equals its own length (plus the shadow at noon). Under the Hanafi school, it begins when the shadow is twice the object's length. This is why Hanafi Asr is always later than Shafi Asr.

### `CalculationParameters` and madhab

`adhanpy.calculation.CalculationParameters` is the configuration object passed to `PrayerTimes`. It holds:

- `fajr_angle` and `isha_angle` — set by the calculation method
- `isha_interval` — used by methods that calculate Isha as a fixed offset after Maghrib (e.g., Umm al-Qura uses 90 minutes during normal days)
- `madhab` — `Madhab.SHAFI` or `Madhab.HANAFI`, controls Asr calculation
- `high_latitude_rule` — for locations near the poles where twilight angles behave unusually

`core.py` constructs this via:

```python
params = CalculationParameters(method=CalculationMethod.MUSLIM_WORLD_LEAGUE)
params.madhab = Madhab.HANAFI
```

### Timezone conversion

`adhanpy` returns all prayer times as UTC `datetime` objects. `core.py` converts them using Python's built-in `zoneinfo.ZoneInfo`:

```python
tz = ZoneInfo("Asia/Jakarta")
fmt = lambda dt: dt.astimezone(tz).strftime("%H:%M")
```

`zoneinfo` uses the system's IANA timezone database (or the `tzdata` package on systems without one). No third-party timezone library is required.

---

## Data flow — end to end

### CLI request: `jadwal today --city jakarta` (preset)

```
CLI parses args (Typer)
    │
    ▼
_common_options() calls get_schedule(city="jakarta")
    │
    ▼
resolve_location("jakarta", None, None, None)
    → key "jakarta" found in CITY_COORDINATES
    → (-6.2088, 106.8456, "Asia/Jakarta", "Jakarta")
    │
    ▼
[adhanpy calculation → PrayerSchedule → Rich Table]
```

### CLI request: `jadwal today --city "Banda Aceh"` (geocoded)

```
CLI parses args (Typer)
    │
    ▼
_common_options() calls get_schedule(city="Banda Aceh")
    │
    ▼
resolve_location("Banda Aceh", None, None, None)
    → key "banda_aceh" NOT in CITY_COORDINATES
    → geocoding.resolve_city("Banda Aceh")
         ├── cache hit? → return GeocodeResult(source="cache")
         └── cache miss → Open-Meteo API call
                          → parse response
                          → write to cache
                          → return GeocodeResult(source="open-meteo")
    → (5.55, 95.31667, "Asia/Jakarta", "Banda Aceh, Aceh, Indonesia")
    │
    ▼
[adhanpy calculation → PrayerSchedule → Rich Table]
```

### HTTP request: `GET /v1/times?city=jakarta`

```
FastAPI parses query params
    │
    ▼
times() endpoint calls get_schedule(city="jakarta", refresh=False)
    │
    ▼
[same core.py path as above]
    │
    ▼
PrayerSchedule.to_dict() → plain dict
    │
    ▼
FastAPI serializes via PrayerTimesResponse Pydantic model → JSON response
```

---

## Testing strategy

### Unit tests (`tests/test_core.py`)

Test the pure functions in `core.py` directly, with no HTTP or process overhead.

- **`TestResolveLocation`** — preset city lookup, coordinate override precedence, case normalization, no-inputs error, geocoder fallback (monkeypatched), geocoder error propagation (monkeypatched).
- **`TestResolveMethod`** — known aliases, case normalization, unknown method error.
- **`TestGetSchedule`** — valid schedule returned, times are HH:MM strings, times are chronologically ordered, Hanafi Asr is always later than Shafi Asr.
- **`TestGetNextPrayer`** — before-Fajr returns Fajr, after-Isha returns tomorrow-Fajr.

The geocoder tests monkeypatch `jadwal.geocoding.resolve_city` so that `test_core.py` never makes network calls — it verifies only that `resolve_location` correctly calls the geocoder and forwards its result.

### Geocoding tests (`tests/test_geocoding.py`)

Test `jadwal/geocoding.py` in full isolation. `httpx.Client` is mocked via `unittest.mock.patch` so no actual network calls are made.

- **`TestOpenMeteoLookup`** — correct parsing of API response (lat, lng, tz, label), empty results raise `ValueError`, missing `results` key raises `ValueError`, `httpx.ConnectError` propagates, `httpx.TimeoutException` propagates.
- **`TestCacheHitMiss`** — cache hit skips network call, normalized keys (`banda aceh` / `BANDA-ACEH`) hit the same entry, `refresh=True` bypasses cache, successful result is written to cache, second call for the same city uses cache (network called only once).
- **`TestGeocodeDisabled`** — `JADWAL_GEOCODER=none` raises `ValueError`, unknown provider string raises `ValueError`.
- **`test_real_open_meteo_lookup`** — live integration test, skipped by default. Run with `JADWAL_RUN_NETWORK_TESTS=1`.

Each test function gets an isolated temporary cache directory via the `isolated_cache` autouse fixture.

### Integration tests (`tests/test_api.py`)

Use FastAPI's `TestClient` (which wraps `httpx`) to exercise the full HTTP stack without a running server:

- Healthcheck endpoint
- `/v1/times` by city (preset) and by coordinates
- `/v1/times` with `refresh=true`
- 400 for unknown city (geocoder monkeypatched to raise `ValueError`)
- 400 for bad date format
- 502 when geocoder raises `httpx.ConnectError`
- `/v1/next` response shape
- `/v1/cities` includes expected entries
- `/v1/methods` includes expected aliases

### Running tests

```bash
pytest                   # runs all, prints coverage
pytest -v                # verbose — shows each test name
pytest --tb=short        # shorter tracebacks on failure
JADWAL_RUN_NETWORK_TESTS=1 pytest -m network   # live geocoding test
```

Coverage configuration is in `pyproject.toml` under `[tool.pytest.ini_options]` — it runs `--cov=jadwal --cov-report=term-missing` automatically.

---

## Docker and deployment

### Multi-stage build

The `Dockerfile` uses two stages to keep the final image small:

**Stage 1 — builder:**
- Copies `pyproject.toml`, `README.md`, and `jadwal/` source.
- Installs `build` and runs `python -m build --wheel` to produce a `.whl` file.
- No dev dependencies are installed here.

**Stage 2 — runtime:**
- Copies only the `.whl` from the builder.
- Installs it with `pip install` (pulls only runtime deps: `adhanpy`, `typer`, `rich`, `fastapi`, `uvicorn`, `pydantic`, `httpx`).
- Runs `uvicorn jadwal.api:app --host 0.0.0.0 --port 8000`.

Result: a minimal image with no build tools, no source code, no dev extras.

### Healthcheck

The `Dockerfile` includes a `HEALTHCHECK` that pings `/healthz` every 30 seconds. Container orchestrators (Docker Compose, Kubernetes, ECS) use this to determine whether the container is healthy and ready to receive traffic.

### Environment configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `JADWAL_GEOCODER` | `open-meteo` | Set to `none` for air-gapped environments |
| `JADWAL_GEOCODE_TIMEOUT` | `5` | Increase on slow or high-latency networks |
| `JADWAL_CACHE_DIR` | `~/.cache/jadwal` | Mount a volume here to persist the geocode cache across container restarts |
| `JADWAL_USER_AGENT` | `jadwal-sholat/0.1.0` | Identify your deployment to the geocoding API |

For containerized deployments that want the geocode cache to survive restarts, mount a volume:

```bash
docker run -p 8000:8000 \
  -v jadwal-cache:/root/.cache/jadwal \
  jadwal-sholat
```

---

## CI pipeline

`.github/workflows/ci.yml` runs on every push and pull request to `master` and `dev`.

Matrix: Python 3.10, 3.11, 3.12.

Steps:
1. Check out code.
2. Set up Python with pip caching.
3. `pip install -e ".[dev]"` — installs the package and all dev dependencies.
4. `ruff check jadwal tests` — lints both source and test directories.
5. `pytest` — runs the full test suite with coverage (network tests are skipped by default).

All three Python versions must pass before a PR can merge.

---

## Adding a new city

Edit `CITY_COORDINATES` in `jadwal/core.py`:

```python
CITY_COORDINATES = {
    ...
    "surabaya": (-7.2575, 112.7521, "Asia/Jakarta"),
    # add your city:
    "pontianak": (0.0263, 109.3425, "Asia/Pontianak"),
}
```

That's the only change needed. The CLI's `jadwal cities` listing and the API's `GET /v1/cities` response both derive from this dict at runtime. Preset cities work offline — no geocoding call is made for them.

---

## Adding a new calculation method

Edit `METHOD_ALIASES` in `jadwal/core.py`:

```python
METHOD_ALIASES = {
    ...
    "my_custom_alias": CalculationMethod.SINGAPORE,
}
```

If `adhanpy` does not have a matching `CalculationMethod` enum value, you would instead construct a `CalculationParameters` object manually with explicit `fajr_angle` and `isha_angle` values and adjust `get_schedule()` accordingly.

---

## Dependency summary

| Package | Role | Notes |
|---------|------|-------|
| `adhanpy` | Prayer time astronomy engine | Implements solar calculations and all CalculationMethod angles |
| `typer` | CLI framework | Argument parsing, help generation, subcommands |
| `rich` | Terminal rendering | Styled tables, panels, colored text |
| `fastapi` | HTTP framework | Routing, Pydantic integration, auto-generated OpenAPI docs |
| `uvicorn` | ASGI server | Runs the FastAPI app |
| `pydantic` | Response models + validation | Request parameter coercion, response serialization |
| `httpx` | HTTP client | Geocoding API calls (runtime); also used by FastAPI's `TestClient` |
| `pytest` | Test runner | Unit and integration tests |
| `pytest-cov` | Coverage reporting | Tracks which lines are exercised by tests |
| `ruff` | Linter | Fast Python linting (replaces flake8 + isort + more) |

All dependencies are standard Python packaging — no compiled extensions, no platform-specific wheels.
