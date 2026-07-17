from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.cli import collect_main
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import load_config
from study_space_hardware.storage import SessionWriter, enforce_session_retention


EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"


def test_session_writer_saves_npz_and_never_audio(tmp_path) -> None:
    config = load_config(EXAMPLE_CONFIG)
    config = replace(
        config,
        storage=replace(config.storage, data_dir=str(tmp_path)),
    )
    clock = ManualClock()
    orchestrator = build_orchestrator(config, clock=clock)
    writer = SessionWriter(
        config=config,
        scenario=config.simulator.scenario,
        known_anomalies=("thermal sensor disconnected", " radar warm-up "),
        now=clock.now_utc(),
    )
    try:
        stored_payload = writer.append(orchestrator.run_window())
    finally:
        orchestrator.close()
    session_path = writer.finalize(clock.now_utc())

    npz_path = next((session_path / "thermal").glob("*.npz"))
    with np.load(npz_path) as data:
        assert data["frames"].shape == (10, 768)
    assert stored_payload["thermal"]["frames_ref"].startswith("local://")
    assert not list(session_path.rglob("*.wav"))
    assert not list(session_path.rglob("*.pcm"))
    assert not list(session_path.rglob("*.mp3"))
    metadata = json.loads((session_path / "session.json").read_text())
    assert metadata["privacy"]["raw_audio_persisted"] is False
    assert metadata["known_anomalies"] == [
        "thermal sensor disconnected",
        "radar warm-up",
    ]
    assert metadata["window_count"] == 1
    assert (session_path / "checksums.json").is_file()


def test_retention_removes_expired_and_excess_sessions_only(tmp_path) -> None:
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    unrelated = tmp_path / "do-not-delete"
    unrelated.mkdir()

    sessions = []
    for index, age_days in enumerate((1, 2, 40)):
        path = tmp_path / f"session-test-{index}"
        path.mkdir()
        (path / "session.json").write_text("{}\n", encoding="utf-8")
        timestamp = (now - timedelta(days=age_days)).timestamp()
        os.utime(path, (timestamp, timestamp))
        sessions.append(path)

    removed = enforce_session_retention(
        tmp_path,
        max_sessions=1,
        max_age_days=30,
        now=now,
    )

    assert set(removed) == {sessions[1], sessions[2]}
    assert sessions[0].is_dir()
    assert unrelated.is_dir()


def test_collect_cli_records_repeatable_known_anomalies(
    tmp_path: Path,
    capsys,
) -> None:
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["storage"]["data_dir"] = str(tmp_path / "sessions")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    result = collect_main(
        [
            "--config",
            str(config_path),
            "--room",
            "room_a",
            "--scenario",
            "quiet_study_recommended",
            "--duration",
            "5",
            "--known-anomaly",
            "mlx90640 initial frame dropped",
            "--known-anomaly",
            "ld2450 warm-up",
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    metadata = json.loads(
        (Path(output["path"]) / "session.json").read_text(encoding="utf-8")
    )
    assert metadata["known_anomalies"] == [
        "mlx90640 initial frame dropped",
        "ld2450 warm-up",
    ]
