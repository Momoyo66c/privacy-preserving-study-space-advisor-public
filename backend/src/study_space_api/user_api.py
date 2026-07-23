from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import time
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .adapters.recommendation import RecommendationContext
from .adapters.recommendation_stub import StubRecommendationAdapter
from .api import build_room_status, get_session, get_settings, utcnow
from .config import Settings
from .errors import APIError, request_id_for
from .repositories import RoomRepository
from .schemas import (
    AuthCredentials,
    AuthSessionResponse,
    AuthenticatedRecommendationRequest,
    DeleteResult,
    MePreferenceResponse,
    MePreferenceUpdate,
    RecommendationResponse,
    RoomSelectionAccepted,
    RoomSelectionHistoryItem,
    RoomSelectionHistoryResponse,
    RoomSelectionRequest,
    UserResponse,
)
from .services.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    authenticate_request,
    hash_password,
    issue_session,
    verify_password,
)
from .services.preferences import (
    apply_evidence,
    as_recommendation_preferences,
    compact_context,
    effective_snapshot,
    preference_response,
    reset_learned,
    sanitize_score_breakdown,
    selection_evidence,
)

router = APIRouter()


def _user_response(user: models.User) -> UserResponse:
    return UserResponse(user_id=user.id, username=user.username, created_at=user.created_at)


def _set_session_cookies(
    response: Response,
    token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    cookie_options = {
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": settings.session_ttl_seconds,
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **cookie_options)
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, **cookie_options)


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


def _profile_and_learned(
    session: Session,
    user: models.User,
) -> tuple[models.PreferenceProfile, models.LearnedPreferenceProfile]:
    profile = session.get(models.PreferenceProfile, user.profile_id)
    learned = session.get(models.LearnedPreferenceProfile, user.id)
    if profile is None or learned is None:
        raise APIError(500, "PROFILE_STATE_INVALID", "The user preference state is unavailable")
    return profile, learned


