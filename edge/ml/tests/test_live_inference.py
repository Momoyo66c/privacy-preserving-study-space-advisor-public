from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator, FormatChecker
import numpy as np

from study_space_ml.live_inference import (
    LiveInferenceProcessor,
    ThermalForegroundCounter,
    fuse_room_state,
)


ROOT = Path(__file__).resolve().parents[3]


class FakePredictor:
    metadata = {"target_max": 2.0}

    def predict_window(self, payload, **kwargs):
        assert len(kwargs["thermal_frames"]) == 2
        assert kwargs["include_features"] is True
        return {
            "prediction_id": "6f52d8e18f1a8e98c4de12ab90",
            "predicted_people_count": 1.08,
            "predicted_people_count_rounded": 1,
            "occupancy_level": "low",
            "confidence": 0.81,
            "model": {
                "name": "people-count-random-forest",
                "version": "0.2.0",
                "feature_schema_version": (
                    "people-count-features-v2-static-heat-motion"
                ),
            },
            "warnings": [],
            "features": {
                "thermal_available": 1.0,
                "thermal_hot_region_count": 1.0,
                "thermal_heat_delta_p95_median": 4.4,
                "window_seconds_actual": 5.0,
            },
        }


class EmptyDeadbandPredictor(FakePredictor):
    def predict_window(self, payload, **kwargs):
        result = super().predict_window(payload, **kwargs)
        result["predicted_people_count"] = 0.68
        result["predicted_people_count_rounded"] = 1
        result["occupancy_level"] = "low"
        result["confidence"] = 0.53
        return result


class EmptyThermalBackgroundPredictor(FakePredictor):
    def predict_window(self, payload, **kwargs):
        result = super().predict_window(payload, **kwargs)
        result["predicted_people_count"] = 1.18
        result["predicted_people_count_rounded"] = 1
        result["features"]["thermal_heat_delta_p95_median"] = 1.4
        return result


def _report(status: str):
    return SimpleNamespace(status=SimpleNamespace(value=status))


def _window():
    return SimpleNamespace(
        payload={
            "schema_version": "1.0",
            "window_id": "room_a-20260727T120000.000Z",
            "room_id": "room_a",
            "device_id": "pi5-room-a",
            "window_start": "2026-07-27T12:00:00Z",
            "window_end": "2026-07-27T12:00:05Z",
            "thermal": {"health": "ok", "frame_count": 2},
            "radar": {
                "health": "not_configured",
                "sample_count": 0,
                "tracks": [],
            },
            "sound": {
                "health": "ok",
                "rms_mean": 0.012,
                "rms_std": 0.002,
                "peak": 0.08,
            },
            "environment": {
                "light_lux": None,
                "temperature_c": 23.0,
                "humidity_pct": 55.0,
            },
            "quality": {"completeness": 0.94, "warnings": []},
        },
        thermal_frames=((23.0,) * 768, (23.1,) * 768),
        relative_features={
            "light": {"normalized": {"mean": 0.65}},
            "sound": {"rms": {"mean": 0.012}, "peak": 0.08},
        },
        health_reports={
            "thermal": _report("ok"),
            "radar": _report("not_configured"),
            "sound": _report("ok"),
            "light": _report("ok"),
            "climate": _report("ok"),
        },
    )


