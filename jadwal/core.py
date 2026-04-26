"""Core prayer time calculation logic.

This module wraps the `adhan` library and provides a clean,
typed interface used by both the CLI and the HTTP API.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.calculation.CalculationParameters import CalculationParameters
from adhanpy.calculation.Madhab import Madhab
from adhanpy.calculation.PrayerAdjustments import PrayerAdjustments
from adhanpy.PrayerTimes import PrayerTimes

# Built-in coordinates for common Indonesian and global cities.
# Users can pass --lat/--lng to override, but this covers the 80% case.
CITY_COORDINATES: dict[str, tuple[float, float, str]] = {
    "jakarta": (-6.2088, 106.8456, "Asia/Jakarta"),
    "bandung": (-6.9175, 107.6191, "Asia/Jakarta"),
    "surabaya": (-7.2575, 112.7521, "Asia/Jakarta"),
    "medan": (3.5952, 98.6722, "Asia/Jakarta"),
    "yogyakarta": (-7.7956, 110.3695, "Asia/Jakarta"),
    "makassar": (-5.1477, 119.4327, "Asia/Makassar"),
    "denpasar": (-8.6705, 115.2126, "Asia/Makassar"),
    "kuala_lumpur": (3.1390, 101.6869, "Asia/Kuala_Lumpur"),
    "singapore": (1.3521, 103.8198, "Asia/Singapore"),
    "mecca": (21.3891, 39.8579, "Asia/Riyadh"),
    "medina": (24.5247, 39.5692, "Asia/Riyadh"),
    "istanbul": (41.0082, 28.9784, "Europe/Istanbul"),
    "cairo": (30.0444, 31.2357, "Africa/Cairo"),
    "dubai": (25.2048, 55.2708, "Asia/Dubai"),
    "london": (51.5074, -0.1278, "Europe/London"),
    "new_york": (40.7128, -74.0060, "America/New_York"),
}

# Calculation method aliases (user-friendly names → adhan enum values)
METHOD_ALIASES: dict[str, CalculationMethod] = {
    "mwl": CalculationMethod.MUSLIM_WORLD_LEAGUE,
    "muslim_world_league": CalculationMethod.MUSLIM_WORLD_LEAGUE,
    "egyptian": CalculationMethod.EGYPTIAN,
    "karachi": CalculationMethod.KARACHI,
    "umm_al_qura": CalculationMethod.UMM_AL_QURA,
    "dubai": CalculationMethod.DUBAI,
    "moonsighting": CalculationMethod.MOON_SIGHTING_COMMITTEE,
    "north_america": CalculationMethod.NORTH_AMERICA,
    "kuwait": CalculationMethod.KUWAIT,
    "qatar": CalculationMethod.QATAR,
    "singapore": CalculationMethod.SINGAPORE,
    # Kemenag RI uses Fajr 20°, Isha 18° (same angles as SINGAPORE in adhanpy).
    # The official Indonesian schedule also adds a 2-minute ihtiyat safety margin;
    # that offset is applied in get_schedule() for these method keys.
    "kemenag": CalculationMethod.SINGAPORE,
    "indonesia": CalculationMethod.SINGAPORE,
}

# Methods that carry a 2-minute ihtiyat (safety margin) per Kemenag RI standard.
_IHTIYAT_METHODS = frozenset({"kemenag", "indonesia"})


@dataclass
class PrayerSchedule:
    """Represents a full day of prayer times for a location."""

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

    def to_dict(self) -> dict:
        return asdict(self)

    def as_list(self) -> list[tuple[str, str]]:
        """Return ordered (prayer_name, time_string) pairs.

        Sunrise is included because users often want it, but it's not
        technically a prayer — we mark it separately in UI layers.
        """
        return [
            ("Fajr", self.fajr),
            ("Sunrise", self.sunrise),
            ("Dhuhr", self.dhuhr),
            ("Asr", self.asr),
            ("Maghrib", self.maghrib),
            ("Isha", self.isha),
        ]


def resolve_location(
    city: str | None,
    lat: float | None,
    lng: float | None,
    timezone: str | None,
    *,
    refresh: bool = False,
) -> tuple[float, float, str, str]:
    """Resolve location inputs into (lat, lng, tz, label).

    Precedence: explicit lat/lng > built-in preset > geocoding API.
    """
    if lat is not None and lng is not None:
        tz = timezone or "UTC"
        label = f"{lat:.4f},{lng:.4f}"
        return lat, lng, tz, label

    if city:
        key = city.lower().replace(" ", "_").replace("-", "_")
        if key in CITY_COORDINATES:
            lat_, lng_, tz_ = CITY_COORDINATES[key]
            return lat_, lng_, timezone or tz_, city.title()

        # Not a built-in preset — try the remote geocoder.
        from jadwal.geocoding import resolve_city  # local import: no hard dep at import time
        result = resolve_city(city, refresh=refresh)
        return result.lat, result.lng, timezone or result.tz, result.label

    raise ValueError("Must provide either a city name or both --lat and --lng.")


def resolve_method(method: str) -> CalculationMethod:
    """Look up a calculation method by user-friendly alias."""
    key = method.lower().replace(" ", "_").replace("-", "_")
    if key not in METHOD_ALIASES:
        raise ValueError(
            f"Unknown method '{method}'. "
            f"Available: {', '.join(sorted(set(METHOD_ALIASES)))}"
        )
    return METHOD_ALIASES[key]


def get_schedule(
    *,
    city: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    timezone: str | None = None,
    target_date: date | None = None,
    method: str = "kemenag",
    madhab: str = "shafi",
    refresh: bool = False,
) -> PrayerSchedule:
    """Compute the full prayer schedule for a given day and location.

    This is the main entry point — both the CLI and the API call this.
    """
    lat_, lng_, tz_, label = resolve_location(city, lat, lng, timezone, refresh=refresh)
    calc_method = resolve_method(method)
    calc_madhab = Madhab.HANAFI if madhab.lower() == "hanafi" else Madhab.SHAFI

    day = target_date or date.today()
    coords = (lat_, lng_)
    params = CalculationParameters(method=calc_method)
    params.madhab = calc_madhab
    # Kemenag RI official schedules round up (ceil) all calculations to the next minute
    # and include a safety margin (ihtiyat): +2 min for Dhuhr and other prayers, and
    # -2 min for Sunrise. Since adhanpy rounds to the nearest minute, we mathematically
    # achieve a ceiling effect by adding an extra +0.5 minutes to all adjustments.
    if method.lower().replace(" ", "_").replace("-", "_") in _IHTIYAT_METHODS:
        params.adjustments = PrayerAdjustments(
            fajr=2.5, sunrise=-1.5, dhuhr=2.5, asr=2.5, maghrib=3.5, isha=2.5
        )

    day_dt = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo("UTC"))
    times = PrayerTimes(coords, day_dt, calculation_parameters=params)
    tz = ZoneInfo(tz_)

    def fmt(dt: datetime) -> str:
        return dt.astimezone(tz).strftime("%H:%M")

    return PrayerSchedule(
        date=day.isoformat(),
        location=label,
        latitude=lat_,
        longitude=lng_,
        timezone=tz_,
        method=method,
        fajr=fmt(times.fajr),
        sunrise=fmt(times.sunrise),
        dhuhr=fmt(times.dhuhr),
        asr=fmt(times.asr),
        maghrib=fmt(times.maghrib),
        isha=fmt(times.isha),
    )


def get_next_prayer(schedule: PrayerSchedule, now: datetime | None = None) -> dict:
    """Given a schedule, return the next upcoming prayer and time remaining."""
    tz = ZoneInfo(schedule.timezone)
    now = now or datetime.now(tz)
    today = now.date()

    prayers = [
        ("Fajr", schedule.fajr),
        ("Dhuhr", schedule.dhuhr),
        ("Asr", schedule.asr),
        ("Maghrib", schedule.maghrib),
        ("Isha", schedule.isha),
    ]

    for name, time_str in prayers:
        hour, minute = map(int, time_str.split(":"))
        prayer_dt = datetime.combine(today, datetime.min.time()).replace(
            hour=hour, minute=minute, tzinfo=tz
        )
        if prayer_dt > now:
            delta = prayer_dt - now
            return {
                "name": name,
                "time": time_str,
                "in_minutes": int(delta.total_seconds() // 60),
                "human": _humanize_delta(delta),
            }

    # All prayers for today have passed — next is tomorrow's Fajr.
    return {
        "name": "Fajr",
        "time": schedule.fajr,
        "in_minutes": None,
        "human": "tomorrow",
        "tomorrow": True,
    }


def _humanize_delta(delta: timedelta) -> str:
    """Turn a timedelta into 'in 2h 34m' style output."""
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes < 1:
        return "now"
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"in {minutes}m"
    return f"in {hours}h {minutes}m"
