from __future__ import annotations

import csv
import json
from pathlib import Path

from study_space_hardware.session_validation import validate_session


DATASET_DIR = (
    Path(__file__).resolve().parents[1]
    / "sample_data"
    / "real_two_person_v1"
)


def test_real_two_person_sample_sessions_and_labels_are_valid() -> None:
    manifest = json.loads(
        (DATASET_DIR / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["synthetic"] is False
    assert manifest["window_count"] == 18
    assert manifest["session_count"] == 2
    assert manifest["privacy"] == {
        "names_recorded": False,
        "student_ids_recorded": False,
        "raw_audio_persisted": False,
        "rgb_images_recorded": False,
        "personal_tracking_recorded": False,
    }

    expected_labels: dict[str, str] = {}
    for item in manifest["sessions"]:
        session_id = item["session_id"]
        report = validate_session(DATASET_DIR / session_id)
        assert report.valid, report.errors
        assert report.window_count == 9
        for line in (
            DATASET_DIR / session_id / "windows.jsonl"
        ).read_text(encoding="utf-8").splitlines():
            window = json.loads(line)
            expected_labels[window["window_id"]] = item["label"]

    with (DATASET_DIR / "labels.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        labels = list(csv.DictReader(handle))

    assert len(labels) == 18
    assert {row["window_id"] for row in labels} == set(expected_labels)
    assert all(
        row["label"] == expected_labels[row["window_id"]]
        for row in labels
    )
