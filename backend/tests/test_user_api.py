from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from study_space_api import models
from study_space_api.adapters.recommendation_stub import StubRecommendationAdapter
from study_space_api.api import utcnow
from study_space_api.repositories import cleanup_expired


def register(client: TestClient, username: str = "study.user") -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "schema_version": "1.0",
            "username": username,
            "password": "a-secure-password",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"X-CSRF-Token": body["csrf_token"]}


def add_room_observations(client: TestClient, valid_observation: dict) -> None:
    variants = [
        ("room_a", "device-a", "observation-a", "quiet_study_recommended", "low", 0.10, 500, 24.0),
        ("room_b", "device-b", "observation-b", "discussion_allowed", "medium", 0.45, 250, 27.0),
        (
            "room_c",
            "device-c",
            "observation-c",
            "not_recommended_noisy_or_crowded",
            "high",
            0.85,
            80,
            31.0,
        ),
    ]
    for room_id, device_id, observation_id, state, occupancy, sound, light, temperature in variants:
        payload = deepcopy(valid_observation)
        payload.update(
            {
                "room_id": room_id,
                "device_id": device_id,
                "observation_id": observation_id,
                "room_state": state,
                "occupancy_level": occupancy,
            }
        )
        payload["features"].update(
            {
                "sound_rms_mean": sound,
                "light_lux": light,
                "temperature_c": temperature,
            }
        )
        assert client.post("/api/v1/edge/observations", json=payload).status_code == 200


def test_registration_session_password_hash_and_logout(client: TestClient, app) -> None:
    body, headers = register(client, "Study.User")
    assert body["user"]["username"] == "study.user"
    assert client.get("/api/v1/me").json()["username"] == "study.user"
    with app.state.database.session() as session:
        user = session.query(models.User).one()
        assert user.password_hash != "a-secure-password"
        assert user.password_hash.startswith("$argon2id$")
        stored_session = session.query(models.UserSession).one()
        assert stored_session.token_hash not in client.cookies.values()
    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "schema_version": "1.0",
            "username": "study.user",
            "password": "another-secure-password",
        },
    )
    assert duplicate.status_code == 409
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/me").status_code == 401


def test_csrf_and_generic_login_failure(client: TestClient) -> None:
    register(client)
    update = {
        "schema_version": "1.0",
        "study_mode": "quiet",
        "quiet_priority": 0.8,
        "low_occupancy_priority": 0.7,
        "brightness_priority": 0.4,
        "comfort_priority": 0.5,
        "distance_priority": 0.0,
        "preferred_temperature_c": 24,
        "learning_enabled": True,
    }
    rejected = client.put("/api/v1/me/preferences", json=update)
    assert rejected.status_code == 403
    failure = client.post(
        "/api/v1/auth/login",
        json={
            "schema_version": "1.0",
            "username": "study.user",
            "password": "wrong-password",
        },
    )
    assert failure.status_code == 401
    assert failure.json()["error"]["message"] == "Username or password is incorrect"


def test_authenticated_recommendation_selection_learning_and_idempotency(
    client: TestClient,
    app,
    valid_observation: dict,
) -> None:
    class LearningBreakdownAdapter(StubRecommendationAdapter):
        name = "module4-test-breakdown"

        async def rank(self, context):
            result = await super().rank(context)
            result.adapter_name = self.name
            result.score_breakdown = {
                room.room_id: {
                    "components": {
                        "quietness": 90 - index * 35,
                        "brightness": 85 - index * 30,
                        "comfort": 80 - index * 25,
                        "current_occupancy": 95 - index * 35,
                        "future_availability": 90 - index * 30,
                        "thermal_frame": [0.1] * 768,
                    },
                    "final_score": 90 - index * 30,
                    "bucket": 0,
                    "prompt": "must-not-be-persisted",
                }
                for index, room in enumerate(context.rooms)
            }
            return result

    app.state.recommendation_adapter = LearningBreakdownAdapter()
    _, headers = register(client)
    add_room_observations(client, valid_observation)
    recommendation = client.post(
        "/api/v1/me/recommendations",
        headers=headers,
        json={
            "schema_version": "1.0",
            "study_mode": "quiet",
            "candidate_room_ids": ["room_a", "room_b", "room_c"],
        },
    )
    assert recommendation.status_code == 200, recommendation.text
    result = recommendation.json()
    assert result["recommendations"][0]["room_id"] == "room_a"
    selection_id = str(uuid4())
    payload = {
        "schema_version": "1.0",
        "selection_id": selection_id,
        "room_id": "room_a",
        "recommendation_request_id": result["request_id"],
        "source": "recommendation",
    }
    first = client.post("/api/v1/me/room-selections", headers=headers, json=payload)
    duplicate = client.post("/api/v1/me/room-selections", headers=headers, json=payload)
    assert first.status_code == duplicate.status_code == 200
    assert first.json()["recorded_at"] == duplicate.json()["recorded_at"]
    preferences = client.get("/api/v1/me/preferences").json()
    assert preferences["evidence_counts"]["quiet_priority"] == 1
    assert preferences["effective"]["quiet_priority"] != preferences["manual"]["quiet_priority"]
    with app.state.database.session() as session:
        assert session.query(models.RoomSelectionEvent).count() == 1
        record = session.query(models.RecommendationRecord).one()
        assert record.user_id is not None
        assert record.score_breakdown_json
        assert "password" not in str(record.score_breakdown_json).lower()
        assert "thermal_frame" not in str(record.score_breakdown_json)
        assert "prompt" not in str(record.score_breakdown_json)

    changed = dict(payload, room_id="room_b")
    conflict = client.post("/api/v1/me/room-selections", headers=headers, json=changed)
    assert conflict.status_code == 409
    history = client.get("/api/v1/me/room-selections").json()
    assert len(history["selections"]) == 1
    assert history["selections"][0]["room_name"] == "Quiet Commons"
    assert client.get("/api/v1/me/room-selections?cursor=%").status_code == 422


