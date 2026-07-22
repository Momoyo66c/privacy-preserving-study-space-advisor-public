from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import __version__, models
from .adapters.recommendation import RecommendationContext
from .adapters.recommendation_stub import StubRecommendationAdapter
from .config import Settings
from .errors import APIError, request_id_for
from .repositories import DeviceRepository, ObservationRepository, PreferenceRepository, RecommendationRepository, RoomRepository
from .schemas import (
    EdgeObservation,
    FeatureSummary,
    ForecastResult,
    HealthResponse,
    LiveSensorSnapshotResponse,
    ObservationAccepted,
    OccupancyLevel,
    PreferenceBody,
    PreferenceProfileResponse,
    RecommendationRequest,
    RecommendationResponse,
    RoomDetailResponse,
    RoomHistoryResponse,
    RoomMetadata,
    RoomState,
    RoomStatus,
    RoomStatusesResponse,
    RoomsResponse,
    SensorHealth,
    SoundPreview,
    SoundPreviewResponse,
    StableId,
    ThermalPreview,
    ThermalPreviewResponse,
)
from .services.forecasting import DeterministicForecastStrategy
from .services.history import build_history_points

router = APIRouter()
logger = logging.getLogger("study_space_api.api")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.database.session() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_edge_auth(request: Request, settings: Settings = Depends(get_settings)) -> None:
    if settings.edge_api_token is None:
        return
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value, settings.edge_api_token):
        raise APIError(401, "AUTHENTICATION_REQUIRED", "A valid edge bearer token is required")


