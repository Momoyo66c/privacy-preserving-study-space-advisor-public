from __future__ import annotations

from study_space_api import models
from study_space_api.recommendation.adapter import RuleBasedRecommendationAdapter
from study_space_api.recommendation.advisor import (
    interpret_study_goal,
    sanitize_study_goal,
)
from study_space_api.schemas import RecommendationPreferences

from test_user_api import add_room_observations, register


def test_goal_interpretation_is_transient_and_deterministic() -> None:
    saved = RecommendationPreferences(
        quiet_priority=0.4,
        low_occupancy_priority=0.5,
        brightness_priority=0.3,
        comfort_priority=0.2,
        distance_priority=0.1,
    )
    result = interpret_study_goal(
        "Two-person group discussion with bright light and plenty of seats",
        "quiet",
        saved,
    )
    assert result.study_mode == "discussion"
    assert result.needs == ["discussion", "low_occupancy", "bright"]
    assert result.preferences.low_occupancy_priority == 0.9
    assert result.preferences.brightness_priority == 0.9
    assert saved.brightness_priority == 0.3


def test_goal_privacy_filter_rejects_identifiers_and_secrets() -> None:
    for value in (
        "Send the result to student@example.com",
        "My student ID is A1234567X",
        "Use this API key for the request",
        "Call me on 81234567",
    ):
        try:
            sanitize_study_goal(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"sensitive goal was accepted: {value}")


def test_authenticated_study_advisor_uses_goal_without_persisting_it(
    client,
    app,
    valid_observation,
) -> None:
    captured: dict[str, str | None] = {}

    class GoalProvider:
        name = "goal-provider"
        model = "goal-model"

        async def health(self):
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "llm_status": "available",
            }

        async def explain(self, items, rooms, study_mode, study_goal=None):
            captured["study_mode"] = study_mode
            captured["study_goal"] = study_goal
            return {
                item.room_id: item.reasons[0]
                for item in items
            }

    app.state.recommendation_adapter = RuleBasedRecommendationAdapter(GoalProvider())
    _, headers = register(client, "advisor.user")
    add_room_observations(client, valid_observation)
    goal = "I need a room for a two-person group discussion and presentation."
    response = client.post(
        "/api/v1/me/study-advisor",
        headers=headers,
        json={
            "schema_version": "1.0",
            "study_goal": goal,
            "candidate_room_ids": ["room_a", "room_b", "room_c"],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["interpreted_study_mode"] == "discussion"
    assert payload["focus_room_id"] == "room_b"
    assert payload["advice_source"] == "llm"
    assert "STUDY_GOAL_NOT_STORED" in payload["warnings"]
    assert captured == {"study_mode": "discussion", "study_goal": goal}
    with app.state.database.session() as session:
        record = session.query(models.RecommendationRecord).one()
        persisted = str(
            {
                "candidate_ids": record.candidate_room_ids_json,
                "rankings": record.rankings_json,
                "breakdown": record.score_breakdown_json,
                "warnings": record.warnings_json,
            }
        )
        assert goal not in persisted
        assert "presentation" not in persisted.lower()


def test_regular_dashboard_recommendations_do_not_invoke_llm(
    client,
    app,
    valid_observation,
) -> None:
    calls = 0

    class CountingProvider:
        name = "counting-provider"
        model = "counting-model"

        async def health(self):
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "llm_status": "available",
            }

        async def explain(self, items, rooms, study_mode, study_goal=None):
            nonlocal calls
            calls += 1
            return {item.room_id: item.reasons[0] for item in items}

    app.state.recommendation_adapter = RuleBasedRecommendationAdapter(CountingProvider())
    _, headers = register(client, "advisor.dashboard")
    add_room_observations(client, valid_observation)
    response = client.post(
        "/api/v1/me/recommendations",
        headers=headers,
        json={
            "schema_version": "1.0",
            "study_mode": "quiet",
            "candidate_room_ids": ["room_a", "room_b", "room_c"],
        },
    )
    assert response.status_code == 200, response.text
    assert calls == 0
    assert all(
        item["explanation_source"] == "template"
        for item in response.json()["recommendations"]
    )


def test_study_advisor_requires_csrf_and_rejects_sensitive_goal(
    client,
    app,
    valid_observation,
) -> None:
    _, headers = register(client, "advisor.privacy")
    add_room_observations(client, valid_observation)
    body = {
        "schema_version": "1.0",
        "study_goal": "My email is student@example.com and I need a quiet room",
        "candidate_room_ids": ["room_a", "room_b", "room_c"],
    }
    assert client.post("/api/v1/me/study-advisor", json=body).status_code == 403
    rejected = client.post("/api/v1/me/study-advisor", headers=headers, json=body)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "PRIVACY_SENSITIVE_INPUT"
