# jadwal-sholat

**Accurate prayer times in your terminal and as a self-hostable API. No API key. No rate limits. No tracking.**

[![PyPI](https://img.shields.io/pypi/v/jadwal-sholat.svg)](https://pypi.org/project/jadwal-sholat/)
[![Python](https://img.shields.io/pypi/pyversions/jadwal-sholat.svg)](https://pypi.org/project/jadwal-sholat/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Most prayer time services are paywalled, rate-limited, or ship with tracking. `jadwal-sholat` is a small, dependency-light Python package that gives you both a CLI and a FastAPI service you can run anywhere — your laptop, a Raspberry Pi, or a container.

Built on top of the [Adhan library](https://github.com/batoulapps/adhan-py), the same calculation engine used by major Islamic apps.

## Features

- **CLI** for quick terminal lookups (`jadwal now`, `jadwal today --city jakarta`)
- **HTTP API** for integration into your own apps (bots, dashboards, home automation)
- **Python library** — import `get_schedule()` directly in your code
- **Any city on Earth** — type any place name and it resolves via Open-Meteo geocoding (free, no key)
- **16 offline presets** for Indonesia, Malaysia, Singapore, and major global cities — no network needed for these
- **On-disk geocoding cache** — after the first lookup a city works offline forever
- **Custom coordinates** supported (lat/lng/timezone)
- **Multiple calculation methods** (Kemenag RI, MWL, Umm al-Qura, and more)
- **Shafi and Hanafi** madhab support for Asr timing
- **Dockerfile** included for one-command self-hosting

## Install

```bash
pip install jadwal-sholat
```

## CLI usage

```bash
# Today's prayer times for Jakarta (offline preset)
jadwal today --city jakarta

# Any city — resolved automatically via geocoding
jadwal today --city "Banda Aceh"
jadwal today --city "Toronto"
jadwal today --city "Kota Tua, Jakarta"

# Next prayer right now
jadwal now --city singapore

# Specific date, custom coordinates
jadwal on 2024-12-25 --lat -8.4 --lng 115.2 --tz Asia/Makassar

# Use a different calculation method
jadwal today --city london --method mwl --madhab hanafi

# JSON output for piping into other tools
jadwal today --city jakarta --json | jq

# List offline preset cities
jadwal cities

# Look up any city and inspect what the geocoder found
jadwal lookup "Banda Aceh"
```

Example output:

```
            Prayer Times  •  Jakarta  •  2024-06-15
┌──────────┬───────┐
│ Prayer   │ Time  │
├──────────┼───────┤
│ Fajr     │ 04:37 │
│ Sunrise  │ 06:00 │
│ Dhuhr    │ 11:54 │
│ Asr      │ 15:15 │
│ Maghrib  │ 17:47 │
│ Isha     │ 19:01 │
└──────────┴───────┘
Method: kemenag  •  Timezone: Asia/Jakarta
```

## API usage

Run the service locally:

```bash
uvicorn jadwal.api:app --reload
```

Or with Docker:

```bash
docker build -t jadwal-sholat .
docker run -p 8000:8000 jadwal-sholat
```

Then hit the endpoints:

```bash
curl "http://localhost:8000/v1/times?city=jakarta"
curl "http://localhost:8000/v1/times?city=Toronto"
curl "http://localhost:8000/v1/next?city=singapore"
curl "http://localhost:8000/v1/times?lat=-6.2&lng=106.8&tz=Asia/Jakarta"
```

Interactive docs are at `http://localhost:8000/docs`.

## Library usage

```python
from jadwal import get_schedule, get_next_prayer

schedule = get_schedule(city="jakarta")
print(schedule.fajr, schedule.maghrib)

nxt = get_next_prayer(schedule)
print(f"{nxt['name']} {nxt['human']}")
```

## Geocoding

Any city name that is not in the built-in preset list is resolved automatically through the [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) — free, keyless, and returns the IANA timezone in the same call.

**Resolution order:**

1. Explicit `--lat`/`--lng` — used as-is, no network call.
2. City matches a built-in preset — used as-is, no network call.
3. City not found locally → geocoding API → result cached on disk.

**Cache location:**

| Platform | Path |
|----------|------|
| Linux/macOS | `~/.cache/jadwal/geocode.json` (or `$XDG_CACHE_HOME/jadwal/`) |
| Windows | `%LOCALAPPDATA%\jadwal\geocode.json` |

Cached results never expire — city coordinates don't change. Use `--refresh-cache` to force a new lookup.

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `JADWAL_GEOCODER` | `open-meteo` | Set to `none` to disable remote geocoding entirely |
| `JADWAL_GEOCODE_TIMEOUT` | `5` | HTTP timeout in seconds |
| `JADWAL_CACHE_DIR` | platform default | Override cache directory |
| `JADWAL_USER_AGENT` | `jadwal-sholat/0.1.0` | HTTP User-Agent header |

Setting `JADWAL_GEOCODER=none` restores the strict offline-only behavior — unknown city names raise an error immediately.

## Calculation methods

| Alias            | Description                                           |
|------------------|-------------------------------------------------------|
| `kemenag`        | Kementerian Agama RI (Indonesia) — Fajr 20°, Isha 18°, +2 min ihtiyat |
| `mwl`            | Muslim World League — Fajr 18°, Isha 17°              |
| `egyptian`       | Egyptian General Authority of Survey                  |
| `karachi`        | University of Islamic Sciences, Karachi               |
| `umm_al_qura`    | Umm al-Qura University, Mecca                         |
| `dubai`          | UAE                                                   |
| `moonsighting`   | Moonsighting Committee                                |
| `north_america`  | ISNA                                                  |
| `kuwait`, `qatar`, `singapore` | Regional authorities                     |

Run `jadwal cities` to see the 16 offline preset locations. Any other city name is resolved via geocoding.

## Development

```bash
git clone https://github.com/yourname/jadwal-sholat
cd jadwal-sholat
pip install -e ".[dev]"
pytest
```

## Why build this

Most prayer time tools online are commercial, locked behind keys, or log every request. For developers who want to integrate prayer times into a personal dashboard, home assistant, or Telegram bot, there's no good self-hostable option. This is that option.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

Prayer time calculations powered by [Adhan](https://github.com/batoulapps/adhan-py) by Batoul Apps. All astronomy, none of the tracking.
