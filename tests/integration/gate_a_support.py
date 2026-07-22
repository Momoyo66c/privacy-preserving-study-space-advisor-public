from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from study_space_api import models
from study_space_api.config import Settings
from study_space_api.database import Base
from study_space_api.main import create_app
from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_ml.inference.predictor import EdgePredictor


ROOT = Path(__file__).resolve().parents[2]


def generate_observation() -> tuple[dict, dict]:
    """Run the real Module 1 simulator and Module 2 predictor in memory."""

    config = load_config(ROOT / "edge" / "hardware" / "config" / "example.yaml")
    clock = ManualClock(
        start=datetime.now(timezone.utc) - timedelta(seconds=config.window_seconds)
    )
    orchestrator = build_orchestrator(config, clock=clock)
    try:
        window = orchestrator.run_window().payload
    finally:
        orchestrator.close()
    observation = EdgePredictor().predict_window(window)
    return window, observation


def create_gate_a_app(database_url: str) -> FastAPI:
    settings = Settings(
        database_url=database_url,
        allow_anonymous_demo=True,
        cors_origins=["http://127.0.0.1:5177"],
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
                    location="Gate A simulation",
                    capacity_band="medium",
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
    return app


def ingest_simulated_observation(app: FastAPI) -> tuple[dict, dict, dict]:
    window, observation = generate_observation()
    with TestClient(app) as client:
        response = client.post("/api/v1/edge/observations", json=observation)
        response.raise_for_status()
        accepted = response.json()
    return window, observation, accepted


def anonymous_recommendation_request() -> dict:
    return {
        "schema_version": "1.0",
        "profile_id": "demo-user",
        "study_mode": "quiet",
        "preferences": {
            "quiet_priority": 0.8,
            "low_occupancy_priority": 0.7,
            "brightness_priority": 0.3,
            "comfort_priority": 0.4,
            "distance_priority": 0.2,
        },
        "candidate_room_ids": ["room_a", "room_b", "room_c"],
    }
