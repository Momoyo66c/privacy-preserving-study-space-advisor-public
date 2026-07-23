from __future__ import annotations

from datetime import datetime, timezone

import pytest

from study_space_api import models
from study_space_api.services.preferences import (
    apply_evidence,
    effective_snapshot,
    sanitize_score_breakdown,
    selection_evidence,
)


def preference_models() -> tuple[
    models.PreferenceProfile,
    models.LearnedPreferenceProfile,
]:
    now = datetime.now(timezone.utc)
    return (
        models.PreferenceProfile(
            profile_id="profile",
            study_mode="quiet",
            quiet_priority=0.6,
            low_occupancy_priority=0.6,
            brightness_priority=0.5,
            comfort_priority=0.5,
            distance_priority=0.2,
            preferred_temperature_c=24,
            created_at=now,
            updated_at=now,
        ),
        models.LearnedPreferenceProfile(
            user_id="user",
            learning_enabled=True,
            quiet_priority=None,
            low_occupancy_priority=None,
            brightness_priority=None,
            comfort_priority=None,
            quiet_evidence_count=0,
            low_occupancy_evidence_count=0,
            brightness_evidence_count=0,
            comfort_evidence_count=0,
            updated_at=now,
        ),
    )


def test_learning_ema_and_forty_percent_cap() -> None:
    profile, learned = preference_models()
    now = datetime.now(timezone.utc)
    apply_evidence(learned, {"quiet_priority": 0.25}, now)
    assert learned.quiet_priority == 0.25
    apply_evidence(learned, {"quiet_priority": 0.75}, now)
    assert learned.quiet_priority == pytest.approx(0.35)
    for _ in range(18):
        apply_evidence(learned, {"quiet_priority": 1.0}, now)
    effective = effective_snapshot(profile, learned)
    expected = profile.quiet_priority * 0.60 + learned.quiet_priority * 0.40
    assert effective.quiet_priority == pytest.approx(expected)
    assert learned.quiet_evidence_count == 20
    assert effective.distance_priority == profile.distance_priority


def test_missing_dimension_and_disabled_learning_do_not_create_evidence() -> None:
    _, learned = preference_models()
    breakdowns = {
        "room_a": {"components": {"quietness": 80, "brightness": None}},
        "room_b": {"components": {"quietness": 20, "brightness": None}},
    }
    evidence = selection_evidence("room_a", breakdowns)
    assert "quiet_priority" in evidence
    assert "brightness_priority" not in evidence
    learned.learning_enabled = False
    apply_evidence(learned, evidence, datetime.now(timezone.utc))
    assert learned.quiet_evidence_count == 0


def test_adapter_breakdown_is_sanitized_before_persistence() -> None:
    raw = {
        "room_a": {
            "components": {
                "quietness": 80,
                "brightness": float("nan"),
                "thermal_frame": [0.1] * 768,
            },
            "weights": {"quietness": 0.2, "password": 1},
            "final_score": 75,
            "health_factor": 0.9,
            "prompt": "private adapter text",
        },
        "not-a-candidate": {"components": {"quietness": 100}},
    }
    sanitized = sanitize_score_breakdown(raw, ["room_a"])
    assert sanitized == {
        "room_a": {
            "components": {"quietness": 80.0},
            "weights": {"quietness": 0.2},
            "final_score": 75.0,
            "health_factor": 0.9,
        }
    }
