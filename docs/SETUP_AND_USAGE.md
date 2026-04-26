# Setup & Usage Guide

This guide covers every way to run `jadwal-sholat`: the terminal CLI, the browser-based GUI (interactive API docs), and the HTTP API for integration.

---

## Prerequisites

- Python 3.10, 3.11, or 3.12
- `pip` (comes with Python)
- Docker (optional, for containerized deployment)

---

## Installation

### Option A — Install from source (development)

Clone the repository and install in editable mode with all dev dependencies:

```bash
git clone <your-repo-url>
cd jadwal-sholat
pip install -e ".[dev]"
```

After this, the `jadwal` command is available in your shell and the package is importable.

### Option B — Virtual environment (recommended for isolation)

```bash
cd jadwal-sholat
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

pip install -e ".[dev]"
```

### Option C — Docker (no Python setup required)

```bash
docker build -t jadwal-sholat .
docker run -p 8000:8000 jadwal-sholat
```

The API is now available at `http://localhost:8000`.

---

## CLI

The CLI is the fastest way to look up prayer times from a terminal. Every command accepts the same location and method flags.

### Common flags

| Flag | Description | Example |
|------|-------------|---------|
| `--city`, `-c` | City name — preset or any place name | `--city jakarta` or `--city "Banda Aceh"` |
| `--lat` | Latitude (overrides `--city`) | `--lat -6.2088` |
| `--lng` | Longitude (overrides `--city`) | `--lng 106.8456` |
| `--tz` | IANA timezone string | `--tz Asia/Jakarta` |
| `--method`, `-m` | Calculation method | `--method kemenag` |
| `--madhab` | Asr timing school (`shafi` or `hanafi`) | `--madhab hanafi` |
| `--refresh-cache` | Force re-fetch from geocoder (ignores cache) | `--refresh-cache` |

`--lat`/`--lng` always take precedence over `--city`. When using coordinates without `--tz`, timezone defaults to UTC.

For `--city`, the resolution order is:
1. Explicit `--lat`/`--lng` wins if provided.
2. If the name matches a built-in preset (see `jadwal cities`) — used offline instantly.
3. Otherwise the name is sent to the Open-Meteo geocoding API and the result is cached locally for future offline use.

---

### `jadwal today` — Full day schedule

```bash
# Jakarta with default settings (Kemenag / Shafi)
jadwal today --city jakarta

# Any city — resolved via geocoding on first use, then cached
jadwal today --city "Banda Aceh"
jadwal today --city "Toronto"
jadwal today --city "Kota Tua, Jakarta"

# Kuala Lumpur with MWL method
jadwal today --city kuala_lumpur --method mwl

# Hanafi Asr timing in Istanbul
jadwal today --city istanbul --madhab hanafi

# Custom coordinates (Bali)
jadwal today --lat -8.4095 --lng 115.1889 --tz Asia/Makassar

# JSON output for piping into jq or other tools
jadwal today --city jakarta --json
jadwal today --city jakarta --json | jq '.fajr'

# Force re-fetch from geocoder (clears the cached entry for this city)
jadwal today --city "Banda Aceh" --refresh-cache
```

Example output:

```
            Prayer Times  •  Jakarta  •  2026-04-26
┌──────────┬───────┐
│ Prayer   │ Time  │
├──────────┼───────┤
│ Fajr     │ 04:42 │
│ Sunrise  │ 05:53 │ ← not a prayer, shown for reference
│ Dhuhr    │ 11:51 │
│ Asr      │ 15:11 │
│ Maghrib  │ 17:48 │
│ Isha     │ 18:55 │
└──────────┴───────┘
Method: kemenag  •  Timezone: Asia/Jakarta
```

---

### `jadwal now` — Next upcoming prayer

Shows only the single next prayer and how long until it starts.

```bash
jadwal now --city jakarta
jadwal now --city singapore
jadwal now --city "Banda Aceh"
jadwal now --lat 21.3891 --lng 39.8579 --tz Asia/Riyadh   # Mecca
```

Example output:

```
╭──────────────────────────────╮
│         Next Prayer          │
│ Maghrib  at 17:48  (in 14m)  │
╰──────────────────────────────╯
```

