"""Loopback-only receiver for privacy-safe remote sound summaries.

The receiver accepts only bounded RMS/std/peak features.  It never accepts,
stores, logs, or returns raw audio.  In production the HTTP listener remains
on Raspberry Pi loopback and is reached from the Windows microphone agent via
an SSH local-forward tunnel.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from uuid import UUID

from .base import BaseSensorDriver, SensorReadError, SensorStartError
from ..clock import Clock
from ..models import (
    SampleQuality,
    SensorHealth,
    SensorHealthReport,
    SensorSample,
    ensure_utc,
)


REMOTE_SOUND_PATH = "/v1/sound-features"
REMOTE_SOUND_SCHEMA_VERSION = "1.0"
_RELATIVE_CURVE_GAIN = 200.0
_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "sample_id",
        "device_id",
        "room_id",
        "captured_at",
        "window_ms",
        "rms",
        "std",
        "peak",
        "calibrated_db",
        "raw_audio_persisted",
    }
)


class RemoteSoundRequestError(ValueError):
    """A sanitized request failure suitable for a small JSON response."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class RemoteSoundFeature:
    sample_id: str
    device_id: str
    room_id: str
    captured_at: datetime
    window_ms: int
    rms: float
    std: float
    peak: float
    payload_hash: str
    received_monotonic_s: float


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RemoteSoundRequestError(
            400,
            "INVALID_TIMESTAMP",
            "captured_at must be a UTC ISO 8601 timestamp ending in Z",
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RemoteSoundRequestError(
            400,
            "INVALID_TIMESTAMP",
            "captured_at must be a valid UTC ISO 8601 timestamp",
        ) from exc
    return ensure_utc(parsed)


def _bounded_feature(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RemoteSoundRequestError(
            400,
            "INVALID_FEATURE",
            f"{name} must be a finite number from 0 to 1",
        )
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise RemoteSoundRequestError(
            400,
            "INVALID_FEATURE",
            f"{name} must be a finite number from 0 to 1",
        )
    return normalized


def relative_microphone_level(value: float) -> float:
    """Map normalized microphone amplitude to a visible relative 0..1 level."""

    bounded = _bounded_feature(value, "microphone amplitude")
    return math.log1p(_RELATIVE_CURVE_GAIN * bounded) / math.log1p(
        _RELATIVE_CURVE_GAIN
    )


def _ascii_identifier(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or not value.isascii()
    ):
        raise RemoteSoundRequestError(
            400,
            "INVALID_IDENTIFIER",
            f"{name} must be a non-empty ASCII string up to 128 characters",
        )
    return value


class RemoteSoundFeatureDriver(BaseSensorDriver):
    """Receive Windows microphone summaries and expose them as a sound driver."""

    def __init__(
        self,
        *,
        room_id: str,
        expected_device_id: str,
        bearer_token: str,
        listen_host: str = "127.0.0.1",
        listen_port: int = 8766,
        sample_rate_hz: float = 1.0,
        max_feature_age_s: float = 4.0,
        max_future_skew_s: float = 2.0,
        offline_after_s: float = 8.0,
        max_body_bytes: int = 4096,
        replay_cache_size: int = 128,
        max_retries: int = 0,
        offline_threshold: int = 1,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "sound",
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        try:
            is_loopback = ipaddress.ip_address(listen_host).is_loopback
        except ValueError as exc:
            raise ValueError("remote sound listen_host must be a loopback IP") from exc
        if not is_loopback:
            raise ValueError("remote sound listener must bind to a loopback IP")
        if not 0 <= int(listen_port) <= 65_535:
            raise ValueError("remote sound listen_port must be between 0 and 65535")
        if len(bearer_token) < 24 or any(char.isspace() for char in bearer_token):
            raise ValueError(
                "remote sound bearer token must contain at least 24 non-space characters"
            )
        if max_feature_age_s <= 0:
            raise ValueError("max_feature_age_s must be positive")
        if max_future_skew_s < 0:
            raise ValueError("max_future_skew_s cannot be negative")
        if offline_after_s < max_feature_age_s:
            raise ValueError("offline_after_s must be at least max_feature_age_s")
        if not 512 <= max_body_bytes <= 65_536:
            raise ValueError("max_body_bytes must be between 512 and 65536")
        if replay_cache_size < 1:
            raise ValueError("replay_cache_size must be positive")

        self.room_id = _ascii_identifier(room_id, "room_id")
        self.expected_device_id = _ascii_identifier(
            expected_device_id,
            "expected_device_id",
        )
        self._bearer_token = bearer_token
        self.listen_host = listen_host
        self.listen_port = int(listen_port)
        self.max_feature_age_s = float(max_feature_age_s)
        self.max_future_skew_s = float(max_future_skew_s)
        self.offline_after_s = float(offline_after_s)
        self.max_body_bytes = int(max_body_bytes)
        self.replay_cache_size = int(replay_cache_size)
        self.raw_audio_persisted = False

        self._lock = threading.Lock()
        self._latest: RemoteSoundFeature | None = None
        self._latest_consumed = True
        self._seen_hashes: OrderedDict[str, str] = OrderedDict()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started_monotonic_s: float | None = None
        self._accepted_count = 0
        self._duplicate_count = 0
        self._rejected_count = 0

    @property
    def bound_port(self) -> int | None:
        server = self._server
        return int(server.server_address[1]) if server is not None else None

    def _start(self) -> None:
        driver = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PssaRemoteSound/1.0"
            sys_version = ""

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                driver._handle_post(self)

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                driver._write_json(
                    self,
                    404,
                    {"accepted": False, "error": "NOT_FOUND"},
                )

            def log_message(self, _format: str, *args: object) -> None:
                # Never allow the HTTP server to log headers or feature bodies.
                return

        try:
            self._server = ThreadingHTTPServer(
                (self.listen_host, self.listen_port),
                Handler,
            )
        except OSError as exc:
            raise SensorStartError(
                f"remote sound listener failed to bind: {type(exc).__name__}"
            ) from exc
        self._server.daemon_threads = True
        self._started_monotonic_s = self.clock.monotonic()
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="remote-sound-feature-receiver",
            daemon=True,
        )
        self._thread.start()

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            if handler.path != REMOTE_SOUND_PATH:
                raise RemoteSoundRequestError(404, "NOT_FOUND", "endpoint not found")
            supplied = handler.headers.get("Authorization", "")
            expected = f"Bearer {self._bearer_token}"
            if not hmac.compare_digest(supplied, expected):
                raise RemoteSoundRequestError(
                    401,
                    "UNAUTHORIZED",
                    "valid bearer authentication is required",
                )
            content_type = handler.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type.strip().lower() != "application/json":
                raise RemoteSoundRequestError(
                    415,
                    "UNSUPPORTED_MEDIA_TYPE",
                    "Content-Type must be application/json",
                )
            try:
                content_length = int(handler.headers.get("Content-Length", ""))
            except ValueError as exc:
                raise RemoteSoundRequestError(
                    400,
                    "INVALID_LENGTH",
                    "Content-Length must be an integer",
                ) from exc
            if content_length < 2 or content_length > self.max_body_bytes:
                raise RemoteSoundRequestError(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    "request body size is outside the accepted range",
                )
            body = handler.rfile.read(content_length)
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RemoteSoundRequestError(
                    400,
                    "INVALID_JSON",
                    "request body must be valid JSON",
                ) from exc
            if not isinstance(payload, dict):
                raise RemoteSoundRequestError(
                    400,
                    "INVALID_PAYLOAD",
                    "request body must be a JSON object",
                )
            accepted, duplicate = self.accept_feature(payload)
            self._write_json(
                handler,
                200 if duplicate else 202,
                {
                    "accepted": accepted,
                    "duplicate": duplicate,
                    "sample_id": payload["sample_id"],
                },
            )
        except RemoteSoundRequestError as exc:
            with self._lock:
                self._rejected_count += 1
            self._write_json(
                handler,
                exc.status,
                {"accepted": False, "error": exc.code, "message": exc.message},
            )

    @staticmethod
    def _write_json(
        handler: BaseHTTPRequestHandler,
        status: int,
        payload: Mapping[str, Any],
    ) -> None:
        body = json.dumps(
            dict(payload),
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)

    def accept_feature(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[bool, bool]:
        """Validate and store one summary. Returns ``(accepted, duplicate)``."""

        if set(payload) != _REQUIRED_FIELDS:
            raise RemoteSoundRequestError(
                400,
                "INVALID_FIELDS",
                "payload fields do not match the remote sound summary contract",
            )
        if payload["schema_version"] != REMOTE_SOUND_SCHEMA_VERSION:
            raise RemoteSoundRequestError(
                400,
                "INVALID_SCHEMA_VERSION",
                "schema_version must be 1.0",
            )
        sample_id = _ascii_identifier(payload["sample_id"], "sample_id")
        try:
            UUID(sample_id)
        except ValueError as exc:
            raise RemoteSoundRequestError(
                400,
                "INVALID_SAMPLE_ID",
                "sample_id must be a UUID",
            ) from exc
        device_id = _ascii_identifier(payload["device_id"], "device_id")
        room_id = _ascii_identifier(payload["room_id"], "room_id")
        if device_id != self.expected_device_id or room_id != self.room_id:
            raise RemoteSoundRequestError(
                409,
                "SOURCE_MISMATCH",
                "room_id or device_id does not match this receiver",
            )
        if payload["calibrated_db"] is not False:
            raise RemoteSoundRequestError(
                400,
                "INVALID_CALIBRATION",
                "calibrated_db must be false for relative microphone features",
            )
        if payload["raw_audio_persisted"] is not False:
            raise RemoteSoundRequestError(
                400,
                "PRIVACY_VIOLATION",
                "raw_audio_persisted must be false",
            )
        window_ms = payload["window_ms"]
        if (
            isinstance(window_ms, bool)
            or not isinstance(window_ms, int)
            or not 100 <= window_ms <= 2_000
        ):
            raise RemoteSoundRequestError(
                400,
                "INVALID_WINDOW",
                "window_ms must be an integer from 100 to 2000",
            )
        captured_at = _parse_utc(payload["captured_at"])
        now = ensure_utc(self.clock.now_utc())
        age_s = (now - captured_at).total_seconds()
        if age_s > self.max_feature_age_s:
            raise RemoteSoundRequestError(
                409,
                "STALE_FEATURE",
                "sound summary is older than the configured freshness limit",
            )
        if age_s < -self.max_future_skew_s:
            raise RemoteSoundRequestError(
                409,
                "FUTURE_FEATURE",
                "sound summary timestamp is too far in the future",
            )
        rms = _bounded_feature(payload["rms"], "rms")
        std = _bounded_feature(payload["std"], "std")
        peak = _bounded_feature(payload["peak"], "peak")
        if peak + 1e-12 < rms:
            raise RemoteSoundRequestError(
                400,
                "INVALID_FEATURE_RELATION",
                "peak must be greater than or equal to rms",
            )

        canonical = json.dumps(
            dict(payload),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        payload_hash = hashlib.sha256(canonical).hexdigest()
        with self._lock:
            previous_hash = self._seen_hashes.get(sample_id)
            if previous_hash is not None:
                if not hmac.compare_digest(previous_hash, payload_hash):
                    raise RemoteSoundRequestError(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "sample_id was already used with a different payload",
                    )
                self._duplicate_count += 1
                return True, True
            self._seen_hashes[sample_id] = payload_hash
            self._seen_hashes.move_to_end(sample_id)
            while len(self._seen_hashes) > self.replay_cache_size:
                self._seen_hashes.popitem(last=False)
            self._latest = RemoteSoundFeature(
                sample_id=sample_id,
                device_id=device_id,
                room_id=room_id,
                captured_at=captured_at,
                window_ms=window_ms,
                rms=rms,
                std=std,
                peak=peak,
                payload_hash=payload_hash,
                received_monotonic_s=self.clock.monotonic(),
            )
            self._latest_consumed = False
            self._accepted_count += 1
        return True, False

    def sample_available(self) -> bool:
        with self._lock:
            feature = self._latest
            if feature is None or self._latest_consumed:
                return False
            return (
                self.clock.monotonic() - feature.received_monotonic_s
                <= self.max_feature_age_s
            )

    def _read(self) -> SensorSample:
        with self._lock:
            feature = self._latest
            if feature is None or self._latest_consumed:
                raise SensorReadError("no new remote sound summary is available")
            age_s = self.clock.monotonic() - feature.received_monotonic_s
            if age_s > self.max_feature_age_s:
                self._latest_consumed = True
                raise SensorReadError("latest remote sound summary is stale")
            self._latest_consumed = True
        output_rms = relative_microphone_level(feature.rms)
        output_peak = relative_microphone_level(feature.peak)
        return SensorSample(
            sensor=self.name,
            captured_at=feature.captured_at,
            monotonic_s=self.clock.monotonic(),
            values={
                "rms": output_rms,
                "std": feature.std,
                "peak": output_peak,
                "relative_level": output_peak,
                "rms_sensor_normalized": feature.rms,
                "peak_sensor_normalized": feature.peak,
                "window_ms": feature.window_ms,
                "calibrated_db": False,
                "raw_audio_persisted": False,
                "sensor_model": "Windows microphone",
            },
            units={
                "rms": "relative_logarithmic",
                "std": "normalized",
                "peak": "relative_logarithmic",
                "relative_level": "relative_logarithmic",
                "rms_sensor_normalized": "sensor_normalized",
                "peak_sensor_normalized": "sensor_normalized",
                "window_ms": "milliseconds",
            },
            quality=SampleQuality.VALID,
            warnings=(
                "windows_microphone_relative_only",
                "sound_not_calibrated_db",
                "windows_microphone_uncalibrated_relative_log_curve",
            ),
            source="remote-feature:windows-microphone",
        )

    def health(self) -> SensorHealthReport:
        report = super().health()
        with self._lock:
            latest = self._latest
            accepted = self._accepted_count
            duplicates = self._duplicate_count
            rejected = self._rejected_count
        details = {
            **dict(report.details),
            "transport": "loopback_http_over_ssh",
            "raw_audio_persisted": False,
            "accepted_features": accepted,
            "duplicate_features": duplicates,
            "rejected_requests": rejected,
        }
        if latest is None:
            return SensorHealthReport(
                sensor=report.sensor,
                status=SensorHealth.DEGRADED,
                successful_reads=report.successful_reads,
                failed_reads=report.failed_reads,
                consecutive_failures=report.consecutive_failures,
                last_success_at=report.last_success_at,
                message="waiting for first remote sound summary",
                details=details,
            )
        age_s = max(0.0, self.clock.monotonic() - latest.received_monotonic_s)
        details["latest_feature_age_s"] = round(age_s, 3)
        if age_s > self.offline_after_s:
            status = SensorHealth.OFFLINE
            message = "remote sound source is offline"
        elif age_s > self.max_feature_age_s:
            status = SensorHealth.DEGRADED
            message = "latest remote sound summary is stale"
        else:
            status = report.status
            message = report.message
        return SensorHealthReport(
            sensor=report.sensor,
            status=status,
            successful_reads=report.successful_reads,
            failed_reads=report.failed_reads,
            consecutive_failures=report.consecutive_failures,
            last_success_at=report.last_success_at,
            message=message,
            details=details,
        )

    def _close(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)
