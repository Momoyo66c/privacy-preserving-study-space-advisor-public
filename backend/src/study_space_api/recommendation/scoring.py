from __future__ import annotations

from dataclasses import dataclass
from math import inf

from ..adapters.recommendation import RecommendationContext
from ..schemas import RecommendationItem, RoomStatus

OCCUPANCY_SCORES = {
    "empty": 100.0,
    "low": 75.0,
    "medium": 40.0,
    "high": 0.0,
}

MODE_SCORES = {
    "quiet": {
        "empty_or_low_activity": 85.0,
        "quiet_study_recommended": 100.0,
        "discussion_allowed": 35.0,
        "not_recommended_noisy_or_crowded": 0.0,
        "unknown": 0.0,
    },
    "discussion": {
        "empty_or_low_activity": 75.0,
        "quiet_study_recommended": 50.0,
        "discussion_allowed": 100.0,
        "not_recommended_noisy_or_crowded": 20.0,
        "unknown": 0.0,
    },
    "any": {
        "empty_or_low_activity": 95.0,
        "quiet_study_recommended": 100.0,
        "discussion_allowed": 90.0,
        "not_recommended_noisy_or_crowded": 20.0,
        "unknown": 0.0,
    },
}

BASE_WEIGHTS = {
    "mode_match": 0.30,
    "quietness": 0.10,
    "current_occupancy": 0.20,
    "future_availability": 0.15,
    "brightness": 0.10,
    "comfort": 0.10,
    "distance": 0.05,
}

DEFAULT_TEMPERATURE_C = 24.0
TARGET_HUMIDITY_PCT = 50.0
TARGET_LIGHT_LUX = 500.0


@dataclass(slots=True)
class ScoredRoom:
    room: RoomStatus
    components: dict[str, float]
    weights: dict[str, float]
    base_score: float
    final_score: int
    confidence_factor: float
    freshness_factor: float
    health_factor: float
    bucket: str
    reasons: list[str]
    forecast_30m: str

    def breakdown(self) -> dict[str, object]:
        return {
            "components": self.components,
            "weights": self.weights,
            "base_score": round(self.base_score, 4),
            "final_score": float(self.final_score),
            "confidence_factor": self.confidence_factor,
            "freshness_factor": self.freshness_factor,
            "health_factor": self.health_factor,
            "bucket": self.bucket,
        }


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def _forecast_component(room: RoomStatus) -> tuple[float | None, str]:
    valid: list[float] = []
    forecast_30m = "unknown"
    for forecast in room.forecasts:
        level = forecast.predicted_occupancy_level
        if forecast.horizon_minutes == 30:
            forecast_30m = level
        score = OCCUPANCY_SCORES.get(level)
        if forecast.horizon_minutes in {15, 30} and score is not None:
            valid.append(score)
    return (sum(valid) / len(valid) if valid else None), forecast_30m


def _brightness_component(room: RoomStatus) -> float | None:
    if room.sensor_health.get("environment") != "ok" or room.features.light_lux is None:
        return None
    return _clamp_score(100.0 - abs(room.features.light_lux - TARGET_LIGHT_LUX) / 5.0)


def _comfort_component(room: RoomStatus, preferred_temperature_c: float | None) -> float | None:
    if room.sensor_health.get("environment") != "ok":
        return None
    values: list[float] = []
    if room.features.temperature_c is not None:
        target = preferred_temperature_c or DEFAULT_TEMPERATURE_C
        values.append(_clamp_score(100.0 - 12.5 * abs(room.features.temperature_c - target)))
    if room.features.humidity_pct is not None:
        values.append(_clamp_score(100.0 - 2.0 * abs(room.features.humidity_pct - TARGET_HUMIDITY_PCT)))
    return sum(values) / len(values) if values else None


def _health_factor(room: RoomStatus) -> float:
    configured = [value for value in room.sensor_health.values() if value != "not_configured"]
    if any(value == "offline" for value in configured):
        return 0.65
    if any(value == "degraded" for value in configured):
        return 0.85
    return 1.0


def _bucket(room: RoomStatus, study_mode: str) -> str:
    mode_mismatch = (
        study_mode == "quiet" and room.room_state == "discussion_allowed"
    ) or (
        study_mode == "discussion"
        and room.room_state == "quiet_study_recommended"
    )
    if (
        room.room_state in {"unknown", "not_recommended_noisy_or_crowded"}
        or room.occupancy_level == "unknown"
        or mode_mismatch
    ):
        return "unknown"
    if room.is_stale:
        return "stale"
    return "fresh"


