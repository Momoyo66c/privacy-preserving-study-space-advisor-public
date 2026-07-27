from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from study_space_api import models
from study_space_api.config import Settings
from study_space_api.database import Base
from study_space_api.main import create_app
from study_space_api.recommendation.adapter import RuleBasedRecommendationAdapter
from study_space_api.recommendation.explanations import ExplanationProviderError


def observation(
    room_id: str,
    device_id: str,
    state: str,
    occupancy: str,
    sound: float,
) -> dict:
    return {
        "schema_version": "1.0",
        "observation_id": f"gate-c-{room_id}",
        "room_id": room_id,
        "device_id": device_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "window_seconds": 5,
        "room_state": state,
        "occupancy_level": occupancy,
        "suitability_score": 80,
        "confidence": 0.9,
        "features": {
            "thermal_hot_region_count": 1,
            "radar_active_target_count": None,
            "sound_rms_mean": sound,
            "light_lux": 480,
            "temperature_c": 24,
            "humidity_pct": 52,
        },
        "sensor_health": {
            "thermal": "ok",
            "radar": "not_configured",
            "sound": "ok",
            "environment": "ok",
        },
        "model": {
            "name": "gate-c-integration",
            "version": "1",
            "feature_schema_version": "1.0",
        },
        "warnings": [],
    }


def request_body(study_mode: str) -> dict:
    return {
        "schema_version": "1.0",
        "profile_id": "gate-c-integration",
        "study_mode": study_mode,
        "preferences": {
            "quiet_priority": 1,
            "low_occupancy_priority": 1,
            "brightness_priority": 0.5,
            "comfort_priority": 0.5,
            "distance_priority": 0,
        },
        "candidate_room_ids": ["room_a", "room_b", "room_c"],
    }


def deterministic_fields(response: dict) -> list[dict]:
    return [
        {
            key: value
            for key, value in item.items()
            if key not in {"explanation", "explanation_source"}
        }
        for item in response["recommendations"]
    ]


def test_gate_c_formal_ranking_llm_fallback_and_sensor_degradation(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'gate-c.db').as_posix()}",
        llm_enabled=False,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    now = datetime.now(timezone.utc)
    with app.state.database.session() as session:
        for room_id, name in (
            ("room_a", "Quiet Commons"),
            ("room_b", "Discussion Hub"),
            ("room_c", "Busy Atrium"),
        ):
            session.add(
                models.Room(
                    id=room_id,
                    name=name,
                    location="Gate C",
                    capacity_band="medium",
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()

    observations = [
        observation(
            "room_a",
            "gate-c-device-a",
            "quiet_study_recommended",
            "low",
            0.08,
        ),
        observation(
            "room_b",
            "gate-c-device-b",
            "discussion_allowed",
            "medium",
            0.43,
        ),
        observation(
            "room_c",
            "gate-c-device-c",
            "not_recommended_noisy_or_crowded",
            "high",
            0.84,
        ),
    ]

    class ApprovedProvider:
        name = "gate-c-provider"
        model = "gate-c-model"

        async def health(self):
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "llm_status": "available",
            }

        async def explain(self, items, rooms, study_mode):
            return {item.room_id: item.reasons[0] for item in items}

    class OfflineProvider(ApprovedProvider):
        async def health(self):
            return {
                "status": "degraded",
                "provider": self.name,
                "model": self.model,
                "llm_status": "unavailable",
            }

        async def explain(self, items, rooms, study_mode):
            raise ExplanationProviderError("LLM_UNAVAILABLE")

    with TestClient(app) as client:
        for payload in observations:
            assert (
                client.post("/api/v1/edge/observations", json=payload).status_code
                == 200
            )

        quiet_template = client.post(
            "/api/v1/recommendations",
            json=request_body("quiet"),
        ).json()
        discussion = client.post(
            "/api/v1/recommendations",
            json=request_body("discussion"),
        ).json()
        assert quiet_template["recommendations"][0]["room_id"] == "room_a"
        assert discussion["recommendations"][0]["room_id"] == "room_b"
        assert {
            item["explanation_source"]
            for item in quiet_template["recommendations"]
        } == {"template"}

        app.state.recommendation_adapter = RuleBasedRecommendationAdapter(
            ApprovedProvider()
        )
        quiet_llm = client.post(
            "/api/v1/recommendations",
            json=request_body("quiet"),
        ).json()
        assert deterministic_fields(quiet_llm) == deterministic_fields(
            quiet_template
        )
        assert {
            item["explanation_source"] for item in quiet_llm["recommendations"]
        } == {"llm"}

        app.state.recommendation_adapter = RuleBasedRecommendationAdapter(
            OfflineProvider()
        )
        quiet_offline = client.post(
            "/api/v1/recommendations",
            json=request_body("quiet"),
        ).json()
        assert deterministic_fields(quiet_offline) == deterministic_fields(
            quiet_template
        )
        assert quiet_offline["warnings"] == ["LLM_UNAVAILABLE"]

        degraded = deepcopy(observations[0])
        degraded["observation_id"] = "gate-c-room-a-degraded"
        degraded["observed_at"] = datetime.now(timezone.utc).isoformat()
        degraded["sensor_health"]["environment"] = "offline"
        degraded["features"]["light_lux"] = None
        degraded["features"]["temperature_c"] = None
        degraded["features"]["humidity_pct"] = None
        assert (
            client.post("/api/v1/edge/observations", json=degraded).status_code
            == 200
        )
        degraded_result = client.post(
            "/api/v1/recommendations",
            json=request_body("quiet"),
        )
        assert degraded_result.status_code == 200
        assert degraded_result.json()["recommendations"]
