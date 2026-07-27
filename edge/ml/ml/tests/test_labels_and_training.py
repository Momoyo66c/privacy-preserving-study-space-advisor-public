from __future__ import annotations

import json
from pathlib import Path

from study_space_ml.data.io import write_jsonl
from study_space_ml.data.labels import load_labels
from study_space_ml.training.train_rule import train_rule_model


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_load_labels_and_train_rule(tmp_path: Path) -> None:
    fixture_dir = repo_root() / "shared" / "fixtures"
    fixture_names = [
        ("sensor_window_empty.json", "empty_or_low_activity"),
        ("sensor_window_quiet.json", "quiet_study_recommended"),
        ("sensor_window_discussion.json", "discussion_allowed"),
        ("sensor_window_crowded.json", "not_recommended_noisy_or_crowded"),
    ]
    windows = []
    labels_lines = ["session_id,window_id,label,annotator,notes"]
    for name, label in fixture_names:
        window = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        windows.append(window)
        labels_lines.append(f"session-test,{window['window_id']},{label},manual,")
    windows_path = tmp_path / "windows.jsonl"
    labels_path = tmp_path / "labels.csv"
    out_dir = tmp_path / "artifact"
    write_jsonl(windows_path, windows)
    labels_path.write_text("\n".join(labels_lines) + "\n", encoding="utf-8")
    labels = load_labels(labels_path)
    assert len(labels) == 4
    report = train_rule_model(windows_path=windows_path, labels_path=labels_path, out_dir=out_dir)
    assert (out_dir / "model.json").is_file()
    assert report["label_counts"]["quiet_study_recommended"] == 1
