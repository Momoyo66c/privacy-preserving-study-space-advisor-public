from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_hardware.models import SensorHealth, SensorHealthReport, SensorSample
from study_space_hardware.windowing import WindowAccumulator


REPOSITORY_ROOT = Path(__file__).parents[3]
EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"


def _window(scenario: str):
    config = load_config(EXAMPLE_CONFIG)
    config = replace(
        config,
        simulator=replace(config.simulator, scenario=scenario),
    )
    orchestrator = build_orchestrator(config, clock=ManualClock())
    try:
        return orchestrator.run_window()
    finally:
        orchestrator.close()


def test_simulator_is_reproducible_for_fixed_seed() -> None:
    first = _window("quiet_study_recommended")
    second = _window("quiet_study_recommended")
    assert first.payload == second.payload
    assert first.thermal_frames == second.thermal_frames


def test_window_counts_and_contract_shape() -> None:
    window = _window("quiet_study_recommended")
    assert window.payload["schema_version"] == "1.0"
    assert window.payload["thermal"]["frame_count"] == 10
    assert window.payload["radar"]["sample_count"] == 50
    assert window.payload["quality"] == {"completeness": 1.0, "warnings": []}
    first_target = window.payload["radar"]["tracks"][0]["targets"][0]
    assert first_target["target_id"].startswith("target-")
    assert len(window.thermal_frames) == 10
    assert len(window.thermal_frames[0]) == 768


def test_generated_normal_and_degraded_windows_match_shared_schema() -> None:
    schema = json.loads(
        (REPOSITORY_ROOT / "shared/contracts/sensor_window.schema.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for scenario in ("quiet_study_recommended", "degraded_thermal"):
        errors = list(validator.iter_errors(_window(scenario).payload))
        assert not errors, [error.message for error in errors]


def test_thermal_offline_degrades_without_crashing() -> None:
    window = _window("degraded_thermal")
    assert window.payload["thermal"]["health"] == "offline"
    assert window.payload["thermal"]["frame_count"] == 0
    assert window.payload["radar"]["sample_count"] == 50
    assert window.payload["quality"]["completeness"] < 1
    assert "thermal:offline" in window.payload["quality"]["warnings"]


def test_thermal_offline_without_configured_radar_blocks_inference() -> None:
    start = datetime(2026, 7, 22, 6, 45, tzinfo=timezone.utc)
    accumulator = WindowAccumulator(
        room_id="room_a",
        device_id="pi5-a",
        window_start=start,
        window_end=start + timedelta(seconds=5),
        start_monotonic_s=0.0,
        expected_counts={"thermal": 10},
    )
    window = accumulator.finalize(
        {
            "thermal": SensorHealthReport(
                sensor="thermal",
                status=SensorHealth.OFFLINE,
            )
        }
    )

    assert window.payload["radar"] == {
        "health": "not_configured",
        "sample_count": 0,
        "tracks": [],
    }
    assert (
        "not_inference_ready:thermal_offline_without_radar"
        in window.payload["quality"]["warnings"]
    )


def test_unscaled_light_and_sound_are_retained_for_training() -> None:
    start = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    accumulator = WindowAccumulator(
        room_id="room_a",
        device_id="pi5-a",
        window_start=start,
        window_end=start + timedelta(seconds=5),
        start_monotonic_s=0.0,
        expected_counts={"light": 1, "sound": 1},
    )
    accumulator.add(
        SensorSample(
            sensor="light",
            captured_at=start,
            monotonic_s=0.0,
            values={
                "light_adc_raw": 420,
                "light_normalized": 0.1026,
                "light_lux": None,
                "calibrated_lux": False,
            },
            units={},
        )
    )
    accumulator.add(
        SensorSample(
            sensor="sound",
            captured_at=start,
            monotonic_s=0.0,
            values={"rms": 0.12, "peak": 0.31},
            units={},
        )
    )
    reports = {
        name: SensorHealthReport(sensor=name, status=SensorHealth.OK)
        for name in ("light", "sound")
    }

    window = accumulator.finalize(reports)

    assert window.payload["environment"]["light_lux"] is None
    assert window.relative_features["light"]["adc"]["mean"] == 420
    assert window.relative_features["light"]["normalized"]["mean"] == 0.1026
    assert window.relative_features["sound"]["rms"]["mean"] == 0.12
    assert window.relative_features["sound"]["calibrated_db"] is False


def test_target_namespace_changes_at_window_boundary() -> None:
    config = load_config(EXAMPLE_CONFIG)
    orchestrator = build_orchestrator(config, clock=ManualClock())
    try:
        first = orchestrator.run_window()
        second = orchestrator.run_window()
    finally:
        orchestrator.close()
    first_id = first.payload["radar"]["tracks"][0]["targets"][0]["target_id"]
    second_id = second.payload["radar"]["tracks"][0]["targets"][0]["target_id"]
    assert first_id != second_id
