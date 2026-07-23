from __future__ import annotations

from pathlib import Path

import pytest

from study_space_ml.jsonl import load_labels_csv


def test_load_labels_csv_accepts_template() -> None:
    labels = load_labels_csv(Path(__file__).resolve().parents[1] / "data" / "labels_template.csv")
    assert labels["room_a-20260716T063005.000Z"]["label"] == "quiet_study_recommended"


def test_load_labels_csv_rejects_unknown_training_label(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("session_id,window_id,label\ns1,w1,unknown\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid label"):
        load_labels_csv(path)
