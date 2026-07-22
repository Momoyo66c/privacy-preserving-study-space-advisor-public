from __future__ import annotations

import math
from datetime import datetime
from statistics import mean
from typing import Any

from .. import models
from ..schemas import (
    LearnedPreferenceValues,
    MePreferenceResponse,
    PreferenceEvidenceCounts,
    PreferenceSnapshot,
    RecommendationPreferences,
)

LEARNING_DIMENSIONS = {
    "quiet_priority": "quietness",
    "brightness_priority": "brightness",
    "comfort_priority": "comfort",
}

SCORE_COMPONENTS = {
    "mode_match",
    "quietness",
    "current_occupancy",
    "future_availability",
    "brightness",
    "comfort",
    "distance",
}
QUALITY_FACTORS = {"confidence_factor", "freshness_factor", "health_factor"}


def _finite_number(value: object, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        return None
    return numeric


def sanitize_score_breakdown(
    raw: object,
    allowed_room_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Retain only bounded, privacy-safe Module 4 adapter output."""
    if not isinstance(raw, dict):
        return {}
    sanitized: dict[str, dict[str, Any]] = {}
    for room_id in allowed_room_ids:
        room = raw.get(room_id)
        if not isinstance(room, dict):
            continue
        safe: dict[str, Any] = {}
        components = room.get("components")
        if isinstance(components, dict):
            safe_components = {
                name: numeric
                for name in SCORE_COMPONENTS
                if (numeric := _finite_number(components.get(name), 0, 100)) is not None
            }
            if safe_components:
                safe["components"] = safe_components
        weights = room.get("weights")
        if isinstance(weights, dict):
            safe_weights = {
                name: numeric
                for name in SCORE_COMPONENTS
                if (numeric := _finite_number(weights.get(name), 0, 1)) is not None
            }
            if safe_weights:
                safe["weights"] = safe_weights
        for name in ("base_score", "final_score"):
            numeric = _finite_number(room.get(name), 0, 100)
            if numeric is not None:
                safe[name] = numeric
        for name in QUALITY_FACTORS:
            numeric = _finite_number(room.get(name), 0, 1)
            if numeric is not None:
                safe[name] = numeric
        bucket = room.get("bucket")
        if isinstance(bucket, int) and not isinstance(bucket, bool) and 0 <= bucket <= 2:
            safe["bucket"] = bucket
        elif bucket in {"fresh", "stale", "unknown"}:
            safe["bucket"] = bucket
        if safe:
            sanitized[room_id] = safe
    return sanitized


def manual_snapshot(profile: models.PreferenceProfile) -> PreferenceSnapshot:
    return PreferenceSnapshot(
        study_mode=profile.study_mode,
        quiet_priority=profile.quiet_priority,
        low_occupancy_priority=profile.low_occupancy_priority,
        brightness_priority=profile.brightness_priority,
        comfort_priority=profile.comfort_priority,
        distance_priority=profile.distance_priority,
        preferred_temperature_c=profile.preferred_temperature_c,
    )


def effective_value(manual: float, learned: float | None, evidence_count: int, enabled: bool) -> float:
    if not enabled or learned is None or evidence_count <= 0:
        return manual
    influence = min(evidence_count / 20, 1.0) * 0.40
    return manual * (1 - influence) + learned * influence


def effective_snapshot(
    profile: models.PreferenceProfile,
    learned: models.LearnedPreferenceProfile,
) -> PreferenceSnapshot:
    return PreferenceSnapshot(
        study_mode=profile.study_mode,
        quiet_priority=effective_value(
            profile.quiet_priority, learned.quiet_priority, learned.quiet_evidence_count, learned.learning_enabled
        ),
        low_occupancy_priority=effective_value(
            profile.low_occupancy_priority,
            learned.low_occupancy_priority,
            learned.low_occupancy_evidence_count,
            learned.learning_enabled,
        ),
        brightness_priority=effective_value(
            profile.brightness_priority,
            learned.brightness_priority,
            learned.brightness_evidence_count,
            learned.learning_enabled,
        ),
        comfort_priority=effective_value(
            profile.comfort_priority,
            learned.comfort_priority,
            learned.comfort_evidence_count,
            learned.learning_enabled,
        ),
        distance_priority=profile.distance_priority,
        preferred_temperature_c=profile.preferred_temperature_c,
    )


def as_recommendation_preferences(snapshot: PreferenceSnapshot) -> RecommendationPreferences:
    return RecommendationPreferences(
        quiet_priority=snapshot.quiet_priority,
        low_occupancy_priority=snapshot.low_occupancy_priority,
        brightness_priority=snapshot.brightness_priority,
        comfort_priority=snapshot.comfort_priority,
        distance_priority=snapshot.distance_priority,
    )


def preference_response(
    profile: models.PreferenceProfile,
    learned: models.LearnedPreferenceProfile,
) -> MePreferenceResponse:
    return MePreferenceResponse(
        manual=manual_snapshot(profile),
        learned=LearnedPreferenceValues(
            quiet_priority=learned.quiet_priority,
            low_occupancy_priority=learned.low_occupancy_priority,
            brightness_priority=learned.brightness_priority,
            comfort_priority=learned.comfort_priority,
            distance_priority=None,
        ),
        effective=effective_snapshot(profile, learned),
        evidence_counts=PreferenceEvidenceCounts(
            quiet_priority=learned.quiet_evidence_count,
            low_occupancy_priority=learned.low_occupancy_evidence_count,
            brightness_priority=learned.brightness_evidence_count,
            comfort_priority=learned.comfort_evidence_count,
            distance_priority=0,
        ),
        learning_enabled=learned.learning_enabled,
        updated_at=learned.updated_at,
    )


def reset_learned(learned: models.LearnedPreferenceProfile, now: datetime) -> None:
    for field in ("quiet_priority", "low_occupancy_priority", "brightness_priority", "comfort_priority"):
        setattr(learned, field, None)
    for field in (
        "quiet_evidence_count",
        "low_occupancy_evidence_count",
        "brightness_evidence_count",
        "comfort_evidence_count",
    ):
        setattr(learned, field, 0)
    learned.updated_at = now


def selection_evidence(selected_room_id: str, breakdowns: dict[str, dict]) -> dict[str, float]:
    selected = breakdowns.get(selected_room_id)
    if selected is None:
        return {}
    evidence: dict[str, float] = {}

    def relative_for(component: str) -> float | None:
        chosen = selected.get("components", {}).get(component)
        alternatives = [
            value.get("components", {}).get(component)
            for room_id, value in breakdowns.items()
            if room_id != selected_room_id
        ]
        alternatives = [float(value) for value in alternatives if value is not None]
        if chosen is None or not alternatives:
            return None
        return max(0.0, min(1.0, 0.5 + (float(chosen) - mean(alternatives)) / 200))

    for preference_field, component in LEARNING_DIMENSIONS.items():
        value = relative_for(component)
        if value is not None:
            evidence[preference_field] = value

    current = selected.get("components", {}).get("current_occupancy")
    future = selected.get("components", {}).get("future_availability")
    chosen_values = [float(value) for value in (current, future) if value is not None]
    alternative_values: list[float] = []
    for room_id, value in breakdowns.items():
        if room_id == selected_room_id:
            continue
        components = value.get("components", {})
        values = [
            float(item)
            for item in (components.get("current_occupancy"), components.get("future_availability"))
            if item is not None
        ]
        if values:
            alternative_values.append(mean(values))
    if chosen_values and alternative_values:
        evidence["low_occupancy_priority"] = max(
            0.0, min(1.0, 0.5 + (mean(chosen_values) - mean(alternative_values)) / 200)
        )
    return evidence


def apply_evidence(
    learned: models.LearnedPreferenceProfile,
    evidence: dict[str, float],
    now: datetime,
) -> None:
    if not learned.learning_enabled:
        return
    count_fields = {
        "quiet_priority": "quiet_evidence_count",
        "low_occupancy_priority": "low_occupancy_evidence_count",
        "brightness_priority": "brightness_evidence_count",
        "comfort_priority": "comfort_evidence_count",
    }
    for field, value in evidence.items():
        if field not in count_fields:
            continue
        current = getattr(learned, field)
        setattr(learned, field, value if current is None else 0.8 * current + 0.2 * value)
        count_field = count_fields[field]
        setattr(learned, count_field, getattr(learned, count_field) + 1)
    if evidence:
        learned.updated_at = now


def compact_context(breakdowns: dict[str, dict]) -> dict[str, Any]:
    return {
        room_id: {
            "components": value.get("components", {}),
            "final_score": value.get("final_score"),
            "bucket": value.get("bucket"),
        }
        for room_id, value in breakdowns.items()
    }
