from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .features import SENSOR_UNAVAILABLE, WindowFeatures


ROOM_STATES = {
    "empty_or_low_activity",
    "quiet_study_recommended",
    "discussion_allowed",
    "not_recommended_noisy_or_crowded",
    "unknown",
}


@dataclass(frozen=True)
class RulePrediction:
    room_state: str
    occupancy_level: str
    suitability_score: int
    confidence: float
    warnings: list[str]


def _clamp_int(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _clamp_float(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _occupancy_from_targets(target_count: int | None) -> str:
    if target_count is None:
        return "unknown"
    if target_count <= 0:
        return "empty"
    if target_count <= 1:
        return "low"
    if target_count <= 3:
        return "medium"
    return "high"


def _environment_score_adjustment(features: dict[str, Any]) -> int:
    adjustment = 0
    light = features.get("light_lux")
    temp = features.get("temperature_c")
    humidity = features.get("humidity_pct")
    if light is not None:
        adjustment += 4 if 250 <= light <= 800 else -4
    if temp is not None:
        adjustment += 3 if 20 <= temp <= 26 else -3
    if humidity is not None:
        adjustment += 2 if 35 <= humidity <= 65 else -2
    return adjustment


class RuleModel:
    """Transparent rule baseline for pre-real-data integration."""

    def __init__(self, model_config: dict[str, Any]) -> None:
        self.config = model_config
        self.name = str(model_config.get("name", "room-state-rule-baseline"))
        self.version = str(model_config.get("version", "0.1.0"))
        self.feature_schema_version = str(model_config.get("feature_schema_version", "1.0"))
        self.low_confidence_threshold = float(model_config.get("low_confidence_threshold", 0.55))
        self.thresholds = dict(model_config.get("thresholds", {}))

    @classmethod
    def load(cls, path: str | Path) -> "RuleModel":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def predict(self, extracted: WindowFeatures) -> RulePrediction:
        values = extracted.values
        warnings = list(extracted.warnings)
        health = extracted.sensor_health

        thermal_unavailable = health["thermal"] in SENSOR_UNAVAILABLE
        radar_unavailable = health["radar"] in SENSOR_UNAVAILABLE
        if thermal_unavailable and radar_unavailable:
            warnings.append("MODEL_INPUT_INSUFFICIENT:thermal_and_radar_unavailable")
            return RulePrediction("unknown", "unknown", 20, 0.0, sorted(set(warnings)))

        completeness = values.get("completeness")
        min_completeness = float(self.thresholds.get("minimum_completeness", 0.50))
        if completeness is not None and completeness < min_completeness:
            warnings.append("MODEL_INPUT_INSUFFICIENT:low_completeness")
            return RulePrediction("unknown", "unknown", 25, 0.0, sorted(set(warnings)))

        target_count = values.get("radar_active_target_count")
        target_count_int = int(target_count) if target_count is not None else None
        sound = values.get("sound_rms_mean")
        sound_value = float(sound) if sound is not None else None

        if radar_unavailable:
            target_count_int = None
            warnings.append("MODEL_INPUT_DEGRADED:radar_unavailable")
        if health["sound"] in SENSOR_UNAVAILABLE or sound_value is None:
            sound_value = 1.0
            warnings.append("MODEL_INPUT_DEGRADED:sound_unavailable")
        if health["environment"] != "ok":
            warnings.append(f"MODEL_INPUT_DEGRADED:environment_{health['environment']}")
        if thermal_unavailable:
            warnings.append("MODEL_INPUT_DEGRADED:thermal_unavailable")

        if target_count_int is None:
            # Without radar, sound can only give a conservative noisy/quiet hint.
            if sound_value <= 0.18:
                room_state = "quiet_study_recommended"
                occupancy_level = "unknown"
                base_score = 70
                confidence = 0.56
            elif sound_value <= 0.45:
                room_state = "discussion_allowed"
                occupancy_level = "unknown"
                base_score = 50
                confidence = 0.52
            else:
                room_state = "not_recommended_noisy_or_crowded"
                occupancy_level = "unknown"
                base_score = 25
                confidence = 0.58
        elif target_count_int <= int(self.thresholds.get("empty_max_radar_targets", 0)) and sound_value <= float(self.thresholds.get("empty_max_sound_rms_mean", 0.08)):
            room_state = "empty_or_low_activity"
            occupancy_level = "empty"
            base_score = 72
            confidence = 0.84
        elif target_count_int <= int(self.thresholds.get("quiet_max_radar_targets", 1)) and sound_value <= float(self.thresholds.get("quiet_max_sound_rms_mean", 0.22)):
            room_state = "quiet_study_recommended"
            occupancy_level = "low"
            base_score = 88
            confidence = 0.84
        elif target_count_int <= int(self.thresholds.get("discussion_max_radar_targets", 3)) and sound_value <= float(self.thresholds.get("discussion_max_sound_rms_mean", 0.55)):
            room_state = "discussion_allowed"
            occupancy_level = _occupancy_from_targets(target_count_int)
            base_score = 62
            confidence = 0.76
        else:
            room_state = "not_recommended_noisy_or_crowded"
            occupancy_level = _occupancy_from_targets(target_count_int)
            base_score = 28
            confidence = 0.80

        # Penalize degraded inputs. Keep the rule model deterministic and easy to explain.
        if completeness is not None:
            confidence *= max(0.50, min(1.0, float(completeness)))
        for sensor_name, sensor_health in health.items():
            if sensor_health == "degraded":
                confidence -= 0.08
            elif sensor_health in SENSOR_UNAVAILABLE:
                confidence -= 0.16

        score = base_score + _environment_score_adjustment(values)
        confidence = _clamp_float(confidence)
        if confidence < self.low_confidence_threshold:
            warnings.append("LOW_MODEL_CONFIDENCE")
            return RulePrediction("unknown", "unknown", min(_clamp_int(score), 45), confidence, sorted(set(warnings)))

        if room_state not in ROOM_STATES:
            raise ValueError(f"Invalid room_state produced by rules: {room_state}")
        return RulePrediction(room_state, occupancy_level, _clamp_int(score), confidence, sorted(set(warnings)))
