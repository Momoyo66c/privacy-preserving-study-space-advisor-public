from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from study_space_hardware.config import config_from_dict
from study_space_hardware.drivers.base import SensorReadError
from study_space_hardware.models import SampleQuality, SensorSample
from study_space_hardware import sound_diagnostic_cli
from study_space_hardware.sound_diagnostic import (
    SoundDiagnosticSnapshot,
    compare_snapshots,
    load_snapshot,
    save_snapshot,
)


NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)


def _sample(
    index: int,
    *,
    rms: float,
    std: float,
    peak: float,
) -> SensorSample:
    return SensorSample(
        sensor="sound",
        captured_at=NOW,
        monotonic_s=float(index),
        values={
            "rms": rms,
            "std": std,
            "peak": peak,
            "chunk_frames": 400,
            "raw_audio_persisted": False,
        },
        units={
            "rms": "normalized",
            "std": "normalized",
            "peak": "normalized",
        },
        quality=SampleQuality.VALID,
        source="test",
    )


def _snapshot(
    label: str,
    *,
    rms: float,
    std: float,
    peak: float,
) -> SoundDiagnosticSnapshot:
    return SoundDiagnosticSnapshot.from_samples(
        device_id="pi5-a",
        label=label,
        samples=[
            _sample(index, rms=rms, std=std, peak=peak)
            for index in range(8)
        ],
        captured_at=NOW,
    )


def test_snapshot_contains_only_non_reconstructive_aggregates(tmp_path) -> None:
    path = tmp_path / "quiet.json"
    snapshot = SoundDiagnosticSnapshot.from_samples(
        device_id="pi5-a",
        label="quiet",
        samples=[
            _sample(
                index,
                rms=index / 1000,
                std=index / 2000,
                peak=index / 500,
            )
            for index in range(8)
        ],
        captured_at=NOW,
    )

    save_snapshot(path, snapshot)
    encoded = json.loads(path.read_text(encoding="utf-8"))

    assert encoded["window_count"] == 8
    assert encoded["firmware_sample_points"] == 3200
    assert encoded["chunk_frames_min"] == 400
    assert encoded["chunk_frames_max"] == 400
    assert encoded["raw_audio_persisted"] is False
    assert encoded["per_window_values_persisted"] is False
    assert set(encoded["metrics"]) == {"rms", "std", "peak"}
    assert "samples" not in encoded
    assert "audio" not in json.dumps(encoded).lower().replace(
        "raw_audio_persisted",
        "",
    )
    assert load_snapshot(path, expected_device_id="pi5-a") == snapshot


def test_compare_detects_sustained_ac_response() -> None:
    result = compare_snapshots(
        _snapshot("quiet", rms=0.001, std=0.001, peak=0.002),
        _snapshot("reference", rms=0.05, std=0.04, peak=0.08),
    )

    assert result["conclusion"] == "sustained_ac_response_detected"
    assert result["suitable_for_relative_room_noise"] is True
    assert result["calibrated_db"] is False


def test_compare_classifies_peak_only_response() -> None:
    quiet = _snapshot("quiet", rms=0.0, std=0.0, peak=0.0)
    reference_samples = [
        _sample(
            index,
            rms=0.0,
            std=0.0,
            peak=0.1 if index == 7 else 0.0,
        )
        for index in range(8)
    ]
    reference = SoundDiagnosticSnapshot.from_samples(
        device_id="pi5-a",
        label="reference",
        samples=reference_samples,
        captured_at=NOW,
    )

    result = compare_snapshots(quiet, reference)

    assert result["conclusion"] == "peak_or_impulse_only_response"
    assert result["suitable_for_relative_room_noise"] is False


def test_snapshot_rejects_invalid_or_incomplete_samples() -> None:
    with pytest.raises(ValueError, match="at least 8"):
        SoundDiagnosticSnapshot.from_samples(
            device_id="pi5-a",
            label="quiet",
            samples=[_sample(1, rms=0.0, std=0.0, peak=0.0)],
        )
    invalid = _sample(0, rms=0.0, std=0.0, peak=0.0)
    value = invalid.values.copy()
    value["std"] = float("nan")
    invalid = SensorSample(
        sensor="sound",
        captured_at=NOW,
        monotonic_s=0.0,
        values=value,
        units=invalid.units,
    )
    with pytest.raises(ValueError, match="std"):
        SoundDiagnosticSnapshot.from_samples(
            device_id="pi5-a",
            label="quiet",
            samples=[invalid] * 8,
        )


def test_cli_capture_discards_warmup_and_timeouts(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class IntermittentSound:
        def __init__(self) -> None:
            self.read_count = 0
            self.closed = False

        def start(self) -> None:
            pass

        def read(self) -> SensorSample:
            self.read_count += 1
            if self.read_count in {1, 4}:
                raise SensorReadError("transient timeout")
            return _sample(
                self.read_count,
                rms=0.001,
                std=0.002,
                peak=0.003,
            )

        def close(self) -> None:
            self.closed = True

    sound = IntermittentSound()
    monkeypatch.setattr(
        sound_diagnostic_cli,
        "build_real_drivers",
        lambda config, clock: {"sound": sound},
    )
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
    output = tmp_path / "quiet.json"

    assert (
        sound_diagnostic_cli.main(
            [
                "capture",
                "--config",
                str(config_path),
                "--label",
                "quiet",
                "--output",
                str(output),
                "--samples",
                "8",
                "--warmup-samples",
                "2",
            ]
        )
        == 0
    )

    result = json.loads(capsys.readouterr().out)
    assert result["snapshot"]["window_count"] == 8
    assert sound.read_count == 12
    assert sound.closed is True


def test_compare_rejects_cross_device_snapshots() -> None:
    quiet = _snapshot("quiet", rms=0.0, std=0.0, peak=0.0)
    reference = SoundDiagnosticSnapshot.from_dict(
        {
            **_snapshot(
                "reference",
                rms=0.1,
                std=0.1,
                peak=0.1,
            ).to_dict(),
            "device_id": "pi5-b",
        }
    )

    with pytest.raises(ValueError, match="different devices"):
        compare_snapshots(quiet, reference)