When all prayers for the day have passed, it shows `Fajr (tomorrow)`.

---

### `jadwal on` — Schedule for a specific date

```bash
jadwal on 2024-12-25 --city jakarta
jadwal on 2025-03-01 --city mecca --method umm_al_qura
jadwal on 2024-06-15 --lat -6.2 --lng 106.8 --tz Asia/Jakarta --json
jadwal on 2024-06-15 --city "Kuala Lumpur" --method mwl
```

Date must be in `YYYY-MM-DD` format.

---

### `jadwal cities` — List offline preset cities

```bash
jadwal cities
```

Lists the 16 built-in preset cities with their coordinates and timezones. These presets work without any network connection.

Any city name **not** in this list is resolved automatically via the Open-Meteo geocoding API — you don't need to add it here first.

Built-in presets:

| City | Country |
|------|---------|
| jakarta, bandung, surabaya, medan, yogyakarta, makassar, denpasar | Indonesia |
| kuala_lumpur | Malaysia |
| singapore | Singapore |
| mecca, medina | Saudi Arabia |
| istanbul | Turkey |
| cairo | Egypt |
| dubai | UAE |
| london | UK |
| new_york | USA |

---

### `jadwal lookup` — Inspect geocoding results

Resolves a city name through the geocoder and prints what was found. Useful for debugging ambiguous names or verifying the timezone that was returned.

```bash
jadwal lookup "Banda Aceh"
jadwal lookup "Springfield"        # shows which Springfield was matched
jadwal lookup "Toronto" --refresh-cache   # force a fresh API call
```

Example output:

```
Banda Aceh, Aceh, Indonesia
  Latitude:  5.55
  Longitude: 95.31667
  Timezone:  Asia/Jakarta
  Source: open-meteo
```

If the result came from the local cache, `Source` shows `cache`.

---

### Calculation methods

Pass any of these to `--method`:

| Alias | Description |
|-------|-------------|
| `kemenag` / `indonesia` | Kementerian Agama RI — Fajr 20°, Isha 18°, +2 min ihtiyat. Matches official Indonesian prayer schedules. |
| `mwl` / `muslim_world_league` | Muslim World League — Fajr 18°, Isha 17° |
| `egyptian` | Egyptian General Authority of Survey — Fajr 19.5°, Isha 17.5° |
| `karachi` | University of Islamic Sciences, Karachi — Fajr 18°, Isha 18° |
| `umm_al_qura` | Umm al-Qura University, Mecca — Fajr 18.5°, Isha 90 min after Maghrib |
| `dubai` | UAE — Fajr & Isha 18.2° |
| `moonsighting` | Moonsighting Committee — Fajr & Isha 18° with seasonal adjustments |
| `north_america` | ISNA — Fajr & Isha 15° |
| `kuwait` | Kuwait — Fajr 18°, Isha 17.5° |
| `qatar` | Qatar — Fajr 18°, Isha 90 min after Maghrib |
| `singapore` | Singapore — Fajr 20°, Isha 18° |

Default is `kemenag`. The angles control when Fajr and Isha are calculated relative to the Sun's position below the horizon (twilight angles).

---

## GUI — Interactive API browser

When the HTTP API server is running, FastAPI automatically generates two browser-based UIs that let you explore and test every endpoint without writing any code.

### Start the server

```bash
# Development (auto-reloads on file changes)
uvicorn jadwal.api:app --reload

# Production-style (no reload, port 8000)
uvicorn jadwal.api:app --host 0.0.0.0 --port 8000
```

Or with Docker:

```bash
docker build -t jadwal-sholat .
docker run -p 8000:8000 jadwal-sholat
```

### Open the GUI

| UI | URL | Description |
|----|-----|-------------|
| **Swagger UI** | `http://localhost:8000/docs` | Interactive: fill form fields, click "Execute", see live responses |
| **ReDoc** | `http://localhost:8000/redoc` | Read-only reference with full schema documentation |

### Using Swagger UI

