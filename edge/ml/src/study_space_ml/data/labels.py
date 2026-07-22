from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from study_space_ml.constants import TRAINING_LABELS


@dataclass(frozen=True, slots=True)
class LabelRow:
    session_id: str
    window_id: str
    label: str
    annotator: str = ""
    notes: str = ""


def load_labels(path: str | Path) -> dict[str, LabelRow]:
    labels_path = Path(path).expanduser().resolve()
    if not labels_path.is_file():
        raise FileNotFoundError(f"labels.csv not found: {labels_path}")
    result: dict[str, LabelRow] = {}
    with labels_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"session_id", "window_id", "label"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"labels.csv is missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            window_id = (row.get("window_id") or "").strip()
            label = (row.get("label") or "").strip()
            if not window_id:
                raise ValueError(f"labels.csv:{line_number}: window_id is required")
            if label not in TRAINING_LABELS:
                raise ValueError(f"labels.csv:{line_number}: invalid label {label!r}")
            if window_id in result:
                raise ValueError(f"labels.csv:{line_number}: duplicate window_id {window_id!r}")
            result[window_id] = LabelRow(
                session_id=(row.get("session_id") or "").strip(),
                window_id=window_id,
                label=label,
                annotator=(row.get("annotator") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
    return result
