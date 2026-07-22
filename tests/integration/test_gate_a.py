from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.integration.gate_a_support import (
    anonymous_recommendation_request,
    create_gate_a_app,
    generate_observation,
)


def test_simulated_window_reaches_backend_status_and_recommendation(tmp_path) -> None:
    window, observation = generate_observation()
    app = create_gate_a_app(f"sqlite:///{(tmp_path / 'gate-a.db').as_posix()}")

    with TestClient(app) as client:
        accepted = client.post("/api/v1/edge/observations", json=observation)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["observation_id"] == observation["observation_id"]

        statuses = client.get("/api/v1/rooms/status")
        assert statuses.status_code == 200, statuses.text
        room_a = next(
            room for room in statuses.json()["rooms"] if room["room_id"] == "room_a"
        )
        assert room_a["observed_at"] == observation["observed_at"]
        assert room_a["room_state"] == observation["room_state"]
        assert room_a["sensor_health"] == observation["sensor_health"]

        history = client.get("/api/v1/rooms/room_a/history?hours=1&bucket_minutes=5")
        assert history.status_code == 200, history.text
        assert any(point["observation_count"] for point in history.json()["points"])

        recommendation = client.post(
            "/api/v1/recommendations",
            json=anonymous_recommendation_request(),
        )
        assert recommendation.status_code == 200, recommendation.text
        assert recommendation.json()["recommendations"][0]["room_id"] == "room_a"

    serialized_observation = json.dumps(observation).lower()
    assert window["schema_version"] == observation["schema_version"] == "1.0"
    assert observation["model"]["name"] == "edge-rule-baseline"
    assert "temperatures_c" not in serialized_observation
    assert "raw_audio" not in serialized_observation
    assert "tracks" not in serialized_observation
