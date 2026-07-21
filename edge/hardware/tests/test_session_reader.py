from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_hardware.session_reader import InvalidSessionError, SessionReader
from study_space_hardware.storage import SessionWriter


EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"


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
        participant_range="1-4",
        now=clock.now_utc(),
    )
    try:
        writer.append(orchestrator.run_window())
        writer.append(orchestrator.run_window())
    finally:
        orchestrator.close()
    return writer.finalize(clock.now_utc())


def test_reader_exposes_validated_windows_and_streams_thermal_npz(tmp_path) -> None:
    session_path = _create_session(tmp_path)

    reader = SessionReader(session_path)
    windows = list(reader)

    assert reader.session_id == session_path.name
    assert reader.metadata["participant_range"] == "1-4"
    assert len(reader) == len(windows) == 2
    assert windows[0].payload["schema_version"] == "1.0"
    assert windows[0].thermal_frames is not None
    assert windows[0].thermal_frames.shape == (10, 768)
    assert windows[0].thermal_frames.dtype.name == "float32"
    assert windows[0].thermal_frames.flags.writeable is False


def test_reader_refuses_tampered_package_before_exposing_windows(tmp_path) -> None:
    session_path = _create_session(tmp_path)
    windows_path = session_path / "windows.jsonl"
    payloads = [json.loads(line) for line in windows_path.read_text().splitlines()]
    payloads[0]["room_id"] = "tampered-room"
    windows_path.write_text(
        "\n".join(json.dumps(payload) for payload in payloads) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidSessionError) as exc_info:
        SessionReader(session_path)

    assert "checksum mismatch: windows.jsonl" in exc_info.value.report.errors
