"""Tests for the geocoding module."""
import json
import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from jadwal.geocoding import resolve_city

OPEN_METEO_RESPONSE = {
    "results": [
        {
            "name": "Banda Aceh",
            "latitude": 5.55,
            "longitude": 95.31667,
            "country": "Indonesia",
            "timezone": "Asia/Jakarta",
            "admin1": "Aceh",
        }
    ]
}

EMPTY_RESPONSE: dict = {"results": []}
NO_RESULTS_KEY: dict = {}


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Give each test its own throwaway cache directory."""
    monkeypatch.setenv("JADWAL_CACHE_DIR", str(tmp_path))
    return tmp_path


def _mock_httpx_client(response_data: dict, *, raise_on_get=None):
    """Return a patched httpx.Client context manager."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    if raise_on_get is not None:
        mock_client.get.side_effect = raise_on_get
    else:
        resp = MagicMock()
        resp.json.return_value = response_data
        resp.raise_for_status = MagicMock()
        mock_client.get.return_value = resp

    return mock_client


class TestOpenMeteoLookup:
    def test_parses_result_correctly(self):
        mock_client = _mock_httpx_client(OPEN_METEO_RESPONSE)
        with patch("jadwal.geocoding.httpx.Client", return_value=mock_client):
            result = resolve_city("Banda Aceh")

        assert result.lat == pytest.approx(5.55)
        assert result.lng == pytest.approx(95.31667)
        assert result.tz == "Asia/Jakarta"
        assert "Banda Aceh" in result.label
        assert "Aceh" in result.label
        assert result.source == "open-meteo"

    def test_label_includes_admin_and_country(self):
        mock_client = _mock_httpx_client(OPEN_METEO_RESPONSE)
        with patch("jadwal.geocoding.httpx.Client", return_value=mock_client):
            result = resolve_city("Banda Aceh")

        assert result.label == "Banda Aceh, Aceh, Indonesia"

    def test_empty_results_raises_value_error(self):
        mock_client = _mock_httpx_client(EMPTY_RESPONSE)
        with (
            patch("jadwal.geocoding.httpx.Client", return_value=mock_client),
            pytest.raises(ValueError, match="Could not resolve"),
        ):
            resolve_city("Atlantis")

    def test_missing_results_key_raises_value_error(self):
        mock_client = _mock_httpx_client(NO_RESULTS_KEY)
        with (
            patch("jadwal.geocoding.httpx.Client", return_value=mock_client),
            pytest.raises(ValueError, match="Could not resolve"),
        ):
            resolve_city("Nowhere")

    def test_http_error_propagates(self):
        mock_client = _mock_httpx_client({}, raise_on_get=httpx.ConnectError("timeout"))
        with (
            patch("jadwal.geocoding.httpx.Client", return_value=mock_client),
            pytest.raises(httpx.ConnectError),
        ):
            resolve_city("Jakarta")

    def test_timeout_error_propagates(self):
        err = httpx.TimeoutException("timed out")
        mock_client = _mock_httpx_client({}, raise_on_get=err)
        with (
            patch("jadwal.geocoding.httpx.Client", return_value=mock_client),
            pytest.raises(httpx.TimeoutException),
        ):
            resolve_city("Jakarta")


class TestCacheHitMiss:
    def test_cache_hit_skips_network(self, tmp_path):
        cache_data = {
            "banda_aceh": {
                "lat": 5.55,
                "lng": 95.31667,
                "tz": "Asia/Jakarta",
                "label": "Banda Aceh, Aceh, Indonesia",
                "fetched_at": "2024-01-01T00:00:00+00:00",
            }
        }
        (tmp_path / "geocode.json").write_text(json.dumps(cache_data))

        with patch("jadwal.geocoding.httpx.Client") as mock_cls:
            result = resolve_city("Banda Aceh")
            mock_cls.assert_not_called()

        assert result.lat == pytest.approx(5.55)
        assert result.source == "cache"

    def test_cache_key_is_normalized(self, tmp_path):
        """'Banda Aceh', 'banda aceh', 'Banda-Aceh' all hit the same cache entry."""
        cache_data = {
            "banda_aceh": {
                "lat": 5.55,
                "lng": 95.31667,
                "tz": "Asia/Jakarta",
                "label": "Banda Aceh",
                "fetched_at": "2024-01-01T00:00:00+00:00",
            }
        }
        (tmp_path / "geocode.json").write_text(json.dumps(cache_data))

        with patch("jadwal.geocoding.httpx.Client") as mock_cls:
            r1 = resolve_city("banda aceh")
            r2 = resolve_city("BANDA-ACEH")
            assert mock_cls.call_count == 0

        assert r1.source == r2.source == "cache"

    def test_refresh_bypasses_cache(self, tmp_path):
        cache_data = {
            "banda_aceh": {
                "lat": 5.55,
                "lng": 95.31667,
                "tz": "Asia/Jakarta",
                "label": "Banda Aceh",
                "fetched_at": "2024-01-01T00:00:00+00:00",
            }
        }
        (tmp_path / "geocode.json").write_text(json.dumps(cache_data))

        mock_client = _mock_httpx_client(OPEN_METEO_RESPONSE)
        with patch("jadwal.geocoding.httpx.Client", return_value=mock_client):
            result = resolve_city("Banda Aceh", refresh=True)
            mock_client.get.assert_called_once()

        assert result.source == "open-meteo"

    def test_result_is_written_to_cache(self, tmp_path):
        mock_client = _mock_httpx_client(OPEN_METEO_RESPONSE)
        with patch("jadwal.geocoding.httpx.Client", return_value=mock_client):
            resolve_city("Banda Aceh")

        cache = json.loads((tmp_path / "geocode.json").read_text())
        assert "banda_aceh" in cache
        entry = cache["banda_aceh"]
        assert entry["tz"] == "Asia/Jakarta"
        assert entry["lat"] == pytest.approx(5.55)
        assert "fetched_at" in entry

    def test_second_call_uses_cache(self, tmp_path):
        mock_client = _mock_httpx_client(OPEN_METEO_RESPONSE)
        with patch("jadwal.geocoding.httpx.Client", return_value=mock_client):
            resolve_city("Banda Aceh")
            resolve_city("Banda Aceh")
            assert mock_client.get.call_count == 1  # network only hit once


class TestGeocodeDisabled:
    def test_none_provider_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("JADWAL_GEOCODER", "none")
        with pytest.raises(ValueError, match="disabled"):
            resolve_city("Anywhere")

    def test_unknown_provider_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("JADWAL_GEOCODER", "bogus-provider")
        with pytest.raises(ValueError, match="Unknown geocoder"):
            resolve_city("Anywhere")


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("JADWAL_RUN_NETWORK_TESTS") != "1",
    reason="Set JADWAL_RUN_NETWORK_TESTS=1 to run live network tests",
)
def test_real_open_meteo_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("JADWAL_CACHE_DIR", str(tmp_path))
    result = resolve_city("Jakarta")
    assert result.lat == pytest.approx(-6.2, abs=0.5)
    assert result.lng == pytest.approx(106.8, abs=0.5)
    assert "Asia" in result.tz
