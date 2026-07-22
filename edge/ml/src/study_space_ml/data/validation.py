from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from study_space_ml.constants import SCHEMA_VERSION, SENSOR_HEALTH_VALUES


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def extend(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def parse_dt(value: Any, field_name: str, result: ValidationResult) -> datetime | None:
    if not isinstance(value, str) or not value:
        result.errors.append(f"{field_name} must be a date-time string")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        result.errors.append(f"{field_name} is not parseable: {value!r}")
        return None
    if parsed.tzinfo is None:
        result.errors.append(f"{field_name} must include timezone")
        return None
    return parsed.astimezone(timezone.utc)


def _require_object(value: Any, field_name: str, result: ValidationResult) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        result.errors.append(f"{field_name} must be an object")
        return None
    return value


def _validate_health(value: Any, field_name: str, result: ValidationResult) -> None:
    if value not in SENSOR_HEALTH_VALUES:
        result.errors.append(f"{field_name} has invalid health {value!r}")


def _nullable_number(
    value: Any,
    field_name: str,
    result: ValidationResult,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        result.errors.append(f"{field_name} must be a number or null")
        return
    if minimum is not None and value < minimum:
        result.errors.append(f"{field_name} below minimum {minimum}")
    if maximum is not None and value > maximum:
        result.errors.append(f"{field_name} above maximum {maximum}")


def _validate_integer(value: Any, field_name: str, result: ValidationResult, *, minimum: int | None = None) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        result.errors.append(f"{field_name} must be an integer")
        return
    if minimum is not None and value < minimum:
        result.errors.append(f"{field_name} below minimum {minimum}")


def _validate_radar_target(target: Any, field_name: str, result: ValidationResult) -> None:
    if not isinstance(target, dict):
        result.errors.append(f"{field_name} must be an object")
        return
    required = ["x_mm", "y_mm", "speed_cm_s", "distance_resolution_mm", "valid", "target_id"]
    for key in required:
        if key not in target:
            result.errors.append(f"{field_name} missing required field: {key}")
    _validate_integer(target.get("x_mm"), f"{field_name}.x_mm", result)
    _validate_integer(target.get("y_mm"), f"{field_name}.y_mm", result)
    _validate_integer(target.get("speed_cm_s"), f"{field_name}.speed_cm_s", result)
    _validate_integer(target.get("distance_resolution_mm"), f"{field_name}.distance_resolution_mm", result, minimum=0)
    if target.get("valid") is not True:
        result.errors.append(f"{field_name}.valid must be true")
    target_id = target.get("target_id")
    if not isinstance(target_id, str) or not target_id.startswith("target-"):
        result.errors.append(f"{field_name}.target_id must be a target-* string")


def validate_sensor_window(window: dict[str, Any]) -> ValidationResult:
    """Validate the Module 1 SensorWindow interface expected by Module 2.

    This is a lightweight stdlib validator aligned with
    ``shared/contracts/sensor_window.schema.json``. It deliberately treats some
    semantic issues as warnings so the inference path can still degrade safely
    instead of dropping a partially useful window.
    """

    result = ValidationResult()
    required = [
        "schema_version",
        "window_id",
        "room_id",
        "device_id",
        "window_start",
        "window_end",
        "thermal",
        "radar",
        "sound",
        "environment",
        "quality",
    ]
    for key in required:
        if key not in window:
            result.errors.append(f"missing required field: {key}")
    if result.errors:
        return result
    if window.get("schema_version") != SCHEMA_VERSION:
        result.errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("window_id", "room_id", "device_id"):
        if not isinstance(window.get(key), str) or not window[key]:
            result.errors.append(f"{key} must be a non-empty string")
    start = parse_dt(window.get("window_start"), "window_start", result)
    end = parse_dt(window.get("window_end"), "window_end", result)
    if start and end:
        seconds = (end - start).total_seconds()
        if seconds <= 0:
            result.errors.append("window_end must be after window_start")
        elif seconds < 5 or seconds > 10:
            result.warnings.append(f"WINDOW_SECONDS_OUTSIDE_CONTRACT:{seconds:g}")

    thermal = _require_object(window.get("thermal"), "thermal", result)
    if thermal is not None:
        _validate_health(thermal.get("health"), "thermal.health", result)
        _validate_integer(thermal.get("frame_count"), "thermal.frame_count", result, minimum=0)
        frames_ref = thermal.get("frames_ref")
        if frames_ref is not None and (not isinstance(frames_ref, str) or not frames_ref.startswith("local://")):
            result.errors.append("thermal.frames_ref must start with local:// when present")
        if thermal.get("health") in {"offline", "not_configured"} and thermal.get("frame_count"):
            result.warnings.append("THERMAL_HAS_FRAMES_WHILE_UNAVAILABLE")

    radar = _require_object(window.get("radar"), "radar", result)
    if radar is not None:
        _validate_health(radar.get("health"), "radar.health", result)
        _validate_integer(radar.get("sample_count"), "radar.sample_count", result, minimum=0)
        tracks = radar.get("tracks")
        if not isinstance(tracks, list):
            result.errors.append("radar.tracks must be an array")
        else:
            for i, track in enumerate(tracks):
                if not isinstance(track, dict):
                    result.errors.append(f"radar.tracks[{i}] must be an object")
                    continue
                _validate_integer(track.get("sample_offset_ms"), f"radar.tracks[{i}].sample_offset_ms", result, minimum=0)
                targets = track.get("targets")
                if not isinstance(targets, list):
                    result.errors.append(f"radar.tracks[{i}].targets must be an array")
                    continue
                if len(targets) > 3:
                    result.errors.append(f"radar.tracks[{i}].targets has more than 3 targets")
                for j, target in enumerate(targets):
                    _validate_radar_target(target, f"radar.tracks[{i}].targets[{j}]", result)
        if radar.get("health") in {"offline", "not_configured"} and radar.get("sample_count"):
            result.warnings.append("RADAR_HAS_SAMPLES_WHILE_UNAVAILABLE")

    sound = _require_object(window.get("sound"), "sound", result)
    if sound is not None:
        _validate_health(sound.get("health"), "sound.health", result)
        _nullable_number(sound.get("rms_mean"), "sound.rms_mean", result, minimum=0, maximum=1)
        _nullable_number(sound.get("rms_std"), "sound.rms_std", result, minimum=0, maximum=1)
        _nullable_number(sound.get("peak"), "sound.peak", result, minimum=0, maximum=1)
        if sound.get("health") in {"offline", "not_configured"} and sound.get("rms_mean") is not None:
            result.warnings.append("SOUND_HAS_VALUES_WHILE_UNAVAILABLE")

    env = _require_object(window.get("environment"), "environment", result)
    if env is not None:
        for key in ("light_lux", "temperature_c", "humidity_pct"):
            if key not in env:
                result.errors.append(f"environment missing required field: {key}")
        _nullable_number(env.get("light_lux"), "environment.light_lux", result, minimum=0)
        _nullable_number(env.get("temperature_c"), "environment.temperature_c", result, minimum=-50, maximum=100)
        _nullable_number(env.get("humidity_pct"), "environment.humidity_pct", result, minimum=0, maximum=100)

    quality = _require_object(window.get("quality"), "quality", result)
    if quality is not None:
        completeness = quality.get("completeness")
        if not isinstance(completeness, (int, float)) or isinstance(completeness, bool) or not (0 <= completeness <= 1):
            result.errors.append("quality.completeness must be between 0 and 1")
        elif completeness < 0.70:
            result.warnings.append("LOW_WINDOW_COMPLETENESS")
        warnings = quality.get("warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            result.errors.append("quality.warnings must be an array of strings")
        elif len(set(warnings)) != len(warnings):
            result.warnings.append("DUPLICATE_QUALITY_WARNINGS")
    return result


def validate_window_collection(windows: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "valid": True,
        "window_count": len(windows),
        "errors": [],
        "warnings": [],
        "duplicate_window_ids": [],
    }
    seen: set[str] = set()
    for index, window in enumerate(windows):
        result = validate_sensor_window(window)
        window_id = str(window.get("window_id", f"index-{index}"))
        if window_id in seen:
            report["duplicate_window_ids"].append(window_id)
        seen.add(window_id)
        for error in result.errors:
            report["errors"].append({"index": index, "window_id": window_id, "message": error})
        for warning in result.warnings:
            report["warnings"].append({"index": index, "window_id": window_id, "message": warning})
    if report["errors"] or report["duplicate_window_ids"]:
        report["valid"] = False
    return report
