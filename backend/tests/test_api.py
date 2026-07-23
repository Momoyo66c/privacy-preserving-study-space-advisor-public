from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from study_space_api.config import Settings
from study_space_api.database import Base
from study_space_api.main import create_app
from study_space_api import models


def test_health_reports_stub_as_degraded(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["recommendation_adapter"]["mode"] == "stub"
    assert response.headers["x-request-id"]


def test_observation_is_idempotent_and_conflicts_on_changed_payload(client: TestClient, valid_observation: dict) -> None:
    first = client.post("/api/v1/edge/observations", json=valid_observation)
    second = client.post("/api/v1/edge/observations", json=valid_observation)
    changed = deepcopy(valid_observation)
    changed["confidence"] = 0.5
    conflict = client.post("/api/v1/edge/observations", json=changed)
    assert first.status_code == second.status_code == 200
    assert first.json()["server_received_at"] == second.json()["server_received_at"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_unknown_room_and_validation_use_error_envelope(client: TestClient, valid_observation: dict) -> None:
    valid_observation["room_id"] = "missing"
    missing = client.post("/api/v1/edge/observations", json=valid_observation)
    assert missing.status_code == 404
    assert missing.json()["schema_version"] == "1.0"
    invalid = client.post("/api/v1/edge/observations", json={"schema_version": "1.0"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_status_history_and_forecast_flow(client: TestClient, valid_observation: dict) -> None:
    assert client.post("/api/v1/edge/observations", json=valid_observation).status_code == 200
    statuses = client.get("/api/v1/rooms/status")
    assert statuses.status_code == 200
    room_a = next(room for room in statuses.json()["rooms"] if room["room_id"] == "room_a")
    assert room_a["room_state"] == "quiet_study_recommended"
    assert room_a["is_stale"] is False
    assert {item["horizon_minutes"] for item in room_a["forecasts"]} == {15, 30}
    room_b = next(room for room in statuses.json()["rooms"] if room["room_id"] == "room_b")
    assert room_b["room_state"] == "unknown"
    assert room_b["is_stale"] is True

    history = client.get("/api/v1/rooms/room_a/history?hours=1&bucket_minutes=5")
    assert history.status_code == 200
    assert len(history.json()["points"]) == 12
    assert sum(point["observation_count"] for point in history.json()["points"]) == 1
    forecast = client.get("/api/v1/rooms/room_a/forecast?minutes=30")
    assert forecast.status_code == 200
    assert forecast.json()["method"] == "current_persistence"


def test_preferences_upsert_get_and_range_validation(client: TestClient) -> None:
    body = {"schema_version":"1.0","study_mode":"quiet","quiet_priority":0.8,"low_occupancy_priority":0.7,"brightness_priority":0.3,"comfort_priority":0.4,"distance_priority":0.2,"preferred_temperature_c":None}
    put = client.put("/api/v1/preferences/demo-user", json=body)
    assert put.status_code == 200
    assert client.get("/api/v1/preferences/demo-user").json()["study_mode"] == "quiet"
    body["quiet_priority"] = 1.1
    assert client.put("/api/v1/preferences/demo-user", json=body).status_code == 422
    assert client.get("/api/v1/preferences/missing").status_code == 404


def test_thermal_preview_is_separate_and_available(client: TestClient) -> None:
    body = {"schema_version":"1.0","room_id":"room_a","captured_at":datetime.now(timezone.utc).isoformat(),"width":32,"height":24,"values":[0.5]*768,"normalization":"window_min_max_clipped","expires_in_seconds":30}
    put = client.put("/api/v1/edge/rooms/room_a/thermal-preview", json=body)
    assert put.status_code == 200
    assert put.json()["available"] is True
    assert client.get("/api/v1/rooms/room_a/thermal-preview").json()["values"] == [0.5] * 768
    unavailable = client.get("/api/v1/rooms/room_b/thermal-preview")
    assert unavailable.json() == {"schema_version":"1.0","room_id":"room_b","available":False,"captured_at":None,"width":None,"height":None,"values":None,"normalization":None,"expires_at":None,"unavailable_reason":"not_available"}


def test_live_sensor_snapshot_combines_status_and_ephemeral_preview(client: TestClient, valid_observation: dict) -> None:
    assert client.post("/api/v1/edge/observations", json=valid_observation).status_code == 200
    preview = {
        "schema_version": "1.0",
        "room_id": "room_a",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "width": 32,
        "height": 24,
        "values": [0.25] * 768,
        "normalization": "window_min_max_clipped",
        "expires_in_seconds": 30,
    }
    assert client.put("/api/v1/edge/rooms/room_a/thermal-preview", json=preview).status_code == 200
    sound_preview = {
        "schema_version": "1.0",
        "room_id": "room_a",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "rms": 0.0375,
        "expires_in_seconds": 3,
    }
    assert client.put("/api/v1/edge/rooms/room_a/sound-preview", json=sound_preview).status_code == 200

    response = client.get("/api/v1/rooms/room_a/live")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["room"]["features"]["temperature_c"] == valid_observation["features"]["temperature_c"]
    assert body["room"]["features"]["sound_rms_mean"] == valid_observation["features"]["sound_rms_mean"]
    assert body["thermal_preview"]["available"] is True
    assert body["thermal_preview"]["values"] == [0.25] * 768
    assert body["sound_preview"]["available"] is True
    assert body["sound_preview"]["rms"] == 0.0375
    assert client.get("/api/v1/rooms/room_a/sound-preview").json()["rms"] == 0.0375
    assert client.get("/api/v1/rooms/missing/live").status_code == 404


def test_recommendation_stub_and_record(client: TestClient, valid_observation: dict, app) -> None:
    client.post("/api/v1/edge/observations", json=valid_observation)
    body = {"schema_version":"1.0","profile_id":"demo-user","study_mode":"quiet","preferences":{"quiet_priority":0.9,"low_occupancy_priority":0.8,"brightness_priority":0.4,"comfort_priority":0.5,"distance_priority":0.3},"candidate_room_ids":["room_a","room_b","room_c"]}
    response = client.post("/api/v1/recommendations", json=body)
    assert response.status_code == 200
    assert response.json()["recommendations"][0]["room_id"] == "room_a"
    assert response.json()["recommendations"][0]["explanation_source"] == "stub"
    with app.state.database.session() as session:
        record = session.query(models.RecommendationRecord).one()
        assert record.adapter_name == "module3-deterministic-stub"
        assert record.score_breakdown_json is None
        assert "values" not in str(record.rankings_json)


def test_anonymous_demo_endpoints_can_be_disabled(client: TestClient, app) -> None:
    app.state.settings.allow_anonymous_demo = False
    body = {
        "schema_version": "1.0",
        "profile_id": "demo-user",
        "study_mode": "quiet",
        "preferences": {
            "quiet_priority": 1,
            "low_occupancy_priority": 1,
            "brightness_priority": 0,
            "comfort_priority": 0,
            "distance_priority": 0,
        },
        "candidate_room_ids": ["room_a"],
    }
    response = client.post("/api/v1/recommendations", json=body)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_DEMO_DISABLED"


def test_optional_edge_bearer_token(tmp_path, valid_observation: dict) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'auth.db').as_posix()}", edge_api_token="secret")
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    now = datetime.now(timezone.utc)
    with app.state.database.session() as session:
        session.add(models.Room(id="room_a",name="A",active=True,created_at=now,updated_at=now))
        session.commit()
    with TestClient(app) as client:
        assert client.post("/api/v1/edge/observations", json=valid_observation).status_code == 401
        assert client.post("/api/v1/edge/observations", json=valid_observation, headers={"Authorization":"Bearer secret"}).status_code == 200


def test_future_and_old_observations_are_rejected(client: TestClient, valid_observation: dict) -> None:
    valid_observation["observed_at"] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    assert client.post("/api/v1/edge/observations", json=valid_observation).status_code == 422
    valid_observation["observation_id"] = "old-observation"
    valid_observation["observed_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    assert client.post("/api/v1/edge/observations", json=valid_observation).status_code == 422


def test_adapter_failure_falls_back_without_exposing_exception(client: TestClient, app) -> None:
    class FailingAdapter:
        name = "failing"

        async def health(self):
            return {"status":"degraded","name":self.name,"mode":"test"}

        async def rank(self, context):
            raise RuntimeError("sensitive provider detail")

    app.state.recommendation_adapter = FailingAdapter()
    body = {"schema_version":"1.0","profile_id":"demo-user","study_mode":"quiet","preferences":{"quiet_priority":0.9,"low_occupancy_priority":0.8,"brightness_priority":0.4,"comfort_priority":0.5,"distance_priority":0.3},"candidate_room_ids":["room_a"]}
    response = client.post("/api/v1/recommendations", json=body)
    assert response.status_code == 200
    assert "RECOMMENDATION_ADAPTER_FALLBACK" in response.json()["warnings"]
    assert "sensitive" not in response.text


def test_body_limit_and_unavailable_database_health(tmp_path) -> None:
    limited = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'limited.db').as_posix()}", max_request_body_bytes=8192))
    Base.metadata.create_all(limited.state.database.engine)
    with TestClient(limited) as client:
        response = client.post("/api/v1/recommendations", content=b"x" * 9000, headers={"content-type":"application/json"})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    unavailable = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'missing' / 'db.sqlite').as_posix()}"))
    with TestClient(unavailable) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["database"] == "unavailable"
