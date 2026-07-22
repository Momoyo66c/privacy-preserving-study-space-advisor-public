from __future__ import annotations

from typing import Any


def _comfort_delta(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if low <= value <= high:
        return 0.0
    if value < low:
        return low - value
    return value - high


def extract_environment_features(window: dict[str, Any]) -> dict[str, Any]:
    env = window.get("environment") or {}
    light = env.get("light_lux")
    temp = env.get("temperature_c")
    humidity = env.get("humidity_pct")
    missing_count = sum(1 for value in (light, temp, humidity) if value is None)
    return {
        "light_lux": light,
        "temperature_c": temp,
        "humidity_pct": humidity,
        "environment_missing_count": missing_count,
        "temperature_comfort_delta": _comfort_delta(temp, 20.0, 26.0),
        "humidity_comfort_delta": _comfort_delta(humidity, 35.0, 65.0),
    }
