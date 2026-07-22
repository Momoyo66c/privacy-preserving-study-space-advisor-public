from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
StableId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class RoomState(StrEnum):
    EMPTY_OR_LOW_ACTIVITY = "empty_or_low_activity"
    QUIET_STUDY_RECOMMENDED = "quiet_study_recommended"
    DISCUSSION_ALLOWED = "discussion_allowed"
    NOT_RECOMMENDED_NOISY_OR_CROWDED = "not_recommended_noisy_or_crowded"
    UNKNOWN = "unknown"


class OccupancyLevel(StrEnum):
    EMPTY = "empty"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class SensorHealth(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    NOT_CONFIGURED = "not_configured"


class StudyMode(StrEnum):
    QUIET = "quiet"
    DISCUSSION = "discussion"
    ANY = "any"


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc)


class FeatureSummary(StrictModel):
    thermal_hot_region_count: int | None = Field(default=None, ge=0)
    radar_active_target_count: int | None = Field(default=None, ge=0)
    sound_rms_mean: FiniteFloat | None = Field(default=None, ge=0, le=1)
    sound_peak_max: FiniteFloat | None = Field(default=None, ge=0, le=1)
    light_relative_mean: FiniteFloat | None = Field(default=None, ge=0, le=1)
    light_lux: FiniteFloat | None = Field(default=None, ge=0)
    temperature_c: FiniteFloat | None = Field(default=None, ge=-50, le=100)
    humidity_pct: FiniteFloat | None = Field(default=None, ge=0, le=100)


class SensorHealthSummary(StrictModel):
    thermal: SensorHealth
    radar: SensorHealth
    sound: SensorHealth
    environment: SensorHealth


class ModelInfo(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    feature_schema_version: str = Field(min_length=1, max_length=100)


class EdgeObservation(StrictModel):
    schema_version: Literal["1.0"]
    observation_id: StableId
    room_id: StableId
    device_id: StableId
    observed_at: datetime
    window_seconds: int = Field(ge=5, le=10)
    room_state: RoomState
    occupancy_level: OccupancyLevel
    suitability_score: int = Field(ge=0, le=100)
    confidence: FiniteFloat = Field(ge=0, le=1)
    features: FeatureSummary
    sensor_health: SensorHealthSummary
    model: ModelInfo
    warnings: list[str] = Field(default_factory=list, max_length=32)

    _normalize_observed_at = field_validator("observed_at")(utc_datetime)

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 256 for value in values):
            raise ValueError("warnings must be non-empty and at most 256 characters")
        return values


class ObservationAccepted(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    accepted: Literal[True] = True
    observation_id: StableId
    server_received_at: datetime


class ThermalPreview(StrictModel):
    schema_version: Literal["1.0"]
    room_id: StableId
    captured_at: datetime
    width: Literal[32]
    height: Literal[24]
    values: list[FiniteFloat]
    normalization: Literal["window_min_max_clipped"]
    expires_in_seconds: int = Field(ge=1, le=30)

    _normalize_captured_at = field_validator("captured_at")(utc_datetime)

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: list[float]) -> list[float]:
        if len(values) != 768:
            raise ValueError("thermal preview must contain exactly 768 values")
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in values):
            raise ValueError("thermal preview values must be finite and between 0 and 1")
        return values


class ThermalPreviewResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    room_id: StableId
    available: bool
    captured_at: datetime | None = None
    width: int | None = None
    height: int | None = None
    values: list[float] | None = None
    normalization: str | None = None
    expires_at: datetime | None = None
    unavailable_reason: str | None = None


class SoundPreview(StrictModel):
    schema_version: Literal["1.0"]
    room_id: StableId
    captured_at: datetime
    rms: FiniteFloat = Field(ge=0, le=1)
    expires_in_seconds: int = Field(ge=1, le=10)

    _normalize_captured_at = field_validator("captured_at")(utc_datetime)


class SoundPreviewResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    room_id: StableId
    available: bool
    captured_at: datetime | None = None
    rms: float | None = Field(default=None, ge=0, le=1)
    expires_at: datetime | None = None
    unavailable_reason: str | None = None


