from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterator


VALID_TRAINING_LABELS = {
    "empty_or_low_activity",
    "quiet_study_recommended",
    "discussion_allowed",
    "not_recommended_noisy_or_crowded",
}


def resolve_windows_jsonl(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "windows.jsonl"
    if not candidate.is_file():
        raise FileNotFoundError(f"windows.jsonl not found: {candidate}")
    return candidate


def read_windows_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    windows_path = resolve_windows_jsonl(path)
    with windows_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {windows_path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Expected object on {windows_path}:{line_number}")
            yield payload


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")))
            handle.write("\n")


def load_labels_csv(path: str | Path) -> dict[str, dict[str, str]]:
    labels_path = Path(path)
    if not labels_path.is_file():
        raise FileNotFoundError(f"labels.csv not found: {labels_path}")
    with labels_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"session_id", "window_id", "label"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"labels.csv missing columns: {sorted(missing)}")
        labels: dict[str, dict[str, str]] = {}
        for row_number, row in enumerate(reader, start=2):
            window_id = (row.get("window_id") or "").strip()
            label = (row.get("label") or "").strip()
            if not window_id:
                raise ValueError(f"labels.csv row {row_number} has empty window_id")
            if label not in VALID_TRAINING_LABELS:
                raise ValueError(f"labels.csv row {row_number} has invalid label: {label}")
            if window_id in labels:
                raise ValueError(f"Duplicate label for window_id: {window_id}")
            labels[window_id] = {key: value for key, value in row.items() if key is not None}
    return labels
