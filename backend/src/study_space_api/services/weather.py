from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

from ..schemas import WeatherResponse

NEA_BASE_URL = "https://api-open.data.gov.sg/v2/real-time/api"
NUS_LATITUDE = 1.2966
NUS_LONGITUDE = 103.7764


class WeatherUnavailable(RuntimeError):
    pass


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "NUS-Study-Space-Advisor/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


class WeatherService:
    def __init__(
        self,
        *,
        timeout_seconds: float = 5,
        cache_ttl_seconds: float = 300,
        stale_ttl_seconds: float = 21_600,
        fetcher: Callable[[str, float], dict[str, Any]] = _fetch_json,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.fetcher = fetcher
        self._cached: WeatherResponse | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def get_current(self) -> WeatherResponse:
        age = time.monotonic() - self._cached_at
        if self._cached is not None and age < self.cache_ttl_seconds:
            return self._cached

        async with self._lock:
            age = time.monotonic() - self._cached_at
            if self._cached is not None and age < self.cache_ttl_seconds:
                return self._cached
            try:
                temperature, humidity, wind, forecast = await asyncio.gather(
                    *(
                        asyncio.to_thread(self.fetcher, f"{NEA_BASE_URL}/{endpoint}", self.timeout_seconds)
                        for endpoint in ("air-temperature", "relative-humidity", "wind-speed", "two-hr-forecast")
                    )
                )
                current = build_weather_response(temperature, humidity, wind, forecast)
            except Exception as exc:
                if self._cached is not None and age <= self.stale_ttl_seconds:
                    return self._cached.model_copy(update={"source": "nea_cache", "is_cached": True})
                raise WeatherUnavailable("NEA weather feeds are temporarily unavailable") from exc

            self._cached = current
            self._cached_at = time.monotonic()
            return current


def build_weather_response(
    temperature_payload: dict[str, Any],
    humidity_payload: dict[str, Any],
    wind_payload: dict[str, Any],
    forecast_payload: dict[str, Any],
) -> WeatherResponse:
    station_name, temperature, observed_at = _nearest_reading(temperature_payload)
    _, humidity, _ = _nearest_reading(humidity_payload)
    _, wind_knots, _ = _nearest_reading(wind_payload)
    condition = _clementi_condition(forecast_payload)
    return WeatherResponse(
        source="nea",
        station_name=station_name,
        location_label=f"NUS · {station_name}",
        observed_at=observed_at,
        temperature_c=round(temperature, 1),
        apparent_temperature_c=round(_heat_index_c(temperature, humidity), 1),
        humidity_percent=round(humidity),
        wind_kph=round(wind_knots * 1.852, 1),
        weather_code=_weather_code(condition),
        condition=condition,
    )


def _nearest_reading(payload: dict[str, Any]) -> tuple[str, float, datetime]:
    data = payload["data"]
    latest = data["readings"][-1]
    values = {item["stationId"]: float(item["value"]) for item in latest["data"]}
    candidates = [station for station in data["stations"] if station["id"] in values]
    if not candidates:
        raise ValueError("weather payload contains no station readings")
    station = min(
        candidates,
        key=lambda item: _distance_squared(
            float(item["location"]["latitude"]),
            float(item["location"]["longitude"]),
            NUS_LATITUDE,
            NUS_LONGITUDE,
        ),
    )
    return station["name"], values[station["id"]], datetime.fromisoformat(latest["timestamp"])


def _clementi_condition(payload: dict[str, Any]) -> str:
    items = payload["data"]["items"]
    forecasts = items[-1]["forecasts"]
    for item in forecasts:
        if item["area"] == "Clementi":
            return str(item["forecast"])
    if not forecasts:
        raise ValueError("weather payload contains no area forecast")
    return str(forecasts[0]["forecast"])


def _distance_squared(latitude: float, longitude: float, target_latitude: float, target_longitude: float) -> float:
    return (latitude - target_latitude) ** 2 + (longitude - target_longitude) ** 2


def _heat_index_c(temperature_c: float, humidity_percent: float) -> float:
    if temperature_c < 27 or humidity_percent < 40:
        return temperature_c
    temperature_f = temperature_c * 9 / 5 + 32
    humidity = humidity_percent
    heat_index_f = (
        -42.379
        + 2.04901523 * temperature_f
        + 10.14333127 * humidity
        - 0.22475541 * temperature_f * humidity
        - 0.00683783 * temperature_f**2
        - 0.05481717 * humidity**2
        + 0.00122874 * temperature_f**2 * humidity
        + 0.00085282 * temperature_f * humidity**2
        - 0.00000199 * temperature_f**2 * humidity**2
    )
    return max(temperature_c, (heat_index_f - 32) * 5 / 9)


def _weather_code(condition: str) -> int:
    normalized = condition.lower()
    if "thunder" in normalized:
        return 95
    if "shower" in normalized:
        return 82 if "heavy" in normalized else 80
    if "rain" in normalized:
        return 65 if "heavy" in normalized else 63 if "moderate" in normalized else 61
    if "haze" in normalized or "mist" in normalized:
        return 45
    if "cloud" in normalized:
        return 2 if "partly" in normalized else 3
    if "fair" in normalized or "sunny" in normalized:
        return 0
    return 3