def _reasons(
    room: RoomStatus,
    study_mode: str,
    components: dict[str, float],
    forecast_30m: str,
    health_factor: float,
) -> list[str]:
    reasons: list[str] = []
    if room.room_state == "unknown":
        reasons.append("Current room conditions are unknown.")
    elif room.room_state == "not_recommended_noisy_or_crowded":
        reasons.append("Current conditions are noisy or crowded.")
    elif study_mode == "quiet" and room.room_state == "quiet_study_recommended":
        reasons.append("Current conditions suit quiet study.")
    elif study_mode == "discussion" and room.room_state == "discussion_allowed":
        reasons.append("Current conditions allow group discussion.")
    elif study_mode == "quiet" and room.room_state == "discussion_allowed":
        reasons.append("Discussion activity may not suit quiet study.")
    elif study_mode == "discussion" and room.room_state == "quiet_study_recommended":
        reasons.append("This is a quiet room, so discussion may disturb others.")
    else:
        reasons.append("The current room state is available for flexible study.")

    if room.is_stale:
        reasons.append("Current data is stale, so use this ranking cautiously.")
    if (room.confidence or 0) < 0.55:
        reasons.append("Model confidence is limited.")
    if health_factor < 1:
        reasons.append("One or more configured sensors are degraded.")

    if room.occupancy_level in {"empty", "low"}:
        reasons.append(f"Current occupancy is {room.occupancy_level}.")
    elif room.occupancy_level in {"medium", "high"}:
        reasons.append(f"Current occupancy is {room.occupancy_level}.")

    if forecast_30m in {"empty", "low"}:
        reasons.append(f"The short-horizon forecast remains {forecast_30m}.")
    elif forecast_30m in {"medium", "high"}:
        reasons.append(f"The short-horizon forecast rises to {forecast_30m}.")

    if components.get("quietness", 0) >= 70:
        reasons.append("The relative sound level is low.")
    if components.get("brightness", 0) >= 70:
        reasons.append("Calibrated light is close to the study target.")
    if components.get("comfort", 0) >= 70:
        reasons.append("Temperature and humidity are near the selected comfort target.")

    deduplicated: list[str] = []
    for reason in reasons:
        if reason not in deduplicated:
            deduplicated.append(reason)
    return deduplicated[:4] or ["No reliable room evidence is currently available."]


def _template_explanation(reasons: list[str]) -> str:
    return " ".join(reasons[:2])


def score_room(context: RecommendationContext, room: RoomStatus) -> ScoredRoom:
    study_mode = context.request.study_mode
    preferences = context.preferences
    components: dict[str, float] = {
        "mode_match": MODE_SCORES[study_mode][room.room_state],
    }
    if room.sensor_health.get("sound") == "ok" and room.features.sound_rms_mean is not None:
        components["quietness"] = _clamp_score(100.0 * (1.0 - room.features.sound_rms_mean))
    occupancy = OCCUPANCY_SCORES.get(room.occupancy_level)
    if occupancy is not None:
        components["current_occupancy"] = occupancy
    forecast_score, forecast_30m = _forecast_component(room)
    if forecast_score is not None:
        components["future_availability"] = forecast_score
    brightness = _brightness_component(room)
    if brightness is not None:
        components["brightness"] = brightness
    comfort = _comfort_component(room, context.preferred_temperature_c)
    if comfort is not None:
        components["comfort"] = comfort

    candidate_weights = {
        "mode_match": BASE_WEIGHTS["mode_match"],
        "quietness": BASE_WEIGHTS["quietness"] * preferences.quiet_priority,
        "current_occupancy": BASE_WEIGHTS["current_occupancy"] * preferences.low_occupancy_priority,
        "future_availability": BASE_WEIGHTS["future_availability"] * preferences.low_occupancy_priority,
        "brightness": BASE_WEIGHTS["brightness"] * preferences.brightness_priority,
        "comfort": BASE_WEIGHTS["comfort"] * preferences.comfort_priority,
        "distance": BASE_WEIGHTS["distance"] * preferences.distance_priority,
    }
    weights = {
        name: weight
        for name, weight in candidate_weights.items()
        if name in components and weight > 0
    }
    denominator = sum(weights.values())
    base_score = (
        sum(components[name] * weight for name, weight in weights.items()) / denominator
        if denominator
        else 0.0
    )
    confidence_factor = room.confidence or 0.0
    freshness_factor = 0.65 if room.is_stale else 1.0
    health_factor = _health_factor(room)
    final_score = round(_clamp_score(base_score * confidence_factor * freshness_factor * health_factor))
    bucket = _bucket(room, study_mode)
    reasons = _reasons(room, study_mode, components, forecast_30m, health_factor)
    return ScoredRoom(
        room=room,
        components=components,
        weights=weights,
        base_score=base_score,
        final_score=final_score,
        confidence_factor=confidence_factor,
        freshness_factor=freshness_factor,
        health_factor=health_factor,
        bucket=bucket,
        reasons=reasons,
        forecast_30m=forecast_30m,
    )


def rank_rooms(context: RecommendationContext) -> list[ScoredRoom]:
    ranked = [score_room(context, room) for room in context.rooms]
    bucket_order = {"fresh": 0, "stale": 1, "unknown": 2}
    ranked.sort(
        key=lambda item: (
            bucket_order[item.bucket],
            -item.final_score,
            -item.confidence_factor,
            item.room.data_age_seconds if item.room.data_age_seconds is not None else inf,
            -(item.room.suitability_score or 0),
            item.room.room_id,
        )
    )
    return ranked


def recommendation_items(ranked: list[ScoredRoom]) -> list[RecommendationItem]:
    return [
        RecommendationItem(
            room_id=item.room.room_id,
            rank=index,
            score=item.final_score,
            current_state=item.room.room_state,
            occupancy_level=item.room.occupancy_level,
            forecast_30m=item.forecast_30m,
            confidence=item.confidence_factor,
            is_stale=item.room.is_stale,
            reasons=item.reasons,
            explanation=_template_explanation(item.reasons),
            explanation_source="template",
        )
        for index, item in enumerate(ranked, start=1)
    ]
