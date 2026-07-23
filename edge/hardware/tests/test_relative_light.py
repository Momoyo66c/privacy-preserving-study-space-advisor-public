from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from study_space_hardware import light_calibration_cli
from study_space_hardware.config import config_from_dict
from study_space_hardware.drivers.base import SensorReadError
from study_space_hardware.light_calibration_cli import main
from study_space_hardware.models import SampleQuality, SensorSample
from study_space_hardware.relative_light import (
    LightAnchor,
    RelativeLightCalibration,
    calibration_from_dict,
    load_calibration,
    save_calibration,
)


NOW = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)


def _anchor(label: str, center: int) -> LightAnchor:
    return LightAnchor.from_samples(
        label,
        [center - 2, center - 1, center, center + 1, center + 2],
    )


def _profile(
    *,
    dark: int = 300,
    bright: int = 900,
) -> RelativeLightCalibration:
    return RelativeLightCalibration.create(
        device_id="pi5-a",
        dark=_anchor("dark", dark),
        bright=_anchor("bright", bright),
        created_at=NOW,
    )


def test_increasing_profile_maps_and_clamps_adc_values() -> None:
    profile = _profile(dark=300, bright=900)

    assert profile.direction == "increasing"
    assert profile.map_adc(100) == 0.0
    assert profile.map_adc(300) == 0.0
    assert profile.map_adc(600) == pytest.approx(0.5)
    assert profile.map_adc(900) == 1.0
    assert profile.map_adc(1200) == 1.0


def test_decreasing_profile_detects_sensor_direction() -> None:
    profile = _profile(dark=900, bright=300)

    assert profile.direction == "decreasing"
    assert profile.map_adc(900) == 0.0
    assert profile.map_adc(600) == pytest.approx(0.5)
    assert profile.map_adc(300) == 1.0


def test_profile_rejects_anchors_without_enough_separation() -> None:
    with pytest.raises(ValueError, match="too close"):
        _profile(dark=300, bright=340)


def test_profile_round_trip_is_strict_and_device_specific(tmp_path) -> None:
    path = tmp_path / "hw486-relative.json"
    profile = _profile()
    save_calibration(path, profile)

    loaded = load_calibration(path, expected_device_id="pi5-a")
    assert loaded == profile

    with pytest.raises(ValueError, match="different device"):
        load_calibration(path, expected_device_id="pi5-b")

    value = json.loads(path.read_text(encoding="utf-8"))
    value["unexpected"] = "rejected"
    with pytest.raises(ValueError, match="unknown or missing"):
        calibration_from_dict(value)


def test_profile_rejects_tampered_span() -> None:
    value = _profile().to_dict()
    value["span_adc"] = 999.0

    with pytest.raises(ValueError, match="span does not match"):
        calibration_from_dict(value)


def test_cli_captures_two_stages_without_persisting_individual_samples(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "esp32.yaml"
    config_path.write_text(
        """
room_id: room_a
device_id: pi5-a
simulator:
  enabled: false
transport:
  mode: esp32_hub
  port: /dev/serial/by-id/test
sensors:
  light:
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    staging = tmp_path / "dark.json"
    profile_path = tmp_path / "profile.json"

    def fake_capture(config, *, label: str, sample_count: int) -> LightAnchor:
        assert config.device_id == "pi5-a"
        assert sample_count == 12
        return _anchor(label, 300 if label == "dark" else 900)

    monkeypatch.setattr(light_calibration_cli, "_capture_anchor", fake_capture)

    assert (
        main(
            [
                "capture-dark",
                "--config",
                str(config_path),
                "--output",
                str(staging),
            ]
        )
        == 0
    )
    dark_result = json.loads(capsys.readouterr().out)
    assert dark_result["anchor"]["sample_count"] == 5
    assert "samples" not in staging.read_text(encoding="utf-8")

    assert (
        main(
            [
                "capture-bright",
                "--config",
                str(config_path),
                "--staging",
                str(staging),
                "--output",
                str(profile_path),
            ]
        )
        == 0
    )
    bright_result = json.loads(capsys.readouterr().out)
    assert bright_result["span_adc"] == 600.0
    assert bright_result["calibrated_lux"] is False
    assert load_calibration(profile_path).map_adc(600) == pytest.approx(0.5)


def test_status_command_states_that_profile_is_not_lux(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "profile.json"
    save_calibration(path, _profile())

    assert main(["status", "--profile", str(path), "--device-id", "pi5-a"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["calibrated_lux"] is False


def test_capture_tolerates_transient_hub_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IntermittentLight:
        def __init__(self) -> None:
            self.read_count = 0
            self.closed = False

        def start(self) -> None:
            pass

        def read(self) -> SensorSample:
            self.read_count += 1
            if self.read_count in {1, 3}:
                raise SensorReadError("transient test timeout")
            return SensorSample(
                sensor="light",
                captured_at=NOW,
                monotonic_s=float(self.read_count),
                values={"light_adc_raw": 300 + self.read_count},
                units={"light_adc_raw": "adc_count"},
                quality=SampleQuality.VALID,
                source="test",
            )

        def close(self) -> None:
            self.closed = True

    light = IntermittentLight()
    monkeypatch.setattr(
        light_calibration_cli,
        "build_real_drivers",
        lambda config, clock: {"light": light},
    )
    config = config_from_dict(
        {
            "room_id": "room_a",
            "device_id": "pi5-a",
            "simulator": {"enabled": False},
            "transport": {
                "mode": "esp32_hub",
                "port": "/dev/serial/by-id/test",
            },
        }
    )

    anchor = light_calibration_cli._capture_anchor(
        config,
        label="dark",
        sample_count=5,
    )

    assert anchor.sample_count == 5
    assert light.read_count == 7
    assert light.closed is True
