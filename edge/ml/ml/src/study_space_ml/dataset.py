from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .features import as_feature_frame, extract_window_features
from .io import (
    discover_labels_file,
    find_session_dirs,
    load_relative_features,
    load_session_metadata,
    read_jsonl,
)
from .labels import load_labels, normalize_labels


def build_feature_table(dataset_root: str | Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for session_dir in find_session_dirs(dataset_root):
        relative_lookup = load_relative_features(session_dir)
        session_meta = load_session_metadata(session_dir)
        windows = read_jsonl(session_dir / "windows.jsonl", strict=False)
        for window in windows:
            row = extract_window_features(
                window,
                session_dir=session_dir,
                relative=relative_lookup.get(window.get("window_id")),
            )
            row["session_id"] = session_meta.get("session_id", session_dir.name)
            row["session_label"] = session_meta.get("scenario", "")
            row["participant_range"] = session_meta.get("participant_range", "")
            rows.append(row)
    return as_feature_frame(rows)


def load_session_meta_by_id(dataset_root: str | Path) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for session_dir in find_session_dirs(dataset_root):
        session_meta = load_session_metadata(session_dir)
        session_id = session_meta.get("session_id", session_dir.name)
        meta[session_id] = session_meta
    return meta


def build_training_table(
    dataset_root: str | Path,
    *,
    labels_path: str | Path | None = None,
) -> pd.DataFrame:
    features = build_feature_table(dataset_root)
    if labels_path is None:
        labels_path = discover_labels_file(dataset_root)
    if labels_path is None:
        raise FileNotFoundError(
            "No labels.csv found. Provide --labels, or place labels.csv at the dataset root."
        )

    meta_by_id = load_session_meta_by_id(dataset_root)
    labels_raw = load_labels(labels_path)
    labels = normalize_labels(labels_raw, session_meta_by_id=meta_by_id)

    keep_cols = ["session_id", "window_id", "people_count"]
    if "label" in labels.columns:
        keep_cols.append("label")
    merged = features.merge(labels[keep_cols], on=["session_id", "window_id"], how="inner")
    if merged.empty:
        raise ValueError(
            "No feature rows matched labels. Check session_id/window_id values in labels.csv."
        )
    return merged


def summarize_dataset(dataset_root: str | Path) -> dict[str, Any]:
    sessions = find_session_dirs(dataset_root)
    summary: dict[str, Any] = {
        "dataset_root": str(dataset_root),
        "session_count": len(sessions),
        "sessions": [],
        "window_count": 0,
    }
    for session_dir in sessions:
        meta = load_session_metadata(session_dir)
        windows_file = session_dir / "windows.jsonl"
        window_count = len(read_jsonl(windows_file, strict=False))
        summary["window_count"] += window_count
        summary["sessions"].append({
            "session_id": meta.get("session_id", session_dir.name),
            "scenario": meta.get("scenario", ""),
            "participant_range": meta.get("participant_range", ""),
            "window_count": window_count,
            "radar_enabled": ((meta.get("sampling_config") or {}).get("sensors") or {}).get("radar", {}).get("enabled"),
        })
    return summary
