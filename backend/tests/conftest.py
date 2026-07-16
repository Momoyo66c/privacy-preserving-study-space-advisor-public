from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from study_space_api import models
from study_space_api.config import Settings
from study_space_api.database import Base
from study_space_api.main import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", cors_origins=["http://testserver"])


@pytest.fixture
def app(settings: Settings):
    application = create_app(settings)
    Base.metadata.create_all(application.state.database.engine)
    now = datetime.now(timezone.utc)
    with application.state.database.session() as session:
        for room_id, name in (("room_a", "Quiet Commons"), ("room_b", "Discussion Hub"), ("room_c", "Busy Atrium")):
            session.add(models.Room(id=room_id, name=name, location="Demo", capacity_band="medium", active=True, created_at=now, updated_at=now))
        session.commit()
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_observation() -> dict:
    payload = json.loads((ROOT / "shared" / "fixtures" / "edge_observation_valid.json").read_text(encoding="utf-8"))
    payload["observed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return payload
