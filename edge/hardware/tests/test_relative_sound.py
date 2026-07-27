from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from study_space_hardware import sound_calibration_cli
from study_space_hardware.bootstrap import build_real_drivers
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import config_from_dict
from study_space_hardware.drivers.base import SensorReadError
from study_space_hardware.models import SampleQuality, SensorSample
from study_space_hardware.relative_sound import (
    RelativeSoundCalibration,
    SoundAnchor,
    calibration_from_dict,
    load_calibration,
    save_calibration,
)
from study_space_hardware.sound_calibration_cli import main


NOW = datetime(2026, 7, 23, 7, 0, tzinfo=timezone.utc)


def _anchor(
    label: str,
    *,
    rms_center: float,
    peak_center: float,
    count: int = 80,
) -> SoundAnchor:
    samples = [
        (
            rms_center + ((index % 5) - 2) * rms_center * 0.01,
            peak_center + ((index % 7) - 3) * peak_center * 0.01,
        )
        for index in range(count)
    ]
    return SoundAnchor.from_samples(label, samples)


def _profile() -> RelativeSoundCalibration:
    return RelativeSoundCalibration.create(
        device_id="pi5-a",
        quiet=_anchor("quiet", rms_center=0.02, peak_center=0.04),
        reference=_anchor("reference", rms_center=0.40, peak_center=0.70),
        noise_margin_fraction=0.10,
        created_at=NOW,
    )


def test_profile_accepts_nonzero_ambient_and_reserves_ten_percent_margin() -> None:
    profile = _profile()
    quiet_rms = profile.quiet.rms.p95
    raw_gap = profile.reference.rms.top_decile_median - quiet_rms

    assert profile.rms_floor == pytest.approx(quiet_rms + raw_gap * 0.10)
    assert profile.rms_floor > quiet_rms
    assert profile.map_rms(profile.rms_floor) == 0.0
    assert profile.map_rms(profile.rms_ceiling) == 1.0
    assert profile.map_peak(profile.peak_floor) == 0.0
    assert profile.map_peak(profile.peak_ceiling) == 1.0
    assert profile.map_peak(0.0) == 0.0
    assert profile.map_peak(1.0) == 1.0


def test_reference_uses_top_decile_median_instead_of_single_spike() -> None:
    values = [(0.02, 0.04)] * 70
    values += [(0.30, 0.50)] * 9
    values += [(1.0, 1.0)]
    reference = SoundAnchor.from_samples("reference", values)

    assert reference.rms.maximum == 1.0
    assert reference.rms.top_decile_median == pytest.approx(0.30)
    assert reference.peak.top_decile_median == pytest.approx(0.50)


def test_profile_rejects_reference_too_close_to_ambient() -> None:
    quiet = _anchor("quiet", rms_center=0.02, peak_center=0.04)
    reference = _anchor("reference", rms_center=0.021, peak_center=0.041)

    with pytest.raises(ValueError, match="reference"):
        RelativeSoundCalibration.create(
            device_id="pi5-a",
            quiet=quiet,
            reference=reference,
        )


def test_profile_round_trip_is_strict_non_db_and_device_specific(tmp_path) -> None:
    path = tmp_path / "hw485-relative.json"
    profile = _profile()
    save_calibration(path, profile)

    assert load_calibration(path, expected_device_id="pi5-a") == profile
    with pytest.raises(ValueError, match="different device"):
        load_calibration(path, expected_device_id="pi5-b")

    value = json.loads(path.read_text(encoding="utf-8"))
    value["calibrated_db"] = True
    with pytest.raises(ValueError, match="cannot claim"):
        calibration_from_dict(value)

    value = profile.to_dict()
    value["unexpected"] = "rejected"
    with pytest.raises(ValueError, match="unknown or missing"):
        calibration_from_dict(value)


def test_profile_rejects_tampered_derived_bounds() -> None:
    value = _profile().to_dict()
    value["rms_floor"] = 0.0

    with pytest.raises(ValueError, match="do not match"):
        calibration_from_dict(value)


