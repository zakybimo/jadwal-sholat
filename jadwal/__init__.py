"""jadwal-sholat: accurate prayer times as a CLI and HTTP API."""
from jadwal.core import (
    CITY_COORDINATES,
    PrayerSchedule,
    get_next_prayer,
    get_schedule,
)

__version__ = "0.1.0"
__all__ = [
    "PrayerSchedule",
    "get_schedule",
    "get_next_prayer",
    "CITY_COORDINATES",
    "__version__",
]
