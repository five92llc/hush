"""Weather for the "tuning in" screen, from Open-Meteo (free, no key)."""
from __future__ import annotations

import time

import httpx

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
UA = {"User-Agent": "Hush/1.0 (self-hosted media player)"}
CODES = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
         56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
         71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
         85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail"}
_cache: dict[tuple, tuple[float, dict]] = {}


def search(q: str, client: httpx.Client | None = None) -> list[dict]:
    r = (client or httpx).get(GEO, params={"name": q, "count": 6, "language": "en", "format": "json"}, headers=UA, timeout=10)
    r.raise_for_status()
    return [{"name": x.get("name", ""), "region": x.get("admin1", ""), "country": x.get("country", ""),
             "lat": x["latitude"], "lon": x["longitude"]} for x in (r.json().get("results") or [])]


def current(lat: float, lon: float, unit: str = "c", client: httpx.Client | None = None) -> dict:
    """Now, today's high and low. Kept for 15 minutes."""
    key = (round(lat, 2), round(lon, 2), unit)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    r = (client or httpx).get(FORECAST, params={
        "latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code", "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto", "forecast_days": 1, "temperature_unit": "fahrenheit" if unit == "f" else "celsius"}, headers=UA, timeout=10)
    r.raise_for_status()
    j = r.json()
    cur, day = j.get("current") or {}, j.get("daily") or {}
    out = {"temp": round(cur.get("temperature_2m", 0)), "text": CODES.get(cur.get("weather_code"), ""),
           "high": round((day.get("temperature_2m_max") or [0])[0]), "low": round((day.get("temperature_2m_min") or [0])[0]),
           "unit": "°F" if unit == "f" else "°C", "timezone": j.get("timezone", "")}
    _cache[key] = (time.time(), out)
    return out
