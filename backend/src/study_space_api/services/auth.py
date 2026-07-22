from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings
from ..errors import APIError

SESSION_COOKIE = "pssa_session"
CSRF_COOKIE = "pssa_csrf"
PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1, hash_len=32, salt_len=16)


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@dataclass(slots=True)
class IssuedSession:
    model: models.UserSession
    token: str
    csrf_token: str


@dataclass(slots=True)
class AuthContext:
    user: models.User
    session: models.UserSession


def issue_session(
    session: Session,
    user: models.User,
    now: datetime,
    settings: Settings,
) -> IssuedSession:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    model = models.UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=secret_hash(token),
        csrf_hash=secret_hash(csrf_token),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        revoked_at=None,
        last_seen_at=now,
    )
    session.add(model)
    return IssuedSession(model=model, token=token, csrf_token=csrf_token)


def authenticate_request(
    request: Request,
    database_session: Session,
    now: datetime,
    *,
    require_csrf: bool = False,
) -> AuthContext:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise APIError(401, "AUTHENTICATION_REQUIRED", "Login is required")
    user_session = database_session.scalar(
        select(models.UserSession).where(models.UserSession.token_hash == secret_hash(raw_token))
    )
    if (
        user_session is None
        or user_session.revoked_at is not None
        or user_session.expires_at <= now
    ):
        raise APIError(401, "SESSION_INVALID", "The session is invalid or expired")
    user = database_session.get(models.User, user_session.user_id)
    if user is None or not user.active:
        raise APIError(401, "SESSION_INVALID", "The session is invalid or expired")
    if require_csrf:
        header_token = request.headers.get("x-csrf-token", "")
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        if (
            not header_token
            or not cookie_token
            or not hmac.compare_digest(header_token, cookie_token)
            or not hmac.compare_digest(secret_hash(header_token), user_session.csrf_hash)
        ):
            raise APIError(403, "CSRF_VALIDATION_FAILED", "A valid CSRF token is required")
    user_session.last_seen_at = now
    return AuthContext(user=user, session=user_session)


class LoginAttemptLimiter:
    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window = timedelta(seconds=window_seconds)
        self._failures: dict[str, deque[datetime]] = defaultdict(deque)

    def _key(self, username: str, ip: str) -> str:
        return f"{ip}:{username}"

    def check(self, username: str, ip: str, now: datetime) -> None:
        key = self._key(username, ip)
        failures = self._failures[key]
        cutoff = now - self.window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if len(failures) >= self.max_failures:
            raise APIError(429, "LOGIN_RATE_LIMITED", "Too many login attempts; try again later")

    def record_failure(self, username: str, ip: str, now: datetime) -> None:
        self._failures[self._key(username, ip)].append(now)

    def reset(self, username: str, ip: str) -> None:
        self._failures.pop(self._key(username, ip), None)
