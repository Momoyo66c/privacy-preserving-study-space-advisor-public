from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.cli import verify_main
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_hardware.session_validation import validate_session
from study_space_hardware.storage import SessionWriter


EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"


def _rewrite_checksums(session_path: Path) -> None:
    checksums = {
        path.relative_to(session_path).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in session_path.rglob("*")
        if path.is_file() and path.name != "checksums.json"
    }
    (session_path / "checksums.json").write_text(
        json.dumps(checksums) + "\n",
        encoding="utf-8",
    )


def _create_session(tmp_path: Path) -> Path:
    config = load_config(EXAMPLE_CONFIG)
    config = replace(
        config,
        storage=replace(config.storage, data_dir=str(tmp_path / "sessions")),
    )
    clock = ManualClock()
    orchestrator = build_orchestrator(config, clock=clock)
    writer = SessionWriter(
        config=config,
        scenario=config.simulator.scenario,
        known_anomalies=("simulated validation session",),
        now=clock.now_utc(),
    )
    try:
        writer.append(orchestrator.run_window())
    finally:
        orchestrator.close()
    return writer.finalize(clock.now_utc())


def test_valid_session_passes_library_and_cli(
    tmp_path: Path,
    capsys,
) -> None:
    session_path = _create_session(tmp_path)

    report = validate_session(session_path)

    assert report.valid is True
    assert report.window_count == 1
    assert report.thermal_files == 1
    assert report.errors == ()
    assert verify_main([str(session_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["session_id"] == session_path.name


def test_privacy_violation_and_checksum_tamper_fail(
    tmp_path: Path,
) -> None:
    session_path = _create_session(tmp_path)
    metadata_path = session_path / "session.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["privacy"]["raw_audio_persisted"] = True
    metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")

    report = validate_session(session_path)

    assert report.valid is False
    assert "session privacy field must be false: raw_audio_persisted" in report.errors
    assert "checksum mismatch: session.json" in report.errors


def test_prohibited_media_and_untracked_file_fail(tmp_path: Path) -> None:
    session_path = _create_session(tmp_path)
    (session_path / "captured-audio.wav").write_bytes(b"not audio")

    report = validate_session(session_path)

    assert report.valid is False
    assert "prohibited audio/image/video file: captured-audio.wav" in report.errors
    assert "file missing from checksums.json: captured-audio.wav" in report.errors


def test_corrupt_thermal_npz_fails(tmp_path: Path) -> None:
    session_path = _create_session(tmp_path)
    thermal_path = next((session_path / "thermal").glob("*.npz"))
    thermal_path.write_bytes(b"corrupt")

    report = validate_session(session_path)

    assert report.valid is False
    assert f"checksum mismatch: thermal/{thermal_path.name}" in report.errors
    assert any(error.startswith("invalid thermal NPZ") for error in report.errors)


def test_window_contract_error_fails(tmp_path: Path) -> None:
    session_path = _create_session(tmp_path)
    windows_path = session_path / "windows.jsonl"
    payload = json.loads(windows_path.read_text(encoding="utf-8"))
    del payload["room_id"]
    windows_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    report = validate_session(session_path)

    assert report.valid is False
    assert any("schema error" in error and "room_id" in error for error in report.errors)
    assert "checksum mismatch: windows.jsonl" in report.errors


def test_semantic_session_mismatch_fails_even_with_updated_checksums(
    tmp_path: Path,
) -> None:
    session_path = _create_session(tmp_path)
    windows_path = session_path / "windows.jsonl"
    payload = json.loads(windows_path.read_text(encoding="utf-8"))
    payload["room_id"] = "different-room"
    payload["window_end"] = payload["window_start"]
    windows_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    _rewrite_checksums(session_path)

    report = validate_session(session_path)

    assert report.valid is False
    assert "window 1 room_id does not match session.json" in report.errors
    assert "window 1 duration must be between 5 and 10 seconds" in report.errors
    assert not any(error.startswith("checksum mismatch") for error in report.errors)


def test_non_finite_thermal_values_fail_even_with_updated_checksums(
    tmp_path: Path,
) -> None:
    session_path = _create_session(tmp_path)
    thermal_path = next((session_path / "thermal").glob("*.npz"))
    with np.load(thermal_path, allow_pickle=False) as data:
        frames = data["frames"].copy()
    frames[0, 0] = np.nan
    np.savez_compressed(thermal_path, frames=frames)
    _rewrite_checksums(session_path)

    report = validate_session(session_path)

    assert report.valid is False
    assert (
        f"thermal NPZ contains non-finite values: thermal/{thermal_path.name}"
        in report.errors
    )
    assert not any(error.startswith("checksum mismatch") for error in report.errors)
