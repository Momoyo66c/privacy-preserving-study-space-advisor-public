from __future__ import annotations

import copy
import http.client
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from study_space_hardware.clock import ManualClock
from study_space_hardware.drivers.remote_sound import (
    REMOTE_SOUND_PATH,
    RemoteSoundFeatureDriver,
    RemoteSoundRequestError,
    relative_microphone_level,
)
from study_space_hardware.models import SensorHealth
from study_space_hardware.remote_sound_agent import (
    build_feature_payload,
    post_feature,
    summarize_feature_rows,
)


TOKEN = "test-token-that-is-longer-than-24-characters"


def _payload(
    clock: ManualClock,
    *,
    sample_id: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "sample_id": sample_id or str(uuid4()),
        "device_id": "windows-laptop-mic",
        "room_id": "room_a",
        "captured_at": (
            clock.now_utc()
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        ),
        "window_ms": 1000,
        "rms": 0.2,
        "std": 0.1,
        "peak": 0.6,
        "calibrated_db": False,
        "raw_audio_persisted": False,
    }


def _driver(clock: ManualClock, **overrides: object) -> RemoteSoundFeatureDriver:
    arguments: dict[str, object] = {
        "room_id": "room_a",
        "expected_device_id": "windows-laptop-mic",
        "bearer_token": TOKEN,
        "listen_port": 0,
        "clock": clock,
    }
    arguments.update(overrides)
    return RemoteSoundFeatureDriver(**arguments)


def _http_post(
    driver: RemoteSoundFeatureDriver,
    payload: dict[str, object],
    *,
    token: str = TOKEN,
) -> tuple[int, dict[str, object]]:
    assert driver.bound_port is not None
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        driver.bound_port,
        timeout=2,
    )
    body = json.dumps(payload, separators=(",", ":"))
    connection.request(
        "POST",
        REMOTE_SOUND_PATH,
        body=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    result = json.loads(response.read())
    connection.close()
    return response.status, result


def test_remote_summary_becomes_sound_sample_and_contains_no_audio(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    clock = ManualClock()
    driver = _driver(clock)
    driver.start()
    try:
        accepted, duplicate = driver.accept_feature(_payload(clock))
        assert accepted is True
        assert duplicate is False
        assert driver.sample_available() is True

        sample = driver.read()

        assert sample.values == {
            "rms": relative_microphone_level(0.2),
            "std": 0.1,
            "peak": relative_microphone_level(0.6),
            "relative_level": relative_microphone_level(0.6),
            "rms_sensor_normalized": 0.2,
            "peak_sensor_normalized": 0.6,
            "window_ms": 1000,
            "calibrated_db": False,
            "raw_audio_persisted": False,
            "sensor_model": "Windows microphone",
        }
        assert sample.source == "remote-feature:windows-microphone"
        assert driver.sample_available() is False
        assert driver.health().status is SensorHealth.OK
        assert list(tmp_path.iterdir()) == []
    finally:
        driver.close()


def test_http_receiver_requires_auth_and_is_idempotent() -> None:
    clock = ManualClock()
    driver = _driver(clock)
    driver.start()
    try:
        payload = _payload(clock)
        status, result = _http_post(driver, payload, token="wrong-token")
        assert status == 401
        assert result["error"] == "UNAUTHORIZED"

        status, result = _http_post(driver, payload)
        assert status == 202
        assert result["accepted"] is True
        assert result["duplicate"] is False

        status, result = _http_post(driver, payload)
        assert status == 200
        assert result["duplicate"] is True

        changed = copy.deepcopy(payload)
        changed["rms"] = 0.3
        status, result = _http_post(driver, changed)
        assert status == 409
        assert result["error"] == "IDEMPOTENCY_CONFLICT"
    finally:
        driver.close()


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"raw_audio_persisted": True}, "PRIVACY_VIOLATION"),
        ({"calibrated_db": True}, "INVALID_CALIBRATION"),
        ({"room_id": "room_b"}, "SOURCE_MISMATCH"),
        ({"device_id": "somebody-else"}, "SOURCE_MISMATCH"),
        ({"peak": 0.1, "rms": 0.2}, "INVALID_FEATURE_RELATION"),
        ({"rms": float("nan")}, "INVALID_FEATURE"),
        ({"samples": [0.1, 0.2]}, "INVALID_FIELDS"),
    ],
)
def test_remote_payload_rejects_unsafe_or_invalid_data(
    change: dict[str, object],
    code: str,
) -> None:
    clock = ManualClock()
    driver = _driver(clock)
    payload = _payload(clock)
    payload.update(change)

    with pytest.raises(RemoteSoundRequestError) as raised:
        driver.accept_feature(payload)

    assert raised.value.code == code


def test_stale_and_future_features_are_rejected() -> None:
    clock = ManualClock()
    driver = _driver(clock)
    stale = _payload(clock)
    stale["captured_at"] = "2026-07-15T23:59:50.000Z"
    with pytest.raises(RemoteSoundRequestError) as raised:
        driver.accept_feature(stale)
    assert raised.value.code == "STALE_FEATURE"

    future = _payload(clock)
    future["captured_at"] = "2026-07-16T00:00:03.000Z"
    with pytest.raises(RemoteSoundRequestError) as raised:
        driver.accept_feature(future)
    assert raised.value.code == "FUTURE_FEATURE"


def test_health_degrades_then_goes_offline_when_windows_agent_stops() -> None:
    clock = ManualClock()
    driver = _driver(
        clock,
        max_feature_age_s=4,
        offline_after_s=8,
    )
    driver.start()
    try:
        driver.accept_feature(_payload(clock))
        driver.read()
        assert driver.health().status is SensorHealth.OK

        clock.advance(5)
        assert driver.health().status is SensorHealth.DEGRADED
        assert driver.sample_available() is False

        clock.advance(4)
        assert driver.health().status is SensorHealth.OFFLINE
    finally:
        driver.close()


def test_listener_refuses_non_loopback_binding() -> None:
    with pytest.raises(ValueError, match="loopback"):
        RemoteSoundFeatureDriver(
            room_id="room_a",
            expected_device_id="windows-laptop-mic",
            bearer_token=TOKEN,
            listen_host="0.0.0.0",
        )


def test_windows_agent_builds_and_posts_only_summary_fields() -> None:
    clock = ManualClock(datetime.now(timezone.utc))
    driver = _driver(clock)
    driver.start()
    try:
        payload = build_feature_payload(
            [0.1, -0.1, 0.2, -0.2],
            room_id="room_a",
            device_id="windows-laptop-mic",
            window_ms=1000,
            captured_at=(
                clock.now_utc()
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            ),
        )
        assert set(payload) == {
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
        assert all(
            forbidden not in json.dumps(payload).lower()
            for forbidden in ("pcm", "waveform", "samples")
        )

        result = post_feature(
            f"http://127.0.0.1:{driver.bound_port}{REMOTE_SOUND_PATH}",
            TOKEN,
            payload,
        )

        assert result["accepted"] is True
        assert driver.read().values["raw_audio_persisted"] is False
    finally:
        driver.close()


def test_diagnostic_summary_keeps_only_aggregate_features() -> None:
    summary = summarize_feature_rows(
        [
            {"rms": 0.01, "std": 0.02, "peak": 0.1},
            {"rms": 0.02, "std": 0.03, "peak": 0.2},
            {"rms": 0.03, "std": 0.04, "peak": 0.3},
        ]
    )

    assert set(summary) == {"rms", "std", "peak"}
    assert summary["rms"]["median"] == 0.02
    assert summary["peak"]["maximum"] == 0.3
