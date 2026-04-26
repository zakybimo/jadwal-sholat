"""Tests for core prayer time logic."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from jadwal.core import (
    get_next_prayer,
    get_schedule,
    resolve_location,
    resolve_method,
)


def _geocoder_raises(*args, **kwargs):
    raise ValueError("Could not resolve city 'atlantis'.")


class TestResolveLocation:
    def test_city_lookup_returns_coords(self):
        lat, lng, tz, label = resolve_location("jakarta", None, None, None)
        assert lat == pytest.approx(-6.2088, abs=0.001)
        assert lng == pytest.approx(106.8456, abs=0.001)
        assert tz == "Asia/Jakarta"
        assert label == "Jakarta"

    def test_explicit_coords_override_city(self):
        lat, lng, tz, label = resolve_location(
            "jakarta", 40.0, -74.0, "America/New_York"
        )
        assert lat == 40.0
        assert lng == -74.0
        assert tz == "America/New_York"

    def test_unknown_city_raises(self, monkeypatch):
        import jadwal.geocoding as geo
        monkeypatch.setattr(geo, "resolve_city", _geocoder_raises)
        with pytest.raises(ValueError):
            resolve_location("atlantis", None, None, None)

    def test_geocoder_fallback_for_unknown_city(self, monkeypatch):
        import jadwal.geocoding as geo
        from jadwal.geocoding import GeocodeResult
        fake = GeocodeResult(
            lat=43.65, lng=-79.38, tz="America/Toronto", label="Toronto", source="open-meteo"
        )
        monkeypatch.setattr(geo, "resolve_city", lambda name, **kw: fake)
        lat, lng, tz, label = resolve_location("Toronto", None, None, None)
        assert lat == pytest.approx(43.65)
        assert lng == pytest.approx(-79.38)
        assert tz == "America/Toronto"
        assert label == "Toronto"

    def test_no_inputs_raises(self):
        with pytest.raises(ValueError, match="Must provide"):
            resolve_location(None, None, None, None)

    def test_city_name_is_case_insensitive(self):
        lat, _, _, _ = resolve_location("JAKARTA", None, None, None)
        assert lat == pytest.approx(-6.2088, abs=0.001)


class TestResolveMethod:
    def test_known_alias(self):
        assert resolve_method("kemenag") is not None
        assert resolve_method("mwl") is not None

    def test_case_insensitive(self):
        assert resolve_method("MWL") is not None

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown method"):
            resolve_method("bogus_method")


class TestGetSchedule:
    def test_jakarta_returns_valid_schedule(self):
        schedule = get_schedule(
            city="jakarta", target_date=date(2024, 6, 15)
        )
        assert schedule.location == "Jakarta"
        assert schedule.timezone == "Asia/Jakarta"
        # Sanity-check all prayer times are HH:MM strings
        for _, time_str in schedule.as_list():
            assert len(time_str) == 5
            assert time_str[2] == ":"

    def test_prayer_times_are_ordered(self):
        schedule = get_schedule(city="jakarta", target_date=date(2024, 6, 15))
        times = [t for _, t in schedule.as_list()]
        assert times == sorted(times), "Prayer times should be ascending"

    def test_hanafi_asr_is_later_than_shafi(self):
        shafi = get_schedule(
            city="jakarta", madhab="shafi", target_date=date(2024, 6, 15)
        )
        hanafi = get_schedule(
            city="jakarta", madhab="hanafi", target_date=date(2024, 6, 15)
        )
        assert hanafi.asr > shafi.asr


class TestGetNextPrayer:
    def test_before_fajr_returns_fajr(self):
        schedule = get_schedule(city="jakarta", target_date=date(2024, 6, 15))
        early = datetime(2024, 6, 15, 3, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_next_prayer(schedule, now=early)
        assert result["name"] == "Fajr"
        assert result["in_minutes"] is not None
        assert result["in_minutes"] > 0

    def test_after_isha_returns_tomorrow_fajr(self):
        schedule = get_schedule(city="jakarta", target_date=date(2024, 6, 15))
        late = datetime(2024, 6, 15, 23, 59, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_next_prayer(schedule, now=late)
        assert result["name"] == "Fajr"
        assert result.get("tomorrow") is True