def canonical_hash(payload: EdgeObservation) -> str:
    raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def room_metadata(room: models.Room) -> RoomMetadata:
    return RoomMetadata(
        id=room.id,
        name=room.name,
        location=room.location,
        latitude=room.latitude,
        longitude=room.longitude,
        capacity_band=room.capacity_band,
        active=room.active,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def build_room_status(session: Session, room: models.Room, settings: Settings, now: datetime) -> RoomStatus:
    latest = ObservationRepository(session).latest_for_room(room.id, before=now + timedelta(seconds=settings.future_skew_seconds))
    strategy = DeterministicForecastStrategy(settings.stale_after_seconds)
    forecasts = [strategy.predict(session, room.id, minutes, now) for minutes in (15, 30)]
    if latest is None:
        return RoomStatus(
            room_id=room.id,
            name=room.name,
            location=room.location,
            observed_at=None,
            received_at=None,
            room_state=RoomState.UNKNOWN,
            occupancy_level=OccupancyLevel.UNKNOWN,
            features=FeatureSummary(),
            sensor_health={key: SensorHealth.NOT_CONFIGURED for key in ("thermal", "radar", "sound", "environment")},
            warnings=["NO_OBSERVATION"],
            data_age_seconds=None,
            is_stale=True,
            forecasts=forecasts,
        )
    age = max(0.0, (now - latest.observed_at).total_seconds())
    return RoomStatus(
        room_id=room.id,
        name=room.name,
        location=room.location,
        observed_at=latest.observed_at,
        received_at=latest.received_at,
        room_state=latest.room_state,
        occupancy_level=latest.occupancy_level,
        suitability_score=latest.suitability_score,
        confidence=latest.confidence,
        features=FeatureSummary.model_validate(latest.feature_summary_json),
        sensor_health=latest.sensor_health_json,
        warnings=latest.warnings_json,
        data_age_seconds=age,
        is_stale=age > settings.stale_after_seconds,
        forecasts=forecasts,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response, session: Session = Depends(get_session)) -> HealthResponse:
    database_status = "ok"
    try:
        session.execute(select(1))
    except SQLAlchemyError:
        database_status = "unavailable"
    try:
        adapter_status = await request.app.state.recommendation_adapter.health()
    except Exception:
        adapter_status = {"status": "degraded", "name": "unavailable", "mode": "fallback"}
    status = "unhealthy" if database_status != "ok" else ("degraded" if adapter_status.get("status") != "ok" else "ok")
    if database_status != "ok":
        response.status_code = 503
    return HealthResponse(
        status=status,
        server_time=utcnow(),
        database=database_status,
        recommendation_adapter=adapter_status,
        write_auth="enabled" if request.app.state.settings.edge_api_token else "disabled",
        version=__version__,
    )


@router.post("/api/v1/edge/observations", response_model=ObservationAccepted, dependencies=[Depends(require_edge_auth)])
def create_observation(payload: EdgeObservation, request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> ObservationAccepted:
    now = utcnow()
    age = now - payload.observed_at
    if payload.observed_at > now + timedelta(seconds=settings.future_skew_seconds):
        raise APIError(422, "OBSERVATION_TIME_INVALID", "observed_at is too far in the future")
    if age > timedelta(days=settings.max_observation_age_days):
        raise APIError(422, "OBSERVATION_TIME_INVALID", "observation is older than the configured retention window")
    payload_hash = canonical_hash(payload)
    observations = ObservationRepository(session)
    existing = observations.get_by_public_id(payload.observation_id)
    if existing is not None:
        if not hmac.compare_digest(existing.payload_hash, payload_hash):
            raise APIError(409, "IDEMPOTENCY_CONFLICT", "observation_id already exists with a different payload")
        logger.info("observation_duplicate request_id=%s observation_id=%s room_id=%s", request_id_for(request), existing.observation_id, existing.room_id)
        return ObservationAccepted(observation_id=existing.observation_id, server_received_at=existing.received_at)

    room = RoomRepository(session).get(payload.room_id)
    if room is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room must be created before observations are accepted", {"room_id": payload.room_id})
    devices = DeviceRepository(session)
    device = devices.get(payload.device_id)
    if device is None:
        if not settings.auto_register_devices:
            raise APIError(404, "DEVICE_NOT_FOUND", "Device is not registered", {"device_id": payload.device_id})
        device = models.Device(id=payload.device_id, room_id=payload.room_id, last_seen_at=now, active=True)
        devices.add(device)
    elif device.room_id != payload.room_id:
        raise APIError(409, "DEVICE_ROOM_CONFLICT", "Device is registered to another room")
    else:
        device.last_seen_at = now

    warnings = list(payload.warnings)
    if age.total_seconds() > settings.delayed_observation_warning_seconds and "DELAYED_OBSERVATION" not in warnings:
        warnings.append("DELAYED_OBSERVATION")
    observations.add(
        models.Observation(
            observation_id=payload.observation_id,
            payload_hash=payload_hash,
            room_id=payload.room_id,
            device_id=payload.device_id,
            observed_at=payload.observed_at,
            received_at=now,
            window_seconds=payload.window_seconds,
            room_state=str(payload.room_state),
            occupancy_level=str(payload.occupancy_level),
            suitability_score=payload.suitability_score,
            confidence=payload.confidence,
            feature_summary_json=payload.features.model_dump(mode="json"),
            sensor_health_json=payload.sensor_health.model_dump(mode="json"),
            warnings_json=warnings,
            model_name=payload.model.name,
            model_version=payload.model.version,
            feature_schema_version=payload.model.feature_schema_version,
            synthetic=False,
        )
    )
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise APIError(500, "DATABASE_ERROR", "Observation could not be stored") from exc
    logger.info(
        "observation_accepted request_id=%s observation_id=%s room_id=%s state=%s delay_ms=%d",
        request_id_for(request), payload.observation_id, payload.room_id, payload.room_state, max(0, int(age.total_seconds() * 1000)),
    )
    return ObservationAccepted(observation_id=payload.observation_id, server_received_at=now)


@router.get("/api/v1/rooms", response_model=RoomsResponse)
def list_rooms(session: Session = Depends(get_session)) -> RoomsResponse:
    return RoomsResponse(rooms=[room_metadata(room) for room in RoomRepository(session).list_active()])


@router.get("/api/v1/rooms/status", response_model=RoomStatusesResponse)
def list_room_statuses(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> RoomStatusesResponse:
    now = utcnow()
    result = RoomStatusesResponse(rooms=[build_room_status(session, room, settings, now) for room in RoomRepository(session).list_active()])
    session.commit()
    return result


@router.get("/api/v1/rooms/{room_id}/live", response_model=LiveSensorSnapshotResponse)
def get_live_sensor_snapshot(
    room_id: StableId,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> LiveSensorSnapshotResponse:
    """Return the latest sensor summary and ephemeral thermal preview together."""

    room = RoomRepository(session).get(room_id)
    if room is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    now = utcnow()
    result = LiveSensorSnapshotResponse(
        generated_at=now,
        room=build_room_status(session, room, settings, now),
        thermal_preview=request.app.state.thermal_cache.get(room_id, now=now),
        sound_preview=request.app.state.sound_cache.get(room_id, now=now),
    )
    session.commit()
    return result


@router.get("/api/v1/rooms/{room_id}", response_model=RoomDetailResponse)
def get_room(room_id: StableId, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> RoomDetailResponse:
    room = RoomRepository(session).get(room_id)
    if room is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    status = build_room_status(session, room, settings, utcnow())
    session.commit()
    return RoomDetailResponse(**status.model_dump(), latitude=room.latitude, longitude=room.longitude, capacity_band=room.capacity_band, active=room.active)


@router.get("/api/v1/rooms/{room_id}/history", response_model=RoomHistoryResponse)
def get_history(
    room_id: StableId,
    hours: int = Query(default=24, ge=1),
    bucket_minutes: int = Query(default=5),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RoomHistoryResponse:
    if RoomRepository(session).get(room_id) is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    if hours > settings.max_history_hours or bucket_minutes not in {1, 5, 15, 30, 60}:
        raise APIError(422, "VALIDATION_ERROR", "History query is outside configured limits")
    point_count = hours * 60 // bucket_minutes
    if point_count > settings.max_history_points:
        raise APIError(422, "VALIDATION_ERROR", "History query would return too many points")
    end = utcnow().replace(second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    rows = ObservationRepository(session).range_for_room(room_id, start, end)
    return RoomHistoryResponse(
        room_id=room_id,
        start_at=start,
        end_at=end,
        bucket_minutes=bucket_minutes,
        points=build_history_points(rows, start, end, bucket_minutes, settings.expected_observation_interval_seconds),
    )


@router.get("/api/v1/rooms/{room_id}/forecast", response_model=ForecastResult)
def get_forecast(
    room_id: StableId,
    minutes: int = Query(default=30),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ForecastResult:
    if minutes not in {15, 30}:
        raise APIError(422, "VALIDATION_ERROR", "minutes must be 15 or 30")
    if RoomRepository(session).get(room_id) is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    result = DeterministicForecastStrategy(settings.stale_after_seconds).predict(session, room_id, minutes, utcnow())
    session.commit()
    return result


@router.put("/api/v1/preferences/{profile_id}", response_model=PreferenceProfileResponse)
def put_preference(profile_id: StableId, body: PreferenceBody, session: Session = Depends(get_session)) -> PreferenceProfileResponse:
    now = utcnow()
    repository = PreferenceRepository(session)
    profile = repository.get(profile_id)
    data = body.model_dump(exclude={"schema_version"})
    if profile is None:
        profile = models.PreferenceProfile(profile_id=profile_id, created_at=now, updated_at=now, **data)
        repository.add(profile)
    else:
        for key, value in data.items():
            setattr(profile, key, value)
        profile.updated_at = now
    session.commit()
    return PreferenceProfileResponse(profile_id=profile.profile_id, created_at=profile.created_at, updated_at=profile.updated_at, **body.model_dump())


@router.get("/api/v1/preferences/{profile_id}", response_model=PreferenceProfileResponse)
def get_preference(profile_id: StableId, session: Session = Depends(get_session)) -> PreferenceProfileResponse:
    profile = PreferenceRepository(session).get(profile_id)
    if profile is None:
        raise APIError(404, "PROFILE_NOT_FOUND", "Preference profile was not found")
    return PreferenceProfileResponse.model_validate({column.name: getattr(profile, column.name) for column in models.PreferenceProfile.__table__.columns})


@router.put("/api/v1/edge/rooms/{room_id}/thermal-preview", response_model=ThermalPreviewResponse, dependencies=[Depends(require_edge_auth)])
def put_thermal_preview(room_id: StableId, body: ThermalPreview, request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> ThermalPreviewResponse:
    if room_id != body.room_id:
        raise APIError(422, "VALIDATION_ERROR", "Path room_id must match payload room_id")
    if RoomRepository(session).get(room_id) is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    now = utcnow()
    if body.captured_at > now + timedelta(seconds=settings.future_skew_seconds):
        raise APIError(422, "PREVIEW_TIME_INVALID", "captured_at is too far in the future")
    if body.captured_at + timedelta(seconds=body.expires_in_seconds) <= now:
        raise APIError(422, "PREVIEW_EXPIRED", "Preview was already expired when received")
    return request.app.state.thermal_cache.put(body, now=now)


@router.get("/api/v1/rooms/{room_id}/thermal-preview", response_model=ThermalPreviewResponse)
def get_thermal_preview(room_id: StableId, request: Request, session: Session = Depends(get_session)) -> ThermalPreviewResponse:
    if RoomRepository(session).get(room_id) is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    return request.app.state.thermal_cache.get(room_id)


@router.put(
    "/api/v1/edge/rooms/{room_id}/sound-preview",
    response_model=SoundPreviewResponse,
    dependencies=[Depends(require_edge_auth)],
)
def put_sound_preview(
    room_id: StableId,
    body: SoundPreview,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SoundPreviewResponse:
    if room_id != body.room_id:
        raise APIError(422, "VALIDATION_ERROR", "Path room_id must match payload room_id")
    if RoomRepository(session).get(room_id) is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    now = utcnow()
    if body.captured_at > now + timedelta(seconds=settings.future_skew_seconds):
        raise APIError(422, "PREVIEW_TIME_INVALID", "captured_at is too far in the future")
    if body.captured_at + timedelta(seconds=body.expires_in_seconds) <= now:
        raise APIError(422, "PREVIEW_EXPIRED", "Preview was already expired when received")
    return request.app.state.sound_cache.put(body, now=now)


@router.get(
    "/api/v1/rooms/{room_id}/sound-preview",
    response_model=SoundPreviewResponse,
)
def get_sound_preview(
    room_id: StableId,
    request: Request,
    session: Session = Depends(get_session),
) -> SoundPreviewResponse:
    if RoomRepository(session).get(room_id) is None:
        raise APIError(404, "ROOM_NOT_FOUND", "Room was not found")
    return request.app.state.sound_cache.get(room_id)


@router.post("/api/v1/recommendations", response_model=RecommendationResponse)
async def recommendations(
    payload: RecommendationRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RecommendationResponse:
    rooms_by_id = {room.id: room for room in RoomRepository(session).list_active()}
    missing = [room_id for room_id in payload.candidate_room_ids if room_id not in rooms_by_id]
    if missing:
        raise APIError(404, "CANDIDATE_ROOM_NOT_FOUND", "Candidate rooms must exist and be active", {"room_ids": missing})
    now = utcnow()
    statuses = [build_room_status(session, rooms_by_id[room_id], settings, now) for room_id in payload.candidate_room_ids]
    context = RecommendationContext(payload, statuses)
    adapter = request.app.state.recommendation_adapter
    started = time.perf_counter()
    fallback_reason: str | None = None
    try:
        adapter_result = await asyncio.wait_for(adapter.rank(context), timeout=settings.recommendation_adapter_timeout_seconds)
    except Exception as exc:
        fallback_reason = type(exc).__name__
        adapter_result = await StubRecommendationAdapter().rank(context)
        adapter_result.warnings.append("RECOMMENDATION_ADAPTER_FALLBACK")
    latency_ms = (time.perf_counter() - started) * 1000
    req_id = request_id_for(request)
    response = RecommendationResponse(request_id=req_id, generated_at=now, recommendations=adapter_result.recommendations, warnings=adapter_result.warnings)
    RecommendationRepository(session).add(
        models.RecommendationRecord(
            request_id=req_id,
            profile_id=payload.profile_id,
            generated_at=now,
            candidate_room_ids_json=payload.candidate_room_ids,
            rankings_json=[item.model_dump(mode="json") for item in response.recommendations],
            explanation_source=response.recommendations[0].explanation_source if response.recommendations else "stub",
            adapter_name=adapter_result.adapter_name,
            fallback_reason=fallback_reason,
            latency_ms=latency_ms,
            warnings_json=response.warnings,
        )
    )
    session.commit()
    return response
