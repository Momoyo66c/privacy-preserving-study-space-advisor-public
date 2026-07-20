from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SENSOR_UNAVAILABLE = {"offline", "not_configured"}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sensor_missing(health: str | None) -> int:
    return 1 if health in SENSOR_UNAVAILABLE else 0


def _environment_health(environment: dict[str, Any]) -> str:
    values = [environment.get("light_lux"), environment.get("temperature_c"), environment.get("humidity_pct")]
    if all(value is None for value in values):
        return "offline"
    if any(value is None for value in values):
        return "degraded"
    return "ok"


@dataclass(frozen=True)
class WindowFeatures:
    values: dict[str, float | int | None]
    contract_summary: dict[str, float | int | None]
    sensor_health: dict[str, str]
    warnings: list[str]


def extract_features(window: dict[str, Any]) -> WindowFeatures:
    """Extract privacy-safe fusion features from one SensorWindow.

    Offline training and online inference should call this same function so
    feature order, missing handling, and summary values stay aligned.
    """
    thermal = window.get("thermal", {})
    radar = window.get("radar", {})
    sound = window.get("sound", {})
    environment = window.get("environment", {})
    quality = window.get("quality", {})

    tracks = radar.get("tracks") or []
    target_counts = [len(track.get("targets") or []) for track in tracks]
    active_target_count = max(target_counts) if target_counts else 0
    mean_target_count = sum(target_counts) / len(target_counts) if target_counts else 0.0

    thermal_health = str(thermal.get("health", "not_configured"))
    radar_health = str(radar.get("health", "not_configured"))
    sound_health = str(sound.get("health", "not_configured"))
    environment_health = _environment_health(environment)

    values: dict[str, float | int | None] = {
        "thermal_frame_count": _as_int(thermal.get("frame_count")),
        "radar_sample_count": _as_int(radar.get("sample_count")),
        "radar_active_target_count": active_target_count,
        "radar_mean_target_count": mean_target_count,
        "sound_rms_mean": _as_float(sound.get("rms_mean")),
        "sound_rms_std": _as_float(sound.get("rms_std")),
        "sound_peak": _as_float(sound.get("peak")),
        "light_lux": _as_float(environment.get("light_lux")),
        "temperature_c": _as_float(environment.get("temperature_c")),
        "humidity_pct": _as_float(environment.get("humidity_pct")),
        "completeness": _as_float(quality.get("completeness")),
        "thermal_missing": _sensor_missing(thermal_health),
        "radar_missing": _sensor_missing(radar_health),
        "sound_missing": _sensor_missing(sound_health),
        "environment_missing": 1 if environment_health in SENSOR_UNAVAILABLE else 0,
    }

    # Thermal raw frames are intentionally not loaded in online inference.
    # A future trained model may parse local:// NPZ during offline feature generation.
    thermal_hot_region_count = None

    contract_summary: dict[str, float | int | None] = {
        "thermal_hot_region_count": thermal_hot_region_count,
        "radar_active_target_count": active_target_count,
        "sound_rms_mean": values["sound_rms_mean"],
        "light_lux": values["light_lux"],
        "temperature_c": values["temperature_c"],
        "humidity_pct": values["humidity_pct"],
    }

    warnings = [str(item) for item in quality.get("warnings", [])]
    return WindowFeatures(
        values=values,
        contract_summary=contract_summary,
        sensor_health={
            "thermal": thermal_health,
            "radar": radar_health,
            "sound": sound_health,
            "environment": environment_health,
        },
        warnings=warnings,
    )
