from __future__ import annotations

from datetime import datetime, timedelta, timezone

from study_space_api import models
from study_space_api.database import Base, Database
from study_space_api.services.forecasting import DeterministicForecastStrategy
from study_space_api.services.history import build_history_points
from study_space_api.services.thermal import ThermalPreviewCache
from study_space_api.schemas import ThermalPreview


def make_observation(room_id: str, device_id: str, at: datetime, level: str, index: int) -> models.Observation:
    return models.Observation(observation_id=f"obs-{index}",payload_hash=str(index).zfill(64),room_id=room_id,device_id=device_id,observed_at=at,received_at=at,window_seconds=5,room_state="unknown" if level=="unknown" else "quiet_study_recommended",occupancy_level=level,suitability_score=50,confidence=0.8,feature_summary_json={},sensor_health_json={"thermal":"ok","radar":"ok","sound":"ok","environment":"ok"},warnings_json=[],model_name="test",model_version="1",feature_schema_version="1.0",synthetic=True)


def test_unknown_is_not_aggregated_as_empty(tmp_path) -> None:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    point = build_history_points([make_observation("r","d",now,"unknown",1)], now, now+timedelta(minutes=5), 5, 5)[0]
    assert point.occupancy_level == "unknown"
    assert point.occupancy_mean is None


def test_forecast_recent_average_and_utc_roundtrip(tmp_path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'service.db').as_posix()}")
    Base.metadata.create_all(database.engine)
    now = datetime.now(timezone.utc)
    with database.session() as session:
        session.add(models.Room(id="r",name="R",active=True,created_at=now,updated_at=now))
        session.add(models.Device(id="d",room_id="r",active=True,last_seen_at=now))
        session.flush()
        for index, level in enumerate(["low","medium","medium"]):
            session.add(make_observation("r","d",now-timedelta(minutes=10-index*2),level,index))
        session.commit()
        result = DeterministicForecastStrategy(30).predict(session,"r",30,now)
        session.commit()
        assert result.method == "recent_exponential_average"
        assert result.predicted_occupancy_level in {"low","medium"}
        assert session.query(models.Observation).first().observed_at.tzinfo is not None
    database.dispose()


def test_forecast_uses_stale_current_when_recent_window_is_empty(tmp_path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'stale.db').as_posix()}")
    Base.metadata.create_all(database.engine)
    now = datetime.now(timezone.utc)
    with database.session() as session:
        session.add(models.Room(id="r",name="R",active=True,created_at=now,updated_at=now))
        session.add(models.Device(id="d",room_id="r",active=True,last_seen_at=now-timedelta(hours=2)))
        session.flush()
        session.add(make_observation("r","d",now-timedelta(hours=2),"medium",1))
        session.commit()
        result = DeterministicForecastStrategy(30).predict(session,"r",30,now)
        assert result.method == "current_persistence"
        assert result.predicted_occupancy_level == "medium"
        assert result.confidence == 0.15
    database.dispose()


def test_thermal_cache_expiration_without_database() -> None:
    now = datetime.now(timezone.utc)
    preview = ThermalPreview(schema_version="1.0",room_id="r",captured_at=now,width=32,height=24,values=[0.1]*768,normalization="window_min_max_clipped",expires_in_seconds=1)
    cache = ThermalPreviewCache()
    assert cache.put(preview,now).available is True
    assert cache.get("r",now+timedelta(seconds=2)).unavailable_reason == "expired"
