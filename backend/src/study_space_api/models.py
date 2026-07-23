from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    capacity_band: Mapped[str | None] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    devices: Mapped[list[Device]] = relationship(back_populates="room")
    observations: Mapped[list[Observation]] = relationship(back_populates="room")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(100))
    firmware_version: Mapped[str | None] = mapped_column(String(100))
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    room: Mapped[Room] = relationship(back_populates="devices")
    observations: Mapped[list[Observation]] = relationship(back_populates="device")


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (Index("ix_observations_room_observed", "room_id", "observed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    room_state: Mapped[str] = mapped_column(String(64), nullable=False)
    occupancy_level: Mapped[str] = mapped_column(String(16), nullable=False)
    suitability_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    feature_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sensor_health_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    room: Mapped[Room] = relationship(back_populates="observations")
    device: Mapped[Device] = relationship(back_populates="observations")


class PreferenceProfile(Base):
    __tablename__ = "preference_profiles"

    profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    study_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    quiet_priority: Mapped[float] = mapped_column(Float, nullable=False)
    low_occupancy_priority: Mapped[float] = mapped_column(Float, nullable=False)
    brightness_priority: Mapped[float] = mapped_column(Float, nullable=False)
    comfort_priority: Mapped[float] = mapped_column(Float, nullable=False)
    distance_priority: Mapped[float] = mapped_column(Float, nullable=False)
    preferred_temperature_c: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_room_target", "room_id", "target_at"),
        Index("ix_forecasts_room_horizon_generated", "room_id", "horizon_minutes", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    target_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_occupancy_level: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_start_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    input_end_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fallback_reason: Mapped[str | None] = mapped_column(String(128))


class RecommendationRecord(Base):
    __tablename__ = "recommendation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    candidate_room_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    rankings_json: Mapped[list] = mapped_column(JSON, nullable=False)
    explanation_source: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(200))
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    score_breakdown_json: Mapped[dict | None] = mapped_column(JSON)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("preference_profiles.profile_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LearnedPreferenceProfile(Base):
    __tablename__ = "learned_preference_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    learning_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quiet_priority: Mapped[float | None] = mapped_column(Float)
    low_occupancy_priority: Mapped[float | None] = mapped_column(Float)
    brightness_priority: Mapped[float | None] = mapped_column(Float)
    comfort_priority: Mapped[float | None] = mapped_column(Float)
    quiet_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_occupancy_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    brightness_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comfort_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class RoomSelectionEvent(Base):
    __tablename__ = "room_selection_events"
    __table_args__ = (
        Index("ix_room_selection_events_user_recorded", "user_id", "recorded_at"),
    )

    selection_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    room_id: Mapped[str] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recommendation_request_id: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    selected_rank: Mapped[int | None] = mapped_column(Integer)
    selected_score: Mapped[int | None] = mapped_column(Integer)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    context_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
