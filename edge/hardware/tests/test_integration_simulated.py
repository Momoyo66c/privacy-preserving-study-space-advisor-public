from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_hardware.drivers.base import BaseSensorDriver, SensorStartError
from study_space_hardware.models import SampleQuality, SensorSample
from study_space_hardware.orchestrator import SensorOrchestrator


EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"


class RecoveringStartDriver(BaseSensorDriver):
    def __init__(self, clock: ManualClock) -> None:
        super().__init__(
            "light",
            sample_rate_hz=1,
            max_retries=0,
            offline_threshold=1,
            clock=clock,
        )
        self.start_attempts = 0

    def _start(self) -> None:
        self.start_attempts += 1
        if self.start_attempts == 1:
            raise SensorStartError("temporarily unavailable")

    def _read(self) -> SensorSample:
        return SensorSample(
            sensor="light",
            captured_at=self.clock.now_utc(),
            monotonic_s=self.clock.monotonic(),
            values={"light_lux": 300.0},
            units={"light_lux": "lux"},
            quality=SampleQuality.VALID,
            source="test",
        )


def test_two_virtual_minutes_run_without_unhandled_exception() -> None:
    config = load_config(EXAMPLE_CONFIG)
    clock = ManualClock()
    orchestrator = build_orchestrator(config, clock=clock)
    try:
        windows = [orchestrator.run_window() for _ in range(24)]
    finally:
        orchestrator.close()
    assert len(windows) == 24
    assert clock.monotonic() >= 120
    assert all(window.payload["quality"]["completeness"] == 1 for window in windows)


def test_single_offline_sensor_still_emits_windows() -> None:
    config = load_config(EXAMPLE_CONFIG)
    config = replace(
        config,
        simulator=replace(config.simulator, scenario="degraded_radar"),
    )
    orchestrator = build_orchestrator(config, clock=ManualClock())
    try:
        windows = [orchestrator.run_window() for _ in range(3)]
    finally:
        orchestrator.close()
    assert all(window.payload["radar"]["health"] == "offline" for window in windows)
    assert all(window.payload["thermal"]["frame_count"] == 10 for window in windows)


def test_failed_start_is_retried_on_next_window() -> None:
    clock = ManualClock()
    driver = RecoveringStartDriver(clock)
    orchestrator = SensorOrchestrator(
        room_id="room_a",
        device_id="test-device",
        window_seconds=5,
        drivers={"light": driver},
        clock=clock,
    )
    try:
        first = orchestrator.run_window()
        second = orchestrator.run_window()
    finally:
        orchestrator.close()

    assert first.payload["environment"]["light_lux"] is None
    assert second.payload["environment"]["light_lux"] == 300.0
    assert driver.start_attempts == 2