def test_live_processor_emits_contract_payloads_without_raw_frames() -> None:
    processor = LiveInferenceProcessor(FakePredictor())  # type: ignore[arg-type]

    result = processor(
        _window(),
        {"thermal_preview": {"schema_version": "1.0"}},
    )

    assert result["people_count"]["schema_version"] == "people_count_prediction.v1"
    assert result["people_count"]["predicted_people_count_rounded"] == 1
    assert result["observation"]["room_state"] == "quiet_study_recommended"
    assert result["observation"]["occupancy_level"] == "low"
    assert result["observation"]["features"]["light_relative_mean"] == 0.65
    serialized = json.dumps(result)
    assert "thermal_frames" not in serialized
    assert "temperatures_c" not in serialized
    assert "DASHBOARD_ONLY_NO_MODULE2_INFERENCE" not in serialized

    for schema_name, payload_name in (
        ("edge_observation.schema.json", "observation"),
        ("people_count_prediction.schema.json", "people_count"),
    ):
        schema = json.loads(
            (ROOT / "shared" / "contracts" / schema_name).read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(result[payload_name])


def test_live_processor_maps_sub_threshold_empty_prediction_to_zero() -> None:
    processor = LiveInferenceProcessor(EmptyDeadbandPredictor())  # type: ignore[arg-type]

    result = processor(_window(), {})

    count = result["people_count"]
    observation = result["observation"]
    assert count["predicted_people_count"] == 0.68
    assert count["predicted_people_count_rounded"] == 0
    assert count["occupancy_level"] == "empty"
    assert "LIVE_EMPTY_DEADBAND_APPLIED" in count["warnings"]
    assert observation["occupancy_level"] == "empty"
    assert observation["room_state"] == "empty_or_low_activity"


def test_live_processor_requires_thermal_presence_before_publishing_one() -> None:
    processor = LiveInferenceProcessor(EmptyThermalBackgroundPredictor())  # type: ignore[arg-type]

    result = processor(_window(), {})

    count = result["people_count"]
    assert count["predicted_people_count"] == 1.18
    assert count["predicted_people_count_rounded"] == 0
    assert count["occupancy_level"] == "empty"
    assert "THERMAL_PRESENCE_GATE_EMPTY" in count["warnings"]
    assert result["observation"]["room_state"] == "empty_or_low_activity"


def test_thermal_foreground_counter_uses_empty_background() -> None:
    counter = ThermalForegroundCounter(stability_windows=1)
    empty = [[23.0] * 768 for _ in range(5)]
    one_person = []
    for _ in range(5):
        frame = [23.0] * 768
        for y in range(9, 14):
            for x in range(14, 18):
                frame[y * 32 + x] = 29.0
        one_person.append(frame)

    assert counter.observe(empty) is None
    assert counter.observe(empty) == 0
    assert counter.observe(one_person) == 1


def _thermal_block(
    *,
    blocks: list[tuple[int, int, int, int]],
    base: float = 23.0,
    hot: float = 29.0,
) -> list[list[float]]:
    frame = np.full((24, 32), base, dtype=float)
    for top, left, height, width in blocks:
        frame[top : top + height, left : left + width] = hot
    return [frame.reshape(-1).tolist() for _ in range(5)]


def _write_calibration_command(
    path: Path,
    *,
    count: int,
    sample_windows: int = 1,
) -> None:
    path.write_text(
        json.dumps(
            {
                "request_id": f"test-{count}",
                "people_count": count,
                "sample_windows": sample_windows,
            }
        ),
        encoding="utf-8",
    )


def test_thermal_counter_calibrates_one_two_and_extrapolates_to_four(
    tmp_path: Path,
) -> None:
    command = tmp_path / "command.json"
    profile = tmp_path / "profile.json"
    counter = ThermalForegroundCounter(
        stability_windows=1,
        calibration_sample_windows=1,
        calibration_profile_path=profile,
        calibration_command_path=command,
    )
    empty = _thermal_block(blocks=[])
    one = _thermal_block(blocks=[(9, 5, 5, 4)])
    two_merged = _thermal_block(blocks=[(9, 5, 5, 8)])
    three_merged = _thermal_block(blocks=[(9, 5, 5, 12)])
    four_merged = _thermal_block(blocks=[(9, 5, 5, 16)])

    _write_calibration_command(command, count=0)
    assert counter.observe(empty) is None
    _write_calibration_command(command, count=1)
    assert counter.observe(one) == 1
    _write_calibration_command(command, count=2)
    assert counter.observe(two_merged) == 2
    assert counter.observe(three_merged) == 3
    assert counter.observe(four_merged) == 4
    assert counter.calibrated_counts == (1, 2)
    saved = json.loads(profile.read_text(encoding="utf-8"))
    assert saved["schema_version"] == "thermal-count-calibration.v1"
    assert set(saved["calibrations"]) == {"1", "2"}


def test_thermal_counter_requires_repeated_windows_before_state_change() -> None:
    counter = ThermalForegroundCounter(stability_windows=2)
    empty = _thermal_block(blocks=[])
    one = _thermal_block(blocks=[(9, 12, 5, 4)])

    assert counter.observe(empty) is None
    assert counter.observe(empty) == 0
    assert counter.observe(one) == 0
    assert counter.observe(one) == 1


def test_thermal_counter_treats_tiny_residual_heat_as_empty(
    tmp_path: Path,
) -> None:
    command = tmp_path / "command.json"
    counter = ThermalForegroundCounter(
        stability_windows=1,
        calibration_sample_windows=1,
        calibration_command_path=command,
    )
    empty = _thermal_block(blocks=[])
    one = _thermal_block(blocks=[(9, 12, 5, 4)])
    residual = _thermal_block(
        blocks=[(10, 13, 1, 3)],
        hot=24.0,
    )

    _write_calibration_command(command, count=0)
    assert counter.observe(empty) is None
    _write_calibration_command(command, count=1)
    assert counter.observe(one) == 1
    assert counter.observe(residual) == 0
    assert counter.last_diagnostics["foreground_area"] <= 3.0
    assert counter.last_diagnostics["excess_heat"] <= 1.2


def test_fusion_state_changes_with_people_and_sound() -> None:
    common = {
        "count_confidence": 0.85,
        "light_relative": 0.6,
        "temperature_c": 23.0,
        "humidity_pct": 55.0,
        "thermal_health": "ok",
        "sound_health": "ok",
        "environment_health": "ok",
        "completeness": 1.0,
    }

    empty = fuse_room_state(
        people_count=0,
        occupancy_level="empty",
        sound_rms=0.01,
        **common,
    )
    quiet = fuse_room_state(
        people_count=1,
        occupancy_level="low",
        sound_rms=0.01,
        **common,
    )
    discussion = fuse_room_state(
        people_count=2,
        occupancy_level="low",
        sound_rms=0.18,
        **common,
    )
    noisy = fuse_room_state(
        people_count=2,
        occupancy_level="low",
        sound_rms=0.40,
        **common,
    )

    assert [
        empty.room_state,
        quiet.room_state,
        discussion.room_state,
        noisy.room_state,
    ] == [
        "empty_or_low_activity",
        "quiet_study_recommended",
        "discussion_allowed",
        "not_recommended_noisy_or_crowded",
    ]


def test_fusion_environment_changes_suitability_not_people_count() -> None:
    comfortable = fuse_room_state(
        people_count=1,
        occupancy_level="low",
        count_confidence=0.85,
        sound_rms=0.01,
        light_relative=0.6,
        temperature_c=23.0,
        humidity_pct=55.0,
        thermal_health="ok",
        sound_health="ok",
        environment_health="ok",
        completeness=1.0,
    )
    uncomfortable = fuse_room_state(
        people_count=1,
        occupancy_level="low",
        count_confidence=0.85,
        sound_rms=0.01,
        light_relative=0.02,
        temperature_c=31.0,
        humidity_pct=82.0,
        thermal_health="ok",
        sound_health="ok",
        environment_health="ok",
        completeness=1.0,
    )

    assert comfortable.room_state == uncomfortable.room_state
    assert comfortable.suitability_score > uncomfortable.suitability_score
