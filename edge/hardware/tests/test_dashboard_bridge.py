from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from study_space_hardware.dashboard_bridge import (
    DashboardClient,
    LiveSnapshotBuilder,
    SensorDashboardBridge,
    count_hot_regions,
    normalize_thermal,
)
from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_hardware.models import (
    SensorHealth,
    SensorHealthReport,
    SensorSample,
)
from study_space_hardware.storage import SessionWriter


NOW = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"
REPOSITORY_ROOT = Path(__file__).parents[3]


class RecordingPublisher:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.previews_published = 0
        self.observations_published = 0
        self.failed = 0
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def submit(self, payload: dict) -> None:
        self.payloads.append(payload)
        self.previews_published += 1

    def close(self) -> None:
        self.closed = True


class NonThermalOrchestrator:
    def __init__(self) -> None:
        self.drivers = {"thermal": object(), "sound": object()}
        self.closed = False

    def run_window(self, *, on_sample) -> object:
        on_sample(_sample("sound", {"rms": 0.04, "peak": 0.12}))
        return type("Window", (), {"payload": {"quality": {"completeness": 0.5}}})()

    def health(self) -> dict[str, SensorHealthReport]:
        return {
            "thermal": SensorHealthReport(
                sensor="thermal",
                status=SensorHealth.OFFLINE,
                consecutive_failures=3,
                failed_reads=3,
                message="initialization failed",
                last_success_at=None,
            ),
            "sound": SensorHealthReport(
                sensor="sound",
                status=SensorHealth.OK,
                consecutive_failures=0,
                failed_reads=0,
                message=None,
                last_success_at=NOW,
            ),
        }

    def close(self) -> None:
        self.closed = True


def _sample(sensor: str, values: dict) -> SensorSample:
    return SensorSample(
        sensor=sensor,
        captured_at=NOW,
        monotonic_s=10.0,
        values=values,
        units={},
        source=f"test:{sensor}",
    )


def test_normalize_thermal_clips_and_preserves_shape() -> None:
    raw = [20.0 + index / 100 for index in range(768)]

    normalized = normalize_thermal(raw)

    assert len(normalized) == 768
    assert min(normalized) == 0.0
    assert max(normalized) == 1.0
    assert normalize_thermal([23.0] * 768) == [0.0] * 768
    with pytest.raises(ValueError, match="768"):
        normalize_thermal([20.0])


def test_hot_region_counter_uses_connected_components() -> None:
    values = [0.0] * 768
    values[33] = values[34] = values[35] = 0.9
    values[400] = values[432] = 0.8
    values[700] = 0.95

    assert count_hot_regions(values) == 2


