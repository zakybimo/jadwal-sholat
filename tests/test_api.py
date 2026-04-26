"""Integration tests for the FastAPI service."""
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from jadwal.api import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_times_with_city():
    response = client.get("/v1/times?city=jakarta")
    assert response.status_code == 200
    data = response.json()
    assert data["timezone"] == "Asia/Jakarta"
    assert "fajr" in data and "isha" in data


def test_times_with_coords():
    response = client.get("/v1/times?lat=-6.2&lng=106.8&tz=Asia/Jakarta")
    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Jakarta"


def test_times_unknown_city_returns_400():
    err = ValueError("Could not resolve city 'atlantis'.")
    with patch("jadwal.geocoding.resolve_city", side_effect=err):
        response = client.get("/v1/times?city=atlantis")
    assert response.status_code == 400


def test_times_geocoder_unavailable_returns_502():
    with patch("jadwal.geocoding.resolve_city", side_effect=httpx.ConnectError("fail")):
        response = client.get("/v1/times?city=toronto")
    assert response.status_code == 502


def test_times_refresh_parameter_accepted():
    response = client.get("/v1/times?city=jakarta&refresh=true")
    assert response.status_code == 200


def test_times_bad_date_returns_400():
    response = client.get("/v1/times?city=jakarta&day=not-a-date")
    assert response.status_code == 400


def test_next_prayer():
    response = client.get("/v1/next?city=jakarta")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] in {"Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"}


def test_list_cities():
    response = client.get("/v1/cities")
    assert response.status_code == 200
    cities = response.json()
    assert any(c["name"] == "jakarta" for c in cities)


def test_list_methods():
    response = client.get("/v1/methods")
    assert response.status_code == 200
    assert "kemenag" in response.json()["methods"]
