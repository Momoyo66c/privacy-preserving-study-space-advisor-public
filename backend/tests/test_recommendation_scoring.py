from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from study_space_api.adapters.recommendation import RecommendationContext
from study_space_api.recommendation.scoring import rank_rooms, recommendation_items
from study_space_api.schemas import (
    FeatureSummary,
    ForecastResult,
    RecommendationPreferences,
    RecommendationRequest,
    RoomStatus,
)

NOW = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)


def make_room(
    room_id: str,
    state: str,
    occupancy: str,
    *,
    sound: float | None = 0.2,
    light_lux: float | None = 500,
    temperature: float | None = 24,
    humidity: float | None = 50,
    confidence: float = 0.9,
    stale: bool = False,
    environment_health: str = "ok",
    sound_health: str = "ok",
    forecast_15: str = "low",
    forecast_30: str = "low",
) -> RoomStatus:
    forecasts = [
        ForecastResult(
            room_id=room_id,
            generated_at=NOW,
            target_at=NOW + timedelta(minutes=horizon),
            horizon_minutes=horizon,
            predicted_occupancy_level=level,
            confidence=confidence,
            method="test",
            model_version="test",
            input_start_at=NOW - timedelta(minutes=5),
            input_end_at=NOW,
            fallback_reason=None,
        )
        for horizon, level in ((15, forecast_15), (30, forecast_30))
    ]
    return RoomStatus(
        room_id=room_id,
        name=room_id.replace("_", " ").title(),
        location="Demo",
        observed_at=NOW,
        received_at=NOW,
        room_state=state,
        occupancy_level=occupancy,
        suitability_score=80,
        confidence=confidence,
        features=FeatureSummary(
            sound_rms_mean=sound,
            light_lux=light_lux,
            temperature_c=temperature,
            humidity_pct=humidity,
        ),
        sensor_health={
            "thermal": "ok",
            "radar": "not_configured",
            "sound": sound_health,
            "environment": environment_health,
        },
        warnings=[],
        data_age_seconds=45 if stale else 5,
        is_stale=stale,
        forecasts=forecasts,
    )


def context(study_mode: str, rooms: list[RoomStatus], **priorities: float) -> RecommendationContext:
    preferences = RecommendationPreferences(
        quiet_priority=priorities.get("quiet_priority", 0.8),
        low_occupancy_priority=priorities.get("low_occupancy_priority", 0.7),
        brightness_priority=priorities.get("brightness_priority", 0.4),
        comfort_priority=priorities.get("comfort_priority", 0.5),
        distance_priority=priorities.get("distance_priority", 0.3),
    )
    request = RecommendationRequest(
        schema_version="1.0",
        profile_id="test-profile",
        study_mode=study_mode,
        preferences=preferences,
        candidate_room_ids=[room.room_id for room in rooms],
    )
    return RecommendationContext(request=request, rooms=rooms)


def standard_rooms() -> list[RoomStatus]:
    return [
        make_room("quiet_room", "quiet_study_recommended", "low", sound=0.1),
        make_room("discussion_room", "discussion_allowed", "medium", sound=0.45),
        make_room(
            "busy_room",
            "not_recommended_noisy_or_crowded",
            "high",
            sound=0.85,
            forecast_15="high",
            forecast_30="high",
        ),
    ]


def test_quiet_and_discussion_modes_produce_expected_deterministic_ranking() -> None:
    rooms = standard_rooms()
    quiet = rank_rooms(context("quiet", rooms))
    discussion = rank_rooms(context("discussion", rooms))
    assert [item.room.room_id for item in quiet] == [
        "quiet_room",
        "discussion_room",
        "busy_room",
    ]
    assert [item.room.room_id for item in discussion][:2] == [
        "discussion_room",
        "quiet_room",
    ]
    assert quiet[1].bucket == "unknown"
    assert discussion[1].bucket == "unknown"
    assert [item.room.room_id for item in rank_rooms(context("quiet", rooms))] == [
        item.room.room_id for item in quiet
    ]


