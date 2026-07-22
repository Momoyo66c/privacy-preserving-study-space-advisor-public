from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from study_space_ml.constants import FEATURE_SCHEMA_VERSION, MODEL_NAME, MODEL_VERSION
from study_space_ml.paths import default_artifact_dir


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class ModelOutput:
    room_state: str
    raw_room_state: str
    occupancy_level: str
    suitability_score: int
    confidence: float
    warnings: list[str]


class RuleModel:
    """Deterministic baseline classifier used until enough labelled data exists."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = str(config.get("model_name") or MODEL_NAME)
        self.version = str(config.get("model_version") or MODEL_VERSION)
        self.feature_schema_version = str(config.get("feature_schema_version") or FEATURE_SCHEMA_VERSION)
        self.confidence_threshold = float(config.get("confidence_threshold", 0.55))
        self.thresholds = dict(config.get("thresholds") or {})

    @classmethod
    def load(cls, artifact_dir: str | Path | None = None) -> "RuleModel":
        directory = Path(artifact_dir).expanduser().resolve() if artifact_dir else default_artifact_dir()
        with (directory / "model.json").open("r", encoding="utf-8") as handle:
            config = json.load(handle)
        return cls(config)

    def _threshold(self, name: str, default: float) -> float:
        try:
            return float(self.thresholds.get(name, default))
        except (TypeError, ValueError):
            return default

    def predict(self, features: dict[str, Any], sensor_health: dict[str, str]) -> ModelOutput:
        warnings: list[str] = []
        if self.feature_schema_version != FEATURE_SCHEMA_VERSION:
            return ModelOutput(
                room_state="unknown",
                raw_room_state="unknown",
                occupancy_level="unknown",
                suitability_score=30,
                confidence=0.0,
                warnings=["FEATURE_SCHEMA_VERSION_MISMATCH"],
            )
        thermal_bad = sensor_health.get("thermal") in {"offline", "not_configured"}
        radar_bad = sensor_health.get("radar") in {"offline", "not_configured"}
        if thermal_bad and radar_bad:
            return ModelOutput(
                room_state="unknown",
                raw_room_state="unknown",
                occupancy_level="unknown",
                suitability_score=30,
                confidence=0.0,
                warnings=["MODEL_INPUT_INSUFFICIENT:THERMAL_AND_RADAR_UNAVAILABLE"],
            )
        completeness = float(features.get("quality_completeness") or 0.0)
        if completeness < self._threshold("low_completeness", 0.70):
            warnings.append("LOW_WINDOW_COMPLETENESS")

        sound = features.get("sound_rms_mean")
        sound_value = float(sound) if sound is not None else 0.0
        sound_missing = bool(features.get("sound_missing"))
        active_targets = int(features.get("radar_max_target_count") or 0)
        peak = features.get("sound_peak")
        peak_value = float(peak) if peak is not None else 0.0

        empty_rms_max = self._threshold("empty_rms_max", 0.08)
        quiet_rms_max = self._threshold("quiet_rms_max", 0.22)
        discussion_rms_max = self._threshold("discussion_rms_max", 0.55)
        crowded_rms_min = self._threshold("crowded_rms_min", 0.55)
        discussion_target_min = int(self._threshold("discussion_target_min", 2))
        crowded_target_min = int(self._threshold("crowded_target_min", 3))

        if sound_missing and radar_bad:
            raw_state = "unknown"
            confidence = 0.0
            warnings.append("MODEL_INPUT_INSUFFICIENT:SOUND_AND_RADAR_UNAVAILABLE")
        elif sound_value >= crowded_rms_min or peak_value >= 0.88 or (active_targets >= crowded_target_min and sound_value >= 0.45):
            raw_state = "not_recommended_noisy_or_crowded"
            confidence = 0.70 + min(0.20, max(sound_value - crowded_rms_min, 0.0))
        elif sound_value >= quiet_rms_max or active_targets >= discussion_target_min:
            raw_state = "discussion_allowed"
            margin = min(abs(sound_value - quiet_rms_max), abs(discussion_rms_max - sound_value))
            confidence = 0.62 + min(0.18, margin)
        elif active_targets == 0 and sound_value <= empty_rms_max:
            raw_state = "empty_or_low_activity"
            confidence = 0.73 + min(0.15, empty_rms_max - sound_value)
        else:
            raw_state = "quiet_study_recommended"
            margin = max(0.0, quiet_rms_max - sound_value)
            confidence = 0.68 + min(0.18, margin)

        if sensor_health.get("thermal") == "degraded" or sensor_health.get("radar") == "degraded":
            warnings.append("DEGRADED_CORE_SENSOR")
            confidence -= 0.08
        if sound_missing:
            warnings.append("SOUND_MISSING")
            confidence -= 0.08
        confidence *= _clamp(completeness if completeness else 1.0, 0.65, 1.0)
        confidence = _clamp(confidence, 0.0, 0.95)

        if raw_state == "unknown" or confidence < self.confidence_threshold:
            if raw_state != "unknown":
                warnings.append("LOW_MODEL_CONFIDENCE")
            room_state = "unknown"
            occupancy = "unknown"
            score = 30
        else:
            room_state = raw_state
            occupancy = occupancy_for_state(room_state)
            score = suitability_score(room_state, features)
        return ModelOutput(
            room_state=room_state,
            raw_room_state=raw_state,
            occupancy_level=occupancy,
            suitability_score=score,
            confidence=round(confidence, 3),
            warnings=warnings,
        )


def occupancy_for_state(room_state: str) -> str:
    return {
        "empty_or_low_activity": "empty",
        "quiet_study_recommended": "low",
        "discussion_allowed": "medium",
        "not_recommended_noisy_or_crowded": "high",
        "unknown": "unknown",
    }.get(room_state, "unknown")


def suitability_score(room_state: str, features: dict[str, Any]) -> int:
    base = {
        "empty_or_low_activity": 72,
        "quiet_study_recommended": 88,
        "discussion_allowed": 58,
        "not_recommended_noisy_or_crowded": 25,
        "unknown": 30,
    }.get(room_state, 30)
    score = float(base)
    light = features.get("light_lux")
    temp_delta = features.get("temperature_comfort_delta")
    humidity_delta = features.get("humidity_comfort_delta")
    if isinstance(light, (int, float)):
        if 250 <= light <= 700:
            score += 4
        elif light < 120:
            score -= 8
        elif light > 1000:
            score -= 5
    if isinstance(temp_delta, (int, float)):
        score += 3 if temp_delta == 0 else -min(8, temp_delta * 1.5)
    if isinstance(humidity_delta, (int, float)):
        score += 2 if humidity_delta == 0 else -min(5, humidity_delta * 0.5)
    return int(_clamp(round(score), 0, 100))