1. Open `http://localhost:8000/docs` in your browser.
2. Click any endpoint (e.g. `GET /v1/times`).
3. Click **Try it out**.
4. Fill in the parameters (e.g. `city = Banda Aceh`).
5. Click **Execute**.
6. The response body, status code, and headers appear below.

---

## HTTP API

The API follows REST conventions. All responses are JSON. All errors return a `4xx` or `5xx` status with a `{"detail": "..."}` body.

### Base URL

```
http://localhost:8000
```

### Endpoints

#### `GET /healthz`

Liveness probe. Returns `{"status": "ok"}` when the server is up.

```bash
curl http://localhost:8000/healthz
```

---

#### `GET /v1/times` — Full prayer schedule

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `city` | string | one of city or lat+lng | Built-in preset name **or** any city/place name (resolved via geocoding) |
| `lat` | float | one of city or lat+lng | Latitude |
| `lng` | float | one of city or lat+lng | Longitude |
| `tz` | string | no | IANA timezone (defaults to city preset/geocoded value, or UTC) |
| `day` | string | no | Date `YYYY-MM-DD` (defaults to today) |
| `method` | string | no | Calculation method (default: `kemenag`) |
| `madhab` | string | no | `shafi` or `hanafi` (default: `shafi`) |
| `refresh` | bool | no | Force re-fetch from geocoder, ignoring cached result (default: `false`) |

```bash
# Built-in preset
curl "http://localhost:8000/v1/times?city=jakarta"

# Any city via geocoding
curl "http://localhost:8000/v1/times?city=Toronto"
curl "http://localhost:8000/v1/times?city=Banda%20Aceh"

# By coordinates
curl "http://localhost:8000/v1/times?lat=-6.2088&lng=106.8456&tz=Asia/Jakarta"

# Specific date
curl "http://localhost:8000/v1/times?city=mecca&day=2024-03-15&method=umm_al_qura"

# Hanafi Asr
curl "http://localhost:8000/v1/times?city=istanbul&madhab=hanafi"

# Force geocoder refresh
curl "http://localhost:8000/v1/times?city=Banda%20Aceh&refresh=true"
```

Response:

```json
{
  "date": "2026-04-26",
  "location": "Jakarta",
  "latitude": -6.2088,
  "longitude": 106.8456,
  "timezone": "Asia/Jakarta",
  "method": "kemenag",
  "fajr": "04:42",
  "sunrise": "05:53",
  "dhuhr": "11:51",
  "asr": "15:11",
  "maghrib": "17:48",
  "isha": "18:55"
}
```

**Error responses:**

| Status | Cause |
|--------|-------|
| `400` | Unknown method, invalid date format, or geocoder returned no result for the city name |
| `502` | Geocoding API is unreachable (network error or timeout) |

---

#### `GET /v1/next` — Next upcoming prayer

Same query parameters as `/v1/times` (minus `day`), including `refresh`. Returns the single next prayer relative to the current server time.

```bash
curl "http://localhost:8000/v1/next?city=jakarta"
curl "http://localhost:8000/v1/next?city=Toronto"
```

Response:

```json
{
  "name": "Maghrib",
  "time": "17:48",
  "in_minutes": 42,
  "human": "in 42m",
  "tomorrow": false
}
```

When all prayers have passed, `name` is `"Fajr"`, `tomorrow` is `true`, and `in_minutes` is `null`.

---

#### `GET /v1/cities` — List offline preset cities

```bash
curl http://localhost:8000/v1/cities
```

Response:

```json
[
  {"name": "cairo", "latitude": 30.0444, "longitude": 31.2357, "timezone": "Africa/Cairo"},
  {"name": "jakarta", "latitude": -6.2088, "longitude": 106.8456, "timezone": "Asia/Jakarta"},
  ...
]
```

This lists only the 16 built-in presets. Any other city name passed to `/v1/times` is resolved via geocoding at request time.

---

#### `GET /v1/methods` — List calculation methods

```bash
curl http://localhost:8000/v1/methods
```

Response:

```json
{"methods": ["dubai", "egyptian", "indonesia", "karachi", "kemenag", "kuwait", ...]}
```

---

## Geocoding

