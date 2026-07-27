from __future__ import annotations

import asyncio

from study_space_api.services.weather import WeatherService


def _reading(unit: str, west_coast_value: float, distant_value: float) -> dict:
    return {
        "code": 0,
        "data": {
            "readingUnit": unit,
            "stations": [
                {"id": "S116", "name": "West Coast Highway", "location": {"latitude": 1.2824, "longitude": 103.7545}},
                {"id": "S109", "name": "Ang Mo Kio Avenue 5", "location": {"latitude": 1.3793, "longitude": 103.85}},
            ],
            "readings": [
                {
                    "timestamp": "2026-07-27T16:00:00+08:00",
                    "data": [
                        {"stationId": "S116", "value": west_coast_value},
                        {"stationId": "S109", "value": distant_value},
                    ],
                }
            ],
        },
    }


def test_weather_service_selects_nearest_station_and_uses_stale_cache() -> None:
    payloads = {
        "air-temperature": _reading("deg C", 31.2, 29.0),
        "relative-humidity": _reading("percentage", 64, 80),
        "wind-speed": _reading("knots", 5, 2),
        "two-hr-forecast": {
            "code": 0,
            "data": {
                "items": [
                    {
                        "forecasts": [
                            {"area": "Clementi", "forecast": "Thundery Showers"},
                            {"area": "Ang Mo Kio", "forecast": "Cloudy"},
                        ]
                    }
                ]
            },
        },
    }
    upstream_available = True

    def fetcher(url: str, _timeout: float) -> dict:
        if not upstream_available:
            raise OSError("offline")
        return payloads[url.rsplit("/", 1)[-1]]

    async def scenario() -> None:
        nonlocal upstream_available
        service = WeatherService(cache_ttl_seconds=0, stale_ttl_seconds=60, fetcher=fetcher)
        fresh = await service.get_current()
        assert fresh.station_name == "West Coast Highway"
        assert fresh.temperature_c == 31.2
        assert fresh.wind_kph == 9.3
        assert fresh.weather_code == 95

        upstream_available = False
        cached = await service.get_current()
        assert cached.source == "nea_cache"
        assert cached.is_cached is True
        assert cached.temperature_c == fresh.temperature_c

    asyncio.run(scenario())