def test_learning_disable_reset_history_delete_and_account_delete(
    client: TestClient,
    app,
    valid_observation: dict,
) -> None:
    _, headers = register(client)
    add_room_observations(client, valid_observation)
    update = {
        "schema_version": "1.0",
        "study_mode": "discussion",
        "quiet_priority": 0.2,
        "low_occupancy_priority": 0.3,
        "brightness_priority": 0.4,
        "comfort_priority": 0.5,
        "distance_priority": 0.6,
        "preferred_temperature_c": 23,
        "learning_enabled": False,
    }
    response = client.put("/api/v1/me/preferences", headers=headers, json=update)
    assert response.status_code == 200
    assert response.json()["effective"] == response.json()["manual"]
    selected = client.post(
        "/api/v1/me/room-selections",
        headers=headers,
        json={
            "schema_version": "1.0",
            "selection_id": str(uuid4()),
            "room_id": "room_b",
            "recommendation_request_id": None,
            "source": "room_detail",
        },
    )
    assert selected.status_code == 200
    assert client.get("/api/v1/me/preferences").json()["evidence_counts"]["quiet_priority"] == 0
    reset = client.post("/api/v1/me/preferences/reset-learned", headers=headers)
    assert reset.status_code == 200
    deleted = client.delete("/api/v1/me/room-selections", headers=headers)
    assert deleted.json()["deleted_count"] == 1
    assert client.get("/api/v1/me/room-selections").json()["selections"] == []
    assert client.post(
        "/api/v1/me/recommendations",
        headers=headers,
        json={
            "schema_version": "1.0",
            "study_mode": "discussion",
            "candidate_room_ids": ["room_a", "room_b"],
        },
    ).status_code == 200
    assert client.delete("/api/v1/me", headers=headers).status_code == 200
    with app.state.database.session() as session:
        assert session.query(models.User).count() == 0
        assert session.query(models.UserSession).count() == 0
        assert session.query(models.RoomSelectionEvent).count() == 0
        assert session.query(models.LearnedPreferenceProfile).count() == 0
        audit = session.query(models.RecommendationRecord).one()
        assert audit.user_id is None
        assert audit.profile_id == "deleted-user"


def test_session_expiry_and_login_rate_limit(client: TestClient, app) -> None:
    _, _ = register(client, "limited.user")
    with app.state.database.session() as session:
        stored = session.query(models.UserSession).one()
        stored.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/v1/me").status_code == 401
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "schema_version": "1.0",
                "username": "limited.user",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        json={
            "schema_version": "1.0",
            "username": "limited.user",
            "password": "wrong-password",
        },
    )
    assert limited.status_code == 429


def test_recommendation_ownership_and_server_side_preferences(
    client: TestClient,
    valid_observation: dict,
) -> None:
    _, first_headers = register(client, "first.user")
    add_room_observations(client, valid_observation)
    rejects_client_weights = client.post(
        "/api/v1/me/recommendations",
        headers=first_headers,
        json={
            "schema_version": "1.0",
            "study_mode": "quiet",
            "candidate_room_ids": ["room_a"],
            "preferences": {"quiet_priority": 1},
        },
    )
    assert rejects_client_weights.status_code == 422
    recommendation = client.post(
        "/api/v1/me/recommendations",
        headers=first_headers,
        json={
            "schema_version": "1.0",
            "study_mode": "quiet",
            "candidate_room_ids": ["room_a", "room_b"],
        },
    ).json()
    assert client.post("/api/v1/auth/logout", headers=first_headers).status_code == 200
    _, second_headers = register(client, "second.user")
    cross_user = client.post(
        "/api/v1/me/room-selections",
        headers=second_headers,
        json={
            "schema_version": "1.0",
            "selection_id": str(uuid4()),
            "room_id": "room_a",
            "recommendation_request_id": recommendation["request_id"],
            "source": "recommendation",
        },
    )
    assert cross_user.status_code == 404


def test_selection_retention_cleanup(client: TestClient, app) -> None:
    _, headers = register(client, "cleanup.user")
    response = client.post(
        "/api/v1/me/room-selections",
        headers=headers,
        json={
            "schema_version": "1.0",
            "selection_id": str(uuid4()),
            "room_id": "room_a",
            "recommendation_request_id": None,
            "source": "room_detail",
        },
    )
    assert response.status_code == 200
    now = utcnow()
    with app.state.database.session() as session:
        event = session.query(models.RoomSelectionEvent).one()
        event.recorded_at = now - timedelta(days=91)
        session.flush()
        counts = cleanup_expired(
            session,
            observation_before=now - timedelta(days=30),
            forecast_before=now - timedelta(days=30),
            recommendation_before=now - timedelta(days=7),
            selection_before=now - timedelta(days=90),
            session_before=now,
        )
        session.commit()
        assert counts["room_selections"] == 1
        assert session.query(models.RoomSelectionEvent).count() == 0
