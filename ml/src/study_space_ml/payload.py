from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .features import WindowFeatures
from .rules import RuleModel, RulePrediction


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def infer_window_seconds(window: dict[str, Any]) -> int:
    try:
        start = parse_datetime(str(window["window_start"]))
        end = parse_datetime(str(window["window_end"]))
        seconds = round((end - start).total_seconds())
    except Exception:
        seconds = 5
    return max(5, min(10, int(seconds)))


def stable_observation_id(window: dict[str, Any], model_version: str) -> str:
    raw = f"{window.get('window_id','missing-window')}:{model_version}"
    return "obs-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def build_edge_observation(
    window: dict[str, Any],
    extracted: WindowFeatures,
    prediction: RulePrediction,
    model: RuleModel,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "observation_id": stable_observation_id(window, model.version),
        "room_id": str(window["room_id"]),
        "device_id": str(window["device_id"]),
        "observed_at": format_utc(parse_datetime(str(window["window_end"]))),
        "window_seconds": infer_window_seconds(window),
        "room_state": prediction.room_state,
        "occupancy_level": prediction.occupancy_level,
        "suitability_score": int(prediction.suitability_score),
        "confidence": round(float(prediction.confidence), 4),
        "features": dict(extracted.contract_summary),
        "sensor_health": dict(extracted.sensor_health),
        "model": {
            "name": model.name,
            "version": model.version,
            "feature_schema_version": model.feature_schema_version,
        },
        "warnings": list(prediction.warnings),
    }