def test_snapshot_builder_keeps_real_proxy_semantics() -> None:
    builder = LiveSnapshotBuilder(room_id="room_a", device_id="pi5-a")
    builder.accept(
        _sample(
            "thermal",
            {"width": 32, "height": 24, "temperatures_c": tuple(22 + index / 200 for index in range(768))},
        )
    )
    builder.accept(
        _sample(
            "sound",
            {
                "rms": 0.12,
                "peak": 0.31,
                "relative_level": 0.72,
                "raw_audio_persisted": False,
            },
        )
    )
    builder.accept(
        _sample(
            "light",
            {
                "light_adc_raw": 420,
                "light_normalized": 0.1026,
                "light_lux": None,
                "calibrated_lux": False,
                "warning": "hw486_uncalibrated_light_proxy",
            },
        )
    )
    builder.accept(
        _sample("climate", {"temperature_c": 23.6, "humidity_pct": 61.0})
    )
    reports = {
        name: SensorHealthReport(sensor=name, status=SensorHealth.OK)
        for name in ("thermal", "sound", "light", "climate")
    }

    bundle = builder.build(reports)
    preview = bundle["thermal_preview"]
    sound_preview = bundle["sound_preview"]
    observation = bundle["observation"]

    assert preview["captured_at"] == "2026-07-22T08:30:00.000Z"
    assert preview["width"] == 32
    assert len(preview["values"]) == 768
    assert sound_preview["captured_at"] == "2026-07-22T08:30:00.000Z"
    assert sound_preview["rms"] == 0.12
    assert sound_preview["expires_in_seconds"] == 3
    assert observation["room_state"] == "unknown"
    assert observation["occupancy_level"] == "unknown"
    assert observation["confidence"] == 0.0
    assert observation["features"]["sound_rms_mean"] == 0.12
    assert observation["features"]["sound_peak_max"] == 0.72
    assert observation["features"]["light_relative_mean"] == 0.1026
    assert observation["features"]["light_lux"] is None
    assert observation["sensor_health"]["radar"] == "not_configured"
    assert observation["model"]["name"] == "sensor-dashboard-bridge"
    assert "hw486_uncalibrated_light_proxy" in observation["warnings"]
    assert "DASHBOARD_ONLY_NO_MODULE2_INFERENCE" in observation["warnings"]

    schema = json.loads(
        (REPOSITORY_ROOT / "shared/contracts/edge_observation.schema.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(observation),
        key=lambda item: list(item.path),
    )
    assert not errors, [error.message for error in errors]


def test_snapshot_builder_expires_sound_peak_hold() -> None:
    builder = LiveSnapshotBuilder(
        room_id="room_a",
        device_id="pi5-a",
        sound_hold_seconds=10.0,
    )
    builder.accept(_sample("sound", {"rms": 0.02, "peak": 0.25}))
    builder.accept(
        replace(
            _sample(
                "thermal",
                {
                    "width": 32,
                    "height": 24,
                    "temperatures_c": (23.0,) * 768,
                },
            ),
            captured_at=NOW + timedelta(seconds=11),
        )
    )

    observation = builder.build({})["observation"]

    assert observation["features"]["sound_peak_max"] is None


def test_snapshot_builder_publishes_nonthermal_data_when_thermal_is_offline() -> None:
    builder = LiveSnapshotBuilder(room_id="room_a", device_id="pi5-a")
    builder.accept(_sample("sound", {"rms": 0.04, "peak": 0.12}))
    reports = NonThermalOrchestrator().health()

    payload = builder.build(reports)

    assert payload["thermal_preview"] is None
    assert payload["sound_preview"]["rms"] == 0.04
    assert payload["observation"]["features"]["thermal_hot_region_count"] is None
    assert payload["observation"]["features"]["sound_rms_mean"] == 0.04
    assert payload["observation"]["sensor_health"]["thermal"] == "offline"


def test_bridge_submits_window_without_a_thermal_frame() -> None:
    orchestrator = NonThermalOrchestrator()
    publisher = RecordingPublisher()
    bridge = SensorDashboardBridge(
        orchestrator=orchestrator,  # type: ignore[arg-type]
        builder=LiveSnapshotBuilder(room_id="room_a", device_id="pi5-a"),
        publisher=publisher,  # type: ignore[arg-type]
    )

    completed = bridge.run(window_count=1)

    assert completed == 1
    assert publisher.payloads[0]["thermal_preview"] is None
    assert publisher.payloads[0]["observation"]["features"]["sound_rms_mean"] == 0.04
    assert orchestrator.closed is True


def test_dashboard_client_requires_absolute_http_url() -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        DashboardClient(backend_url="localhost:8000", room_id="room_a")


def test_one_process_streams_and_writes_the_same_sensor_window(tmp_path: Path) -> None:
    config = load_config(EXAMPLE_CONFIG)
    config = replace(
        config,
        storage=replace(config.storage, data_dir=str(tmp_path / "sessions")),
    )
    clock = ManualClock()
    orchestrator = build_orchestrator(config, clock=clock)
    publisher = RecordingPublisher()
    writer = SessionWriter(
        config=config,
        scenario="unlabeled_relative_training",
        now=clock.now_utc(),
    )
    bridge = SensorDashboardBridge(
        orchestrator=orchestrator,
        builder=LiveSnapshotBuilder(
            room_id=config.room_id,
            device_id=config.device_id,
        ),
        publisher=publisher,  # type: ignore[arg-type]
    )

    completed = bridge.run(writer=writer, window_count=1)
    session_path = writer.finalize(clock.now_utc())

    assert completed == writer.window_count == 1
    assert publisher.started is True
    assert publisher.closed is True
    assert publisher.payloads
    assert (session_path / "windows.jsonl").is_file()
    assert (session_path / "relative_features.jsonl").is_file()
