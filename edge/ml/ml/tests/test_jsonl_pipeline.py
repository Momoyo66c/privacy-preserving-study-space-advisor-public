from __future__ import annotations

import json
from pathlib import Path

from study_space_ml.data.io import load_windows, write_jsonl
from study_space_ml.inference.predictor import EdgePredictor


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_predict_jsonl_like_module1_output(tmp_path: Path) -> None:
    fixture_dir = repo_root() / "shared" / "fixtures"
    windows = [
        json.loads((fixture_dir / "sensor_window_empty.json").read_text(encoding="utf-8")),
        json.loads((fixture_dir / "sensor_window_quiet.json").read_text(encoding="utf-8")),
        json.loads((fixture_dir / "sensor_window_discussion.json").read_text(encoding="utf-8")),
    ]
    jsonl = tmp_path / "windows.jsonl"
    write_jsonl(jsonl, windows)
    loaded = load_windows(jsonl)
    predictor = EdgePredictor()
    outputs = [predictor.predict_window(window) for window in loaded]
    assert [item["room_state"] for item in outputs] == [
        "empty_or_low_activity",
        "quiet_study_recommended",
        "discussion_allowed",
    ]