City names not in the built-in preset list are resolved automatically via the [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) — free, no API key required. The first lookup for a city makes a network call; all subsequent lookups for the same city are served from a local JSON cache and require no internet access.

### Cache location

| Platform | Default path |
|----------|-------------|
| Linux/macOS | `~/.cache/jadwal/geocode.json` |
| Windows | `%LOCALAPPDATA%\jadwal\geocode.json` |

Override with `JADWAL_CACHE_DIR=/path/to/dir`.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JADWAL_GEOCODER` | `open-meteo` | Set to `none` to disable remote geocoding entirely |
| `JADWAL_GEOCODE_TIMEOUT` | `5` | HTTP timeout in seconds for geocoding requests |
| `JADWAL_CACHE_DIR` | platform default | Override the cache directory |
| `JADWAL_USER_AGENT` | `jadwal-sholat/0.1.0` | HTTP User-Agent sent to the geocoding API |

### Disabling geocoding

Set `JADWAL_GEOCODER=none` to revert to the original strict offline behavior. Any city not in the built-in preset list will immediately raise an error, just as it did before geocoding was added.

```bash
JADWAL_GEOCODER=none jadwal today --city "Banda Aceh"
# Error: Unknown city 'Banda Aceh'. Remote geocoding is disabled...
```

---

## Library usage (Python)

Import directly into your own Python project:

```python
from jadwal import get_schedule, get_next_prayer

# Today's schedule (offline preset)
schedule = get_schedule(city="jakarta")
print(schedule.fajr)      # "04:42"
print(schedule.maghrib)   # "17:48"

# Any city — resolved via geocoding on first call, cached after
schedule = get_schedule(city="Banda Aceh")

# Force re-fetch from geocoder
schedule = get_schedule(city="Banda Aceh", refresh=True)

# Iterate all times
for name, time in schedule.as_list():
    print(f"{name:10s} {time}")

# Next prayer
nxt = get_next_prayer(schedule)
print(f"{nxt['name']} at {nxt['time']} ({nxt['human']})")

# Custom coordinates and date
from datetime import date
custom = get_schedule(
    lat=-8.4095,
    lng=115.1889,
    timezone="Asia/Makassar",
    target_date=date(2024, 12, 25),
    method="kemenag",
    madhab="hanafi",
)
```

See `examples/library_usage.py` for a runnable example.

---

## Running the test suite

```bash
pytest                              # all tests + coverage report
pytest tests/test_core.py           # core logic only
pytest tests/test_api.py            # API integration tests only
pytest tests/test_geocoding.py      # geocoding module tests only
pytest tests/test_core.py::TestGetSchedule::test_hanafi_asr_is_later_than_shafi
```

Run live network tests (hits the real Open-Meteo API):

```bash
JADWAL_RUN_NETWORK_TESTS=1 pytest -m network
```

Run the linter:

```bash
ruff check jadwal tests
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'adhanpy'`**
Run `pip install -e ".[dev]"` from the project root to install all dependencies.

**City name returns wrong location (e.g. wrong "Springfield")**
Open-Meteo returns the top-ranked result for ambiguous names. Run `jadwal lookup "<name>"` to see exactly which place was matched. If it's wrong, pass `--lat`/`--lng` explicitly, or add the city name along with a country/region qualifier (e.g. `"Springfield, Illinois"`).

**Times look wrong / off by an hour**
Confirm you are passing the correct `--tz` (IANA timezone string). When using `--lat`/`--lng` without `--tz`, the default is UTC. Example: `--tz Asia/Jakarta`.

**Geocoding request fails / times out**
The Open-Meteo API requires internet access. If the request fails, you will see:
- CLI: `Error: Geocoding service unavailable. Try again later.`
- API: HTTP 502 with `{"detail": "Geocoding service unavailable. Try again later."}`

Check your internet connection and retry. Once a city is cached, it works fully offline.

**Want to disable geocoding entirely (air-gapped environment)**
Set `JADWAL_GEOCODER=none`. Only the 16 built-in preset cities will work; all other names raise an error immediately without attempting a network call.

**Docker container exits immediately**
Check that port 8000 is not already in use: `lsof -i :8000`. Change the host port with `-p 9000:8000`.
