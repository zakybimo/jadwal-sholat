"""HTTP API for jadwal-sholat.

Run with:
    uvicorn jadwal.api:app --reload

Endpoints:
    GET /healthz
    GET /v1/times?city=jakarta
    GET /v1/times?lat=-6.2&lng=106.8&tz=Asia/Jakarta
    GET /v1/next?city=jakarta
    GET /v1/cities
"""
from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jadwal.core import (
    CITY_COORDINATES,
    METHOD_ALIASES,
    get_next_prayer,
    get_schedule,
)

app = FastAPI(
    title="Jadwal Sholat API",
    description=(
        "Accurate prayer times, self-hostable, no API key required. "
        "Powered by the Adhan calculation library."
    ),
    version="0.1.0",
)

# Wide-open CORS by default — self-hosters can tighten via env/config.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class PrayerTimesResponse(BaseModel):
    date: str
    location: str
    latitude: float
    longitude: float
    timezone: str
    method: str
    fajr: str
    sunrise: str
    dhuhr: str
    asr: str
    maghrib: str
    isha: str


class NextPrayerResponse(BaseModel):
    name: str
    time: str
    in_minutes: int | None
    human: str
    tomorrow: bool = False


class CityEntry(BaseModel):
    name: str
    latitude: float
    longitude: float
    timezone: str


@app.get("/healthz", tags=["meta"])
def healthz():
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/v1/times", response_model=PrayerTimesResponse, tags=["prayer"])
def times(
    city: str | None = Query(
        None,
        description="Preset name (see /v1/cities) OR any city/place name resolved via Open-Meteo.",
    ),
    lat: float | None = Query(None, description="Latitude"),
    lng: float | None = Query(None, description="Longitude"),
    tz: str | None = Query(None, description="IANA timezone"),
    day: str | None = Query(None, description="Date YYYY-MM-DD (default: today)"),
    method: str = Query("kemenag", description="Calculation method"),
    madhab: str = Query("shafi", description="shafi or hanafi"),
    refresh: bool = Query(False, description="Force re-fetch coordinates from geocoder"),
):
    """Get the full prayer schedule for a given day and location."""
    target = None
    if day:
        try:
            target = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.") from exc

    try:
        schedule = get_schedule(
            city=city,
            lat=lat,
            lng=lng,
            timezone=tz,
            target_date=target,
            method=method,
            madhab=madhab,
            refresh=refresh,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, "Geocoding service unavailable. Try again later.") from e

    return schedule.to_dict()


@app.get("/v1/next", response_model=NextPrayerResponse, tags=["prayer"])
def next_prayer(
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    tz: str | None = Query(None),
    method: str = Query("kemenag"),
    madhab: str = Query("shafi"),
    refresh: bool = Query(False, description="Force re-fetch coordinates from geocoder"),
):
    """Get the next upcoming prayer."""
    try:
        schedule = get_schedule(
            city=city, lat=lat, lng=lng, timezone=tz, method=method, madhab=madhab,
            refresh=refresh,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, "Geocoding service unavailable. Try again later.") from e

    result = get_next_prayer(schedule)
    result.setdefault("tomorrow", False)
    return result


@app.get("/v1/cities", response_model=list[CityEntry], tags=["meta"])
def list_cities():
    """List all built-in cities."""
    return [
        {"name": name, "latitude": lat, "longitude": lng, "timezone": tz}
        for name, (lat, lng, tz) in sorted(CITY_COORDINATES.items())
    ]


@app.get("/v1/methods", tags=["meta"])
def list_methods():
    """List all supported calculation methods."""
    return {"methods": sorted(set(METHOD_ALIASES.keys()))}