def test_missing_uncalibrated_dimensions_are_omitted_and_weights_renormalize() -> None:
    room = make_room(
        "relative_only",
        "quiet_study_recommended",
        "low",
        light_lux=None,
        temperature=None,
        humidity=None,
        environment_health="degraded",
        sound=None,
        sound_health="offline",
    )
    scored = rank_rooms(context("quiet", [room]))[0]
    assert set(scored.components) == {
        "mode_match",
        "current_occupancy",
        "future_availability",
    }
    assert "brightness" not in scored.weights
    assert "comfort" not in scored.weights
    assert "quietness" not in scored.weights
    assert "distance" not in scored.weights
    assert 0 <= scored.final_score <= 100


def test_user_priorities_change_ranking_without_changing_rules() -> None:
    quiet_but_busy = make_room(
        "quiet_but_busy",
        "quiet_study_recommended",
        "high",
        sound=0.02,
        forecast_15="high",
        forecast_30="high",
    )
    louder_but_empty = make_room(
        "louder_but_empty",
        "quiet_study_recommended",
        "empty",
        sound=0.82,
        forecast_15="empty",
        forecast_30="empty",
    )
    rooms = [quiet_but_busy, louder_but_empty]
    quiet_priority = rank_rooms(
        context(
            "quiet",
            rooms,
            quiet_priority=1,
            low_occupancy_priority=0,
            brightness_priority=0,
            comfort_priority=0,
            distance_priority=0,
        )
    )
    occupancy_priority = rank_rooms(
        context(
            "quiet",
            rooms,
            quiet_priority=0,
            low_occupancy_priority=1,
            brightness_priority=0,
            comfort_priority=0,
            distance_priority=0,
        )
    )
    assert quiet_priority[0].room.room_id == "quiet_but_busy"
    assert occupancy_priority[0].room.room_id == "louder_but_empty"


def test_stale_unknown_and_degraded_rooms_are_bucketed_and_penalized() -> None:
    fresh = make_room("fresh", "quiet_study_recommended", "low", confidence=0.75)
    stale = make_room("stale", "quiet_study_recommended", "low", confidence=0.99, stale=True)
    unknown = make_room("unknown", "unknown", "unknown", confidence=0.99)
    degraded = make_room(
        "degraded",
        "quiet_study_recommended",
        "low",
        confidence=0.75,
        environment_health="degraded",
    )
    ranked = rank_rooms(context("quiet", [unknown, stale, degraded, fresh]))
    assert ranked[0].bucket == "fresh"
    assert ranked[-2].bucket == "stale"
    assert ranked[-1].bucket == "unknown"
    assert stale.is_stale and ranked[-2].freshness_factor == 0.65
    degraded_item = next(item for item in ranked if item.room.room_id == "degraded")
    assert degraded_item.health_factor == 0.85
    assert any("degraded" in reason for reason in degraded_item.reasons)


def test_score_breakdown_matches_learning_boundary_and_template_is_grounded() -> None:
    ranked = rank_rooms(context("quiet", standard_rooms()))
    items = recommendation_items(ranked)
    breakdown = ranked[0].breakdown()
    assert set(breakdown["components"]).issubset(
        {
            "mode_match",
            "quietness",
            "current_occupancy",
            "future_availability",
            "brightness",
            "comfort",
            "distance",
        }
    )
    assert 0 <= breakdown["final_score"] <= 100
    assert items[0].explanation_source == "template"
    assert items[0].explanation
    assert len(items[0].reasons) <= 4


@pytest.mark.parametrize("index", range(30))
def test_thirty_fixed_scenarios_remain_bounded_and_private(index: int) -> None:
    states = [
        "empty_or_low_activity",
        "quiet_study_recommended",
        "discussion_allowed",
        "not_recommended_noisy_or_crowded",
        "unknown",
    ]
    occupancies = ["empty", "low", "medium", "high", "unknown"]
    room = make_room(
        f"room_{index}",
        states[index % len(states)],
        occupancies[(index * 2) % len(occupancies)],
        sound=(index % 10) / 10,
        light_lux=None if index % 4 == 0 else float(200 + index * 20),
        confidence=(index % 11) / 10,
        stale=index % 3 == 0,
        environment_health="degraded" if index % 7 == 0 else "ok",
    )
    scored = rank_rooms(context(("quiet", "discussion", "any")[index % 3], [room]))[0]
    serialized = str(scored.breakdown()).lower()
    assert 0 <= scored.final_score <= 100
    assert "thermal" not in serialized
    assert "audio" not in serialized
    assert "username" not in serialized
