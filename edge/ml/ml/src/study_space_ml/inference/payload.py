from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from study_space_ml.constants import SCHEMA_VERSION, SENSOR_HEALTH_VALUES
from study_space_ml.data.validation import ValidationResult, parse_dt
from study_space_ml.inference.model import ModelOutput, RuleModel

_SAFE_ID = re.compile(r"[^A-Za-z0-9._:-]")


def _stable_id(window_id: str, model_version: str) -> str:
    """Build a deterministic id without ever truncating away the hash suffix."""

    suffix = hashlib.sha256(f"{window_id}:{model_version}".encode("utf-8")).hexdigest()[:10]
    base = _SAFE_ID.sub("-", window_id).strip(".-_:") or "observation"
    max_base_len = 128 - 1 - len(suffix)
    base = base[:max_base_len].rstrip(".-_:") or "observation"
    value = f"{base}-{suffix}"
    if not value[0].isalnum():
        value = f"o{value}"
    return value[:128]


def _window_seconds(window: dict[str, Any], warnings: list[str]) -> int:
    result = ValidationResult()
    start = parse_dt(window.get("window_start"), "window_start", result)
    end = parse_dt(window.get("window_end"), "window_end", result)
    if start and end:
        seconds = int(round((end - start).total_seconds()))
        if 5 <= seconds <= 10:
            return seconds
    warnings.append("WINDOW_SECONDS_DEFAULTED")
    return 5


def _environment_health(window: dict[str, Any]) -> str:
    env = window.get("environment") or {}
    values = [env.get("light_lux"), env.get("temperature_c"), env.get("humidity_pct")]
    if all(value is None for value in values):
        return "offline"
    if any(value is None for value in values):
        return "degraded"
    return "ok"


def _health(value: Any) -> str:
    return str(value) if value in SENSOR_HEALTH_VALUES else "not_configured"


def sensor_health_summary(window: dict[str, Any]) -> dict[str, str]:
    """Map Module 1 sensor health into the backend EdgeObservation contract.

    Module 1 exposes separate light and climate drivers but the SensorWindow
    contract only contains aggregate environment values. Therefore environment
    health is derived from null vs non-null environment fields.
    """

    return {
        "thermal": _health((window.get("thermal") or {}).get("health")),
        "radar": _health((window.get("radar") or {}).get("health")),
        "sound": _health((window.get("sound") or {}).get("health")),
        "environment": _environment_health(window),
    }


def _bounded_feature_summary(summary: dict[str, Any]) -> dict[str, Any]:
    # Keep the output strictly inside shared/contracts/edge_observation.schema.json.
    sound = summary.get("sound_rms_mean")
    if isinstance(sound, (int, float)):
        sound = max(0.0, min(1.0, float(sound)))
    return {
        "thermal_hot_region_count": summary.get("thermal_hot_region_count"),
        "radar_active_target_count": summary.get("radar_active_target_count"),
        "sound_rms_mean": sound,
        "light_lux": summary.get("light_lux"),
        "temperature_c": summary.get("temperature_c"),
        "humidity_pct": summary.get("humidity_pct"),
    }


def build_edge_observation(
    window: dict[str, Any],
    *,
    model: RuleModel,
    model_output: ModelOutput,
    feature_summary: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    merged_warnings: list[str] = []
    for item in [*(warnings or []), *model_output.warnings]:
        if item and item not in merged_warnings:
            merged_warnings.append(str(item)[:256])
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_id": _stable_id(str(window["window_id"]), model.version),
        "room_id": window["room_id"],
        "device_id": window["device_id"],
        "observed_at": window["window_end"],
        "window_seconds": _window_seconds(window, merged_warnings),
        "room_state": model_output.room_state,
        "occupancy_level": model_output.occupancy_level,
        "suitability_score": int(max(0, min(100, model_output.suitability_score))),
        "confidence": float(max(0.0, min(1.0, model_output.confidence))),
        "features": _bounded_feature_summary(feature_summary),
        "sensor_health": sensor_health_summary(window),
        "model": {
            "name": model.name,
            "version": model.version,
            "feature_schema_version": model.feature_schema_version,
        },
        "warnings": merged_warnings[:32],
    }


def validate_edge_observation(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "schema_version",
        "observation_id",
        "room_id",
        "device_id",
        "observed_at",
        "window_seconds",
        "room_state",
        "occupancy_level",
        "suitability_score",
        "confidence",
        "features",
        "sensor_health",
        "model",
        "warnings",
    ]
    for key in required:
        if key not in payload:
            errors.append(f"missing required field: {key}")
    if errors:
        return errors
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 1.0")
    observation_id = payload.get("observation_id")
    if not isinstance(observation_id, str) or not observation_id or len(observation_id) > 128 or not observation_id[0].isalnum():
        errors.append("observation_id must match backend id contract")
    if not isinstance(payload.get("window_seconds"), int) or not 5 <= payload["window_seconds"] <= 10:
        errors.append("window_seconds must be 5..10")
    if payload.get("room_state") not in {
        "empty_or_low_activity",
        "quiet_study_recommended",
        "discussion_allowed",
        "not_recommended_noisy_or_crowded",
        "unknown",
    }:
        errors.append("room_state is invalid")
    if payload.get("occupancy_level") not in {"empty", "low", "medium", "high", "unknown"}:
        errors.append("occupancy_level is invalid")
    score = payload.get("suitability_score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        errors.append("suitability_score must be 0..100")
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("confidence must be 0..1")
    try:
        parsed = datetime.fromisoformat(str(payload.get("observed_at")).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            errors.append("observed_at must include timezone")
        else:
            parsed.astimezone(timezone.utc)
    except Exception:
        errors.append("observed_at is not parseable")
    features = payload.get("features")
    if not isinstance(features, dict):
        errors.append("features must be an object")
    elif isinstance(features.get("sound_rms_mean"), (int, float)) and not 0 <= features["sound_rms_mean"] <= 1:
        errors.append("features.sound_rms_mean must be 0..1 or null")
    sensor_health = payload.get("sensor_health")
    if not isinstance(sensor_health, dict):
        errors.append("sensor_health must be an object")
    else:
        for name in ("thermal", "radar", "sound", "environment"):
            if sensor_health.get(name) not in SENSOR_HEALTH_VALUES:
                errors.append(f"sensor_health.{name} is invalid")
    if not isinstance(payload.get("warnings"), list):
        errors.append("warnings must be an array")
    return errors