def _selection_hash(payload: RoomSelectionRequest) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = int(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise APIError(422, "CURSOR_INVALID", "The selection history cursor is invalid") from None
    if value < 0:
        raise APIError(422, "CURSOR_INVALID", "The selection history cursor is invalid")
    return value


@router.post("/api/v1/auth/register", response_model=AuthSessionResponse, status_code=201)
def register(
    payload: AuthCredentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthSessionResponse:
    now = utcnow()
    if session.scalar(select(models.User.id).where(models.User.username == payload.username)):
        raise APIError(409, "USERNAME_TAKEN", "The username is already registered")
    user_id = str(uuid.uuid4())
    profile_id = f"user-{user_id}"
    profile = models.PreferenceProfile(
        profile_id=profile_id,
        study_mode="quiet",
        quiet_priority=0.6,
        low_occupancy_priority=0.6,
        brightness_priority=0.5,
        comfort_priority=0.5,
        distance_priority=0.0,
        preferred_temperature_c=24.0,
        created_at=now,
        updated_at=now,
    )
    user = models.User(
        id=user_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        profile_id=profile_id,
        active=True,
        created_at=now,
        last_login_at=now,
    )
    learned = models.LearnedPreferenceProfile(
        user_id=user_id,
        learning_enabled=True,
        quiet_priority=None,
        low_occupancy_priority=None,
        brightness_priority=None,
        comfort_priority=None,
        quiet_evidence_count=0,
        low_occupancy_evidence_count=0,
        brightness_evidence_count=0,
        comfort_evidence_count=0,
        updated_at=now,
    )
    try:
        # Explicit flush boundaries keep SQLite foreign-key ordering deterministic
        # without requiring ORM relationships solely for insertion order.
        session.add(profile)
        session.flush()
        session.add(user)
        session.flush()
        session.add(learned)
        issued = issue_session(session, user, now, settings)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "USERNAME_TAKEN", "The username is already registered") from exc
    _set_session_cookies(response, issued.token, issued.csrf_token, settings)
    return AuthSessionResponse(
        user=_user_response(user),
        csrf_token=issued.csrf_token,
        expires_at=issued.model.expires_at,
    )


@router.post("/api/v1/auth/login", response_model=AuthSessionResponse)
def login(
    payload: AuthCredentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthSessionResponse:
    now = utcnow()
    ip = request.client.host if request.client else "unknown"
    limiter = request.app.state.login_attempt_limiter
    limiter.check(payload.username, ip, now)
    user = session.scalar(select(models.User).where(models.User.username == payload.username))
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        limiter.record_failure(payload.username, ip, now)
        raise APIError(401, "INVALID_CREDENTIALS", "Username or password is incorrect")
    limiter.reset(payload.username, ip)
    user.last_login_at = now
    issued = issue_session(session, user, now, settings)
    session.commit()
    _set_session_cookies(response, issued.token, issued.csrf_token, settings)
    return AuthSessionResponse(
        user=_user_response(user),
        csrf_token=issued.csrf_token,
        expires_at=issued.model.expires_at,
    )


@router.post("/api/v1/auth/logout", response_model=DeleteResult)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DeleteResult:
    auth = authenticate_request(request, session, utcnow(), require_csrf=True)
    auth.session.revoked_at = utcnow()
    session.commit()
    _clear_session_cookies(response, settings)
    return DeleteResult(deleted=True, deleted_count=1)


@router.get("/api/v1/me", response_model=UserResponse)
def me(request: Request, session: Session = Depends(get_session)) -> UserResponse:
    auth = authenticate_request(request, session, utcnow())
    session.commit()
    return _user_response(auth.user)


@router.delete("/api/v1/me", response_model=DeleteResult)
def delete_me(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DeleteResult:
    auth = authenticate_request(request, session, utcnow(), require_csrf=True)
    profile_id = auth.user.profile_id
    session.execute(
        update(models.RecommendationRecord)
        .where(models.RecommendationRecord.user_id == auth.user.id)
        .values(user_id=None, profile_id="deleted-user")
    )
    session.delete(auth.user)
    session.flush()
    profile = session.get(models.PreferenceProfile, profile_id)
    if profile is not None:
        session.delete(profile)
    session.commit()
    _clear_session_cookies(response, settings)
    return DeleteResult(deleted=True, deleted_count=1)


@router.get("/api/v1/me/preferences", response_model=MePreferenceResponse)
def get_my_preferences(
    request: Request,
    session: Session = Depends(get_session),
) -> MePreferenceResponse:
    auth = authenticate_request(request, session, utcnow())
    profile, learned = _profile_and_learned(session, auth.user)
    session.commit()
    return preference_response(profile, learned)


@router.put("/api/v1/me/preferences", response_model=MePreferenceResponse)
def put_my_preferences(
    payload: MePreferenceUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> MePreferenceResponse:
    now = utcnow()
    auth = authenticate_request(request, session, now, require_csrf=True)
    profile, learned = _profile_and_learned(session, auth.user)
    values = payload.model_dump(exclude={"schema_version", "learning_enabled"})
    for field, value in values.items():
        setattr(profile, field, value)
    profile.updated_at = now
    learned.learning_enabled = payload.learning_enabled
    learned.updated_at = now
    session.commit()
    return preference_response(profile, learned)


@router.post("/api/v1/me/preferences/reset-learned", response_model=MePreferenceResponse)
def reset_my_learned_preferences(
    request: Request,
    session: Session = Depends(get_session),
) -> MePreferenceResponse:
    now = utcnow()
    auth = authenticate_request(request, session, now, require_csrf=True)
    profile, learned = _profile_and_learned(session, auth.user)
    reset_learned(learned, now)
    session.commit()
    return preference_response(profile, learned)


@router.post("/api/v1/me/recommendations", response_model=RecommendationResponse)
async def my_recommendations(
    payload: AuthenticatedRecommendationRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RecommendationResponse:
    now = utcnow()
    auth = authenticate_request(request, session, now, require_csrf=True)
    profile, learned = _profile_and_learned(session, auth.user)
    rooms_by_id = {room.id: room for room in RoomRepository(session).list_active()}
    missing = [room_id for room_id in payload.candidate_room_ids if room_id not in rooms_by_id]
    if missing:
        raise APIError(
            404,
            "CANDIDATE_ROOM_NOT_FOUND",
            "Candidate rooms must exist and be active",
            {"room_ids": missing},
        )
    statuses = [
        build_room_status(session, rooms_by_id[room_id], settings, now)
        for room_id in payload.candidate_room_ids
    ]
    effective = effective_snapshot(profile, learned)
    context = RecommendationContext(
        request=payload,
        rooms=statuses,
        effective_preferences=as_recommendation_preferences(effective),
        preferred_temperature_c=effective.preferred_temperature_c,
    )
    adapter = request.app.state.recommendation_adapter
    started = time.perf_counter()
    fallback_reason: str | None = None
    try:
        adapter_result = await asyncio.wait_for(
            adapter.rank(context),
            timeout=settings.recommendation_adapter_timeout_seconds,
        )
    except Exception as exc:
        fallback_reason = type(exc).__name__
        adapter_result = await StubRecommendationAdapter().rank(context)
        adapter_result.warnings.append("RECOMMENDATION_ADAPTER_FALLBACK")
    latency_ms = (time.perf_counter() - started) * 1000
    recommendation_request_id = request_id_for(request)
    result = RecommendationResponse(
        request_id=recommendation_request_id,
        generated_at=now,
        recommendations=adapter_result.recommendations,
        warnings=adapter_result.warnings,
    )
    score_breakdown = sanitize_score_breakdown(
        adapter_result.score_breakdown,
        payload.candidate_room_ids,
    )
    session.add(
        models.RecommendationRecord(
            request_id=recommendation_request_id,
            profile_id=profile.profile_id,
            user_id=auth.user.id,
            generated_at=now,
            candidate_room_ids_json=payload.candidate_room_ids,
            rankings_json=[item.model_dump(mode="json") for item in result.recommendations],
            score_breakdown_json=score_breakdown or None,
            explanation_source=(
                result.recommendations[0].explanation_source
                if result.recommendations
                else "template"
            ),
            adapter_name=adapter_result.adapter_name,
            fallback_reason=fallback_reason,
            latency_ms=latency_ms,
            warnings_json=result.warnings,
        )
    )
    session.commit()
    return result


async def _direct_selection_breakdowns(
    request: Request,
    session: Session,
    settings: Settings,
    profile: models.PreferenceProfile,
    learned: models.LearnedPreferenceProfile,
) -> tuple[dict[str, dict], dict[str, tuple[int, int]]]:
    now = utcnow()
    rooms = RoomRepository(session).list_active()
    payload = AuthenticatedRecommendationRequest(
        schema_version="1.0",
        study_mode=profile.study_mode,
        candidate_room_ids=[room.id for room in rooms],
    )
    effective = effective_snapshot(profile, learned)
    context = RecommendationContext(
        request=payload,
        rooms=[build_room_status(session, room, settings, now) for room in rooms],
        effective_preferences=as_recommendation_preferences(effective),
        preferred_temperature_c=effective.preferred_temperature_c,
    )
    try:
        adapter_result = await asyncio.wait_for(
            request.app.state.recommendation_adapter.rank(context),
            timeout=settings.recommendation_adapter_timeout_seconds,
        )
    except Exception:
        adapter_result = await StubRecommendationAdapter().rank(context)
    ranking = {
        item.room_id: (item.rank, item.score)
        for item in adapter_result.recommendations
    }
    return sanitize_score_breakdown(
        adapter_result.score_breakdown,
        [room.id for room in rooms],
    ), ranking


@router.post("/api/v1/me/room-selections", response_model=RoomSelectionAccepted)
async def record_room_selection(
    payload: RoomSelectionRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RoomSelectionAccepted:
    now = utcnow()
    auth = authenticate_request(request, session, now, require_csrf=True)
    payload_hash = _selection_hash(payload)
    selection_id = str(payload.selection_id)
    existing = session.get(models.RoomSelectionEvent, selection_id)
    profile, learned = _profile_and_learned(session, auth.user)
    if existing is not None:
        if existing.user_id != auth.user.id or not hmac.compare_digest(
            existing.payload_hash, payload_hash
        ):
            raise APIError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "selection_id already exists with a different payload",
            )
        session.commit()
        return RoomSelectionAccepted(
            selection_id=payload.selection_id,
            room_id=existing.room_id,
            recorded_at=existing.recorded_at,
            effective_preferences=effective_snapshot(profile, learned),
        )
    room = session.get(models.Room, payload.room_id)
    if room is None or not room.active:
        raise APIError(404, "ROOM_NOT_FOUND", "The selected room does not exist or is inactive")

    breakdowns: dict[str, dict]
    ranking: dict[str, tuple[int, int]]
    if payload.source == "recommendation":
        record = session.scalar(
            select(models.RecommendationRecord).where(
                models.RecommendationRecord.request_id
                == payload.recommendation_request_id
            )
        )
        if (
            record is None
            or record.user_id != auth.user.id
            or payload.room_id not in record.candidate_room_ids_json
        ):
            raise APIError(
                404,
                "RECOMMENDATION_NOT_FOUND",
                "The recommendation does not belong to this user or candidate set",
            )
        breakdowns = record.score_breakdown_json or {}
        ranking = {
            item["room_id"]: (int(item["rank"]), int(item["score"]))
            for item in record.rankings_json
        }
    else:
        breakdowns, ranking = await _direct_selection_breakdowns(
            request,
            session,
            settings,
            profile,
            learned,
        )

    evidence = selection_evidence(payload.room_id, breakdowns)
    selected_rank, selected_score = ranking.get(payload.room_id, (None, None))
    event = models.RoomSelectionEvent(
        selection_id=selection_id,
        payload_hash=payload_hash,
        user_id=auth.user.id,
        room_id=payload.room_id,
        recommendation_request_id=payload.recommendation_request_id,
        source=payload.source,
        recorded_at=now,
        selected_rank=selected_rank,
        selected_score=selected_score,
        evidence_json=evidence,
        context_summary_json=compact_context(breakdowns),
    )
    session.add(event)
    apply_evidence(learned, evidence, now)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        duplicate = session.get(models.RoomSelectionEvent, selection_id)
        if (
            duplicate is None
            or duplicate.user_id != auth.user.id
            or not hmac.compare_digest(duplicate.payload_hash, payload_hash)
        ):
            raise APIError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "selection_id already exists with a different payload",
            ) from exc
        profile, learned = _profile_and_learned(session, auth.user)
        return RoomSelectionAccepted(
            selection_id=payload.selection_id,
            room_id=duplicate.room_id,
            recorded_at=duplicate.recorded_at,
            effective_preferences=effective_snapshot(profile, learned),
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise APIError(500, "DATABASE_ERROR", "The room selection could not be stored") from exc
    return RoomSelectionAccepted(
        selection_id=payload.selection_id,
        room_id=payload.room_id,
        recorded_at=now,
        effective_preferences=effective_snapshot(profile, learned),
    )


@router.get("/api/v1/me/room-selections", response_model=RoomSelectionHistoryResponse)
def list_room_selections(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> RoomSelectionHistoryResponse:
    auth = authenticate_request(request, session, utcnow())
    offset = _decode_cursor(cursor)
    query = (
        select(models.RoomSelectionEvent, models.Room.name)
        .join(models.Room, models.Room.id == models.RoomSelectionEvent.room_id)
        .where(models.RoomSelectionEvent.user_id == auth.user.id)
        .order_by(
            models.RoomSelectionEvent.recorded_at.desc(),
            models.RoomSelectionEvent.selection_id.desc(),
        )
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list(session.execute(query))
    has_more = len(rows) > limit
    rows = rows[:limit]
    session.commit()
    return RoomSelectionHistoryResponse(
        selections=[
            RoomSelectionHistoryItem(
                selection_id=event.selection_id,
                room_id=event.room_id,
                room_name=room_name,
                source=event.source,
                recommendation_request_id=event.recommendation_request_id,
                recorded_at=event.recorded_at,
                selected_rank=event.selected_rank,
                selected_score=event.selected_score,
                evidence=event.evidence_json,
            )
            for event, room_name in rows
        ],
        next_cursor=_encode_cursor(offset + limit) if has_more else None,
    )


@router.delete("/api/v1/me/room-selections", response_model=DeleteResult)
def delete_room_selections(
    request: Request,
    session: Session = Depends(get_session),
) -> DeleteResult:
    now = utcnow()
    auth = authenticate_request(request, session, now, require_csrf=True)
    _, learned = _profile_and_learned(session, auth.user)
    result = session.execute(
        delete(models.RoomSelectionEvent).where(
            models.RoomSelectionEvent.user_id == auth.user.id
        )
    )
    reset_learned(learned, now)
    session.commit()
    return DeleteResult(deleted=True, deleted_count=int(result.rowcount or 0))
