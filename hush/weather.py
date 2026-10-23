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


def icon(code: int | None, day: bool = True) -> str:
    """A picture for a weather code (emoji, so there is nothing to download)."""
    if code in (0, 1): return "☀️" if day else "🌙"
    if code == 2: return "⛅" if day else "☁️"
    if code == 3: return "☁️"
    if code in (45, 48): return "🌫️"
    if code in (51, 53, 55, 56, 57): return "🌦️"
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return "🌧️"
    if code in (71, 73, 75, 77, 85, 86): return "❄️"
    if code in (95, 96, 99): return "⛈️"
    return "🌡️"


def search(q: str, client: httpx.Client | None = None) -> list[dict]:
    r = (client or httpx).get(GEO, params={"name": q, "count": 6, "language": "en", "format": "json"}, headers=UA, timeout=10)
    r.raise_for_status()
    return [{"name": x.get("name", ""), "region": x.get("admin1", ""), "country": x.get("country", ""),
             "lat": x["latitude"], "lon": x["longitude"], "timezone": x.get("timezone", "")} for x in (r.json().get("results") or [])]


def current(lat: float, lon: float, unit: str = "c", client: httpx.Client | None = None) -> dict:
    """Now, today's high and low, details and the next days. Kept for 15 minutes."""
    key = (round(lat, 2), round(lon, 2), unit)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    r = (client or httpx).get(FORECAST, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        "timezone": "auto", "forecast_days": 5, "temperature_unit": "fahrenheit" if unit == "f" else "celsius",
        "wind_speed_unit": "mph" if unit == "f" else "kmh"}, headers=UA, timeout=10)
    r.raise_for_status()
    j = r.json()
    cur, day = j.get("current") or {}, j.get("daily") or {}
    out = {"temp": round(cur.get("temperature_2m", 0)), "text": CODES.get(cur.get("weather_code"), ""),
           "high": round((day.get("temperature_2m_max") or [0])[0]), "low": round((day.get("temperature_2m_min") or [0])[0]),
           "unit": "°F" if unit == "f" else "°C", "timezone": j.get("timezone", ""),
           "icon": icon(cur.get("weather_code"), bool(cur.get("is_day", 1))), "feels": round(cur.get("apparent_temperature", cur.get("temperature_2m", 0))),
           "humidity": cur.get("relative_humidity_2m"), "wind": round(cur.get("wind_speed_10m", 0)), "wind_unit": "mph" if unit == "f" else "km/h",
           "rain": (day.get("precipitation_probability_max") or [None])[0],
           "sunrise": ((day.get("sunrise") or [""])[0] or "")[-5:], "sunset": ((day.get("sunset") or [""])[0] or "")[-5:],
           "days": [{"date": d, "icon": icon(c), "text": CODES.get(c, ""), "high": round(hi), "low": round(lo), "rain": rp}
                    for d, c, hi, lo, rp in zip(day.get("time") or [], day.get("weather_code") or [], day.get("temperature_2m_max") or [],
                                                day.get("temperature_2m_min") or [], day.get("precipitation_probability_max") or [None] * 5)]}
    _cache[key] = (time.time(), out)
    return out