class RoomMetadata(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: StableId
    name: str
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    capacity_band: Literal["small", "medium", "large"] | None = None
    active: bool
    created_at: datetime
    updated_at: datetime


class RoomsResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    rooms: list[RoomMetadata]


class ForecastResult(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    room_id: StableId
    generated_at: datetime
    target_at: datetime
    horizon_minutes: Literal[15, 30]
    predicted_occupancy_level: OccupancyLevel
    confidence: FiniteFloat = Field(ge=0, le=1)
    method: str
    model_version: str
    input_start_at: datetime | None
    input_end_at: datetime | None
    fallback_reason: str | None


class RoomStatus(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    room_id: StableId
    name: str
    location: str | None = None
    observed_at: datetime | None
    received_at: datetime | None
    room_state: RoomState
    occupancy_level: OccupancyLevel
    suitability_score: int | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    features: FeatureSummary
    sensor_health: dict[str, SensorHealth]
    warnings: list[str]
    data_age_seconds: float | None = Field(default=None, ge=0)
    is_stale: bool
    forecasts: list[ForecastResult]


class RoomStatusesResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    rooms: list[RoomStatus]


class LiveSensorSnapshotResponse(StrictModel):
    """Dashboard-friendly projection of the latest anonymous sensor state."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    generated_at: datetime
    room: RoomStatus
    thermal_preview: ThermalPreviewResponse
    sound_preview: SoundPreviewResponse


class RoomDetailResponse(RoomStatus):
    latitude: float | None = None
    longitude: float | None = None
    capacity_band: str | None = None
    active: bool


class HistoryPoint(StrictModel):
    bucket_start: datetime
    bucket_end: datetime
    observation_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    dominant_room_state: RoomState
    last_room_state: RoomState
    occupancy_level: OccupancyLevel
    occupancy_mean: float | None = Field(default=None, ge=0, le=3)
    suitability_mean: float | None = Field(default=None, ge=0, le=100)
    confidence_mean: float | None = Field(default=None, ge=0, le=1)
    sound_rms_mean: float | None = Field(default=None, ge=0, le=1)
    light_lux_mean: float | None = Field(default=None, ge=0)
    temperature_c_mean: float | None = None
    humidity_pct_mean: float | None = Field(default=None, ge=0, le=100)


class RoomHistoryResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    room_id: StableId
    start_at: datetime
    end_at: datetime
    bucket_minutes: Literal[1, 5, 15, 30, 60]
    points: list[HistoryPoint]


class PreferenceBody(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    study_mode: StudyMode
    quiet_priority: FiniteFloat = Field(ge=0, le=1)
    low_occupancy_priority: FiniteFloat = Field(ge=0, le=1)
    brightness_priority: FiniteFloat = Field(ge=0, le=1)
    comfort_priority: FiniteFloat = Field(ge=0, le=1)
    distance_priority: FiniteFloat = Field(ge=0, le=1)
    preferred_temperature_c: FiniteFloat | None = Field(default=None, ge=10, le=35)


class PreferenceProfileResponse(PreferenceBody):
    profile_id: StableId
    created_at: datetime
    updated_at: datetime


class RecommendationPreferences(StrictModel):
    quiet_priority: FiniteFloat = Field(ge=0, le=1)
    low_occupancy_priority: FiniteFloat = Field(ge=0, le=1)
    brightness_priority: FiniteFloat = Field(ge=0, le=1)
    comfort_priority: FiniteFloat = Field(ge=0, le=1)
    distance_priority: FiniteFloat = Field(ge=0, le=1)


class RecommendationRequest(StrictModel):
    schema_version: Literal["1.0"]
    profile_id: StableId
    study_mode: StudyMode
    preferences: RecommendationPreferences
    candidate_room_ids: list[StableId] = Field(min_length=1, max_length=50)

    @field_validator("candidate_room_ids")
    @classmethod
    def unique_candidates(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("candidate_room_ids must be unique")
        return values


class RecommendationItem(StrictModel):
    room_id: StableId
    rank: int = Field(ge=1)
    score: int = Field(ge=0, le=100)
    current_state: RoomState
    occupancy_level: OccupancyLevel
    forecast_30m: OccupancyLevel
    confidence: float = Field(ge=0, le=1)
    is_stale: bool
    reasons: list[str] = Field(min_length=1, max_length=4)
    explanation: str
    explanation_source: Literal["stub", "template", "llm"]


class RecommendationResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    request_id: str
    generated_at: datetime
    recommendations: list[RecommendationItem]
    warnings: list[str]


class HealthResponse(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    status: Literal["ok", "degraded", "unhealthy"]
    server_time: datetime
    database: Literal["ok", "unavailable"]
    recommendation_adapter: dict[str, str]
    write_auth: Literal["enabled", "disabled"]
    version: str
