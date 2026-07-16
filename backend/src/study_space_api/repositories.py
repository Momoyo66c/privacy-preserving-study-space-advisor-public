from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import models


class RoomRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, room_id: str) -> models.Room | None:
        return self.session.get(models.Room, room_id)

    def list_active(self) -> list[models.Room]:
        return list(self.session.scalars(select(models.Room).where(models.Room.active.is_(True)).order_by(models.Room.id)))


class DeviceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, device_id: str) -> models.Device | None:
        return self.session.get(models.Device, device_id)

    def add(self, device: models.Device) -> None:
        self.session.add(device)


class ObservationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_public_id(self, observation_id: str) -> models.Observation | None:
        return self.session.scalar(select(models.Observation).where(models.Observation.observation_id == observation_id))

    def add(self, observation: models.Observation) -> None:
        self.session.add(observation)

    def latest_for_room(self, room_id: str, before: datetime | None = None) -> models.Observation | None:
        query = select(models.Observation).where(models.Observation.room_id == room_id)
        if before is not None:
            query = query.where(models.Observation.observed_at <= before)
        return self.session.scalar(query.order_by(models.Observation.observed_at.desc(), models.Observation.id.desc()).limit(1))

    def range_for_room(self, room_id: str, start: datetime, end: datetime) -> list[models.Observation]:
        query = (
            select(models.Observation)
            .where(
                models.Observation.room_id == room_id,
                models.Observation.observed_at >= start,
                models.Observation.observed_at <= end,
            )
            .order_by(models.Observation.observed_at)
        )
        return list(self.session.scalars(query))

    def before_for_room(self, room_id: str, end: datetime, start: datetime | None = None) -> list[models.Observation]:
        query = select(models.Observation).where(
            models.Observation.room_id == room_id,
            models.Observation.observed_at <= end,
        )
        if start is not None:
            query = query.where(models.Observation.observed_at >= start)
        return list(self.session.scalars(query.order_by(models.Observation.observed_at)))


class PreferenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, profile_id: str) -> models.PreferenceProfile | None:
        return self.session.get(models.PreferenceProfile, profile_id)

    def add(self, profile: models.PreferenceProfile) -> None:
        self.session.add(profile)


class ForecastRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, forecast: models.Forecast) -> None:
        self.session.add(forecast)


class RecommendationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: models.RecommendationRecord) -> None:
        self.session.add(record)


def cleanup_expired(
    session: Session,
    observation_before: datetime,
    forecast_before: datetime,
    recommendation_before: datetime,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, statement in (
        ("recommendations", delete(models.RecommendationRecord).where(models.RecommendationRecord.generated_at < recommendation_before)),
        ("forecasts", delete(models.Forecast).where(models.Forecast.generated_at < forecast_before)),
        ("observations", delete(models.Observation).where(models.Observation.observed_at < observation_before)),
    ):
        result = session.execute(statement)
        counts[key] = int(result.rowcount or 0)
    return counts