def test_cli_captures_two_aggregate_only_stages(
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
  sound:
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    staging = tmp_path / "quiet.json"
    profile_path = tmp_path / "trial.json"

    def fake_capture(
        config,
        *,
        label: str,
        sample_count: int,
        warmup_count: int,
    ) -> SoundAnchor:
        assert config.device_id == "pi5-a"
        assert sample_count in {20, 32}
        assert warmup_count == 8
        if label == "quiet":
            return _anchor(label, rms_center=0.02, peak_center=0.04)
        return _anchor(label, rms_center=0.40, peak_center=0.70)

    monkeypatch.setattr(sound_calibration_cli, "_capture_anchor", fake_capture)

    assert (
        main(
            [
                "preflight",
                "--config",
                str(config_path),
            ]
        )
        == 0
    )
    preflight_result = json.loads(capsys.readouterr().out)
    assert preflight_result["saved"] is False
    assert preflight_result["diagnostic_only"] is True

    assert (
        main(
            [
                "capture-quiet",
                "--config",
                str(config_path),
                "--output",
                str(staging),
            ]
        )
        == 0
    )
    quiet_result = json.loads(capsys.readouterr().out)
    assert quiet_result["calibrated_db"] is False
    staging_text = staging.read_text(encoding="utf-8")
    assert "audio" not in staging_text.lower()
    assert "samples" not in staging_text.lower()

    assert (
        main(
            [
                "capture-reference",
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
    result = json.loads(capsys.readouterr().out)
    assert result["noise_margin_fraction"] == 0.10
    assert result["calibrated_db"] is False
    assert load_calibration(profile_path).map_rms(1.0) == 1.0


def test_capture_discards_warmup_and_tolerates_transient_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IntermittentSound:
        def __init__(self) -> None:
            self.read_count = 0
            self.closed = False

        def start(self) -> None:
            pass

        def read(self) -> SensorSample:
            self.read_count += 1
            if self.read_count in {1, 4, 9}:
                raise SensorReadError("transient test timeout")
            return SensorSample(
                sensor="sound",
                captured_at=NOW,
                monotonic_s=float(self.read_count),
                values={"rms": 0.02, "peak": 0.04},
                units={"rms": "normalized", "peak": "normalized"},
                quality=SampleQuality.VALID,
                source="test",
            )

        def close(self) -> None:
            self.closed = True

    sound = IntermittentSound()
    monkeypatch.setattr(
        sound_calibration_cli,
        "build_real_drivers",
        lambda config, clock: {"sound": sound},
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

    anchor = sound_calibration_cli._capture_anchor(
        config,
        label="quiet",
        sample_count=20,
        warmup_count=5,
    )

    assert anchor.sample_count == 20
    assert sound.read_count == 28
    assert sound.closed is True


def test_status_command_reports_relative_not_db(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "trial.json"
    save_calibration(path, _profile())

    assert main(["status", "--profile", str(path), "--device-id", "pi5-a"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["calibrated_db"] is False


def test_bootstrap_loads_device_matched_profile_from_environment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "trial.json"
    save_calibration(path, _profile())
    monkeypatch.setenv("HW485_RELATIVE_CALIBRATION_PATH", str(path))
    config = config_from_dict(
        {
            "room_id": "room_a",
            "device_id": "pi5-a",
            "simulator": {"enabled": False},
            "transport": {
                "mode": "esp32_hub",
                "port": "/dev/serial/by-id/test",
            },
            "sensors": {
                "thermal": {"enabled": False},
                "radar": {"enabled": False},
                "light": {"enabled": False},
                "climate": {"enabled": False},
            },
        }
    )

    drivers = build_real_drivers(config, ManualClock())

    assert set(drivers) == {"sound"}
    sound = drivers["sound"]
    assert sound.relative_calibration == _profile()  # type: ignore[attr-defined]
