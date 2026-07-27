from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from study_space_ml.data.io import load_windows
from study_space_ml.data.labels import load_labels
from study_space_ml.features import extract_feature_bundle
from study_space_ml.paths import infer_session_dir

DEFAULT_THRESHOLDS = {
    "quiet_rms_max": 0.22,
    "discussion_rms_max": 0.55,
    "empty_rms_max": 0.08,
    "crowded_rms_min": 0.55,
    "discussion_target_min": 2,
    "crowded_target_min": 3,
    "low_completeness": 0.70,
}


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def train_rule_model(*, windows_path: str | Path, labels_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    labels = load_labels(labels_path)
    session_dir = infer_session_dir(windows_path)
    windows = load_windows(windows_path)
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_label_count = 0
    for window in windows:
        label = labels.get(str(window.get("window_id")))
        if label is None:
            missing_label_count += 1
            continue
        bundle = extract_feature_bundle(window, session_dir=session_dir)
        row = dict(bundle.features)
        row["label"] = label.label
        by_label[label.label].append(row)

    thresholds = dict(DEFAULT_THRESHOLDS)
    medians: dict[str, dict[str, float | None]] = {}
    for label, rows in by_label.items():
        sounds = [float(row["sound_rms_mean"]) for row in rows if row.get("sound_rms_mean") is not None]
        targets = [float(row["radar_max_target_count"] or 0) for row in rows]
        medians[label] = {
            "sound_rms_mean": _median(sounds),
            "radar_max_target_count": _median(targets),
        }

    empty_med = medians.get("empty_or_low_activity", {}).get("sound_rms_mean")
    quiet_med = medians.get("quiet_study_recommended", {}).get("sound_rms_mean")
    discussion_med = medians.get("discussion_allowed", {}).get("sound_rms_mean")
    crowded_med = medians.get("not_recommended_noisy_or_crowded", {}).get("sound_rms_mean")

    if empty_med is not None and quiet_med is not None:
        thresholds["empty_rms_max"] = round((empty_med + quiet_med) / 2, 4)
    if quiet_med is not None and discussion_med is not None:
        thresholds["quiet_rms_max"] = round((quiet_med + discussion_med) / 2, 4)
    if discussion_med is not None and crowded_med is not None:
        value = round((discussion_med + crowded_med) / 2, 4)
        thresholds["discussion_rms_max"] = value
        thresholds["crowded_rms_min"] = value

    report = {
        "model_name": "edge-rule-baseline",
        "model_version": "0.3.0-custom",
        "feature_schema_version": "1.0",
        "confidence_threshold": 0.55,
        "thresholds": thresholds,
        "label_counts": {label: len(rows) for label, rows in sorted(by_label.items())},
        "missing_label_count": missing_label_count,
        "class_medians": medians,
        "notes": "Rule thresholds recalibrated from labels.csv. This is still a baseline, not a Random Forest accuracy claim.",
    }
    output = Path(out_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "model.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    feature_schema_source = Path(__file__).resolve().parents[3] / "configs" / "features.json"
    if feature_schema_source.is_file():
        (output / "feature_schema.json").write_text(feature_schema_source.read_text(encoding="utf-8"), encoding="utf-8")
    (output / "training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
