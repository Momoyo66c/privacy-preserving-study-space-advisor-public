from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .constants import (
    FEATURE_NAMES,
    PEOPLE_COUNT_FEATURE_SCHEMA_VERSION,
    PEOPLE_COUNT_MODEL_NAME,
    PEOPLE_COUNT_MODEL_VERSION,
)
from .features import extract_window_features
from .io import load_relative_features, read_jsonl, write_jsonl


STATIC_HEAT_SEQUENCE_WINDOWS = 3


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def occupancy_level_from_count(count: int) -> str:
    if count <= 0:
        return "empty"
    if count <= 2:
        return "low"
    if count <= 5:
        return "medium"
    return "high"


def compute_prediction_id(window_id: str, model_version: str) -> str:
    raw = f"{window_id}:{model_version}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:26]


def _static_single_window_candidate(features: dict[str, Any]) -> bool:
    """Single-window signal for a possible laptop/computer heat source.

    It is intentionally conservative: a single still window only creates a warning
    and a small confidence reduction. Stronger correction needs multiple
    consecutive windows.
    """
    return (
        float(features.get("thermal_available", 0.0) or 0.0) >= 1.0
        and float(features.get("thermal_hot_region_count", 0.0) or 0.0) >= 1.0
        and float(features.get("thermal_static_heat_score", 0.0) or 0.0) >= 0.86
        and float(features.get("thermal_main_hot_centroid_path_px", 0.0) or 0.0) <= 0.45
        and float(features.get("thermal_hot_motion_ratio", 0.0) or 0.0) <= 0.05
        and float(features.get("sound_rms_mean", 0.0) or 0.0) <= 0.006
    )


def _apply_count_update(record: dict[str, Any], new_count_float: float, warning: str) -> None:
    raw = float(record.get("predicted_people_count", 0.0) or 0.0)
    new_count_float = max(0.0, float(new_count_float))
    if new_count_float >= raw:
        return

    record.setdefault("postprocess", {})
    record["postprocess"]["raw_predicted_people_count"] = raw
    record["postprocess"]["adjusted_by_static_heat_guard"] = True
    record["postprocess"]["static_heat_guard_note"] = warning

    record["predicted_people_count"] = new_count_float
    record["predicted_people_count_rounded"] = int(max(0, round(new_count_float)))
    record["occupancy_level"] = occupancy_level_from_count(record["predicted_people_count_rounded"])
    record["confidence"] = float(_clamp(float(record.get("confidence", 0.0) or 0.0) * 0.82, 0.05, 0.99))

    warnings = record.setdefault("warnings", [])
    if warning not in warnings:
        warnings.append(warning)


def _apply_single_window_static_guard(record: dict[str, Any]) -> None:
    features = record.get("features") or {}
    if not _static_single_window_candidate(features):
        return

    warnings = record.setdefault("warnings", [])
    if "STATIC_HEAT_SOURCE_CANDIDATE_SINGLE_WINDOW" not in warnings:
        warnings.append("STATIC_HEAT_SOURCE_CANDIDATE_SINGLE_WINDOW")

    # A single 5-second window is not enough to say "computer" with high
    # certainty because a seated person may also be still. Apply only a soft
    # adjustment in the 0-vs-1 range.
    raw = float(record.get("predicted_people_count", 0.0) or 0.0)
    if 0.6 <= raw <= 1.4:
        _apply_count_update(
            record,
            max(0.0, raw - 0.35),
            "STATIC_HEAT_SOURCE_SOFT_ADJUSTMENT_SINGLE_WINDOW",
        )


def _apply_sequence_static_heat_guard(records: list[dict[str, Any]]) -> None:
    """Detect a static heat source across a short time sequence.

    File-reading logic is unchanged: this function runs only after records have
    already been read and predicted. It looks for the same unmoving heat source
    over several consecutive windows.
    """
    if len(records) < STATIC_HEAT_SEQUENCE_WINDOWS:
        return

    for idx in range(STATIC_HEAT_SEQUENCE_WINDOWS - 1, len(records)):
        window_slice = records[idx - STATIC_HEAT_SEQUENCE_WINDOWS + 1 : idx + 1]
        feats = [r.get("features") or {} for r in window_slice]
        if not all(_static_single_window_candidate(f) for f in feats):
            continue

        xs = np.array([float(f.get("thermal_main_hot_centroid_x", 0.0) or 0.0) for f in feats])
        ys = np.array([float(f.get("thermal_main_hot_centroid_y", 0.0) or 0.0) for f in feats])
        paths = np.array([float(f.get("thermal_main_hot_centroid_path_px", 0.0) or 0.0) for f in feats])
        static_scores = np.array([float(f.get("thermal_static_heat_score", 0.0) or 0.0) for f in feats])
        sounds = np.array([float(f.get("sound_rms_mean", 0.0) or 0.0) for f in feats])
        radar_targets = np.array([float(f.get("radar_valid_target_count", 0.0) or 0.0) for f in feats])

        stable_across_windows = (
            float(np.std(xs)) <= 0.55
            and float(np.std(ys)) <= 0.55
            and float(np.mean(paths)) <= 0.45
            and float(np.mean(static_scores)) >= 0.86
        )
        no_other_human_evidence = (
            float(np.mean(sounds)) <= 0.006
            and float(np.max(radar_targets)) <= 0.0
        )

        if not (stable_across_windows and no_other_human_evidence):
            continue

        current = records[idx]
        raw = float(current.get("predicted_people_count", 0.0) or 0.0)
        if 0.5 <= raw <= 1.7:
            _apply_count_update(
                current,
                max(0.0, raw - 1.0),
                "STATIC_HEAT_SOURCE_POSSIBLE_COMPUTER_SEQUENCE_GUARD",
            )


class PeopleCountPredictor:
    def __init__(self, artifact_dir: str | Path):
        self.artifact_dir = Path(artifact_dir)
        self.model = joblib.load(self.artifact_dir / "model.joblib")
        meta_path = self.artifact_dir / "metadata.json"
        self.metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        self.feature_names = self.metadata.get("feature_names", FEATURE_NAMES)
        self.model_version = self.metadata.get(
            "model_version",
            PEOPLE_COUNT_MODEL_VERSION,
        )

    def _confidence(self, X: pd.DataFrame, features: dict[str, Any]) -> float:
        try:
            imputer = self.model.named_steps["imputer"]
            forest = self.model.named_steps["model"]
            X_imp = imputer.transform(X)
            tree_preds = np.array([tree.predict(X_imp)[0] for tree in forest.estimators_], dtype=float)
            std = float(np.std(tree_preds))
            max_target = float(self.metadata.get("target_max", 5.0) or 5.0)
            conf = 1.0 - (std / max(max_target + 1.0, 1.0))
        except Exception:
            conf = 0.7

        completeness = float(features.get("quality_completeness", 1.0) or 0.0)
        thermal_available = float(features.get("thermal_available", 0.0) or 0.0)
        sound_available = float(features.get("sound_available", 0.0) or 0.0)
        radar_available = float(features.get("radar_available", 0.0) or 0.0)

        sensor_factor = 0.45 + 0.25 * thermal_available + 0.25 * sound_available + 0.05 * radar_available
        conf = conf * _clamp(completeness, 0.35, 1.0) * _clamp(sensor_factor, 0.2, 1.0)

        if _static_single_window_candidate(features):
            conf *= 0.88

        return float(_clamp(conf, 0.05, 0.99))

    def predict_window(
        self,
        window: dict[str, Any],
        *,
        session_dir: str | Path | None = None,
        relative: dict[str, Any] | None = None,
        thermal_frames: Any | None = None,
        include_features: bool = True,
        apply_single_window_guard: bool = True,
    ) -> dict[str, Any]:
        features = extract_window_features(
            window,
            session_dir=session_dir,
            relative=relative,
            thermal_frames=thermal_frames,
        )
        X = pd.DataFrame([{name: features.get(name, 0.0) for name in self.feature_names}])
        pred_float = float(self.model.predict(X)[0])
        pred_rounded = int(max(0, round(pred_float)))
        confidence = self._confidence(X, features)

        warnings = []
        if features.get("thermal_available", 0.0) == 0.0:
            warnings.append("THERMAL_UNAVAILABLE_OR_REF_MISSING")
        if features.get("sound_available", 0.0) == 0.0:
            warnings.append("SOUND_UNAVAILABLE")
        if features.get("radar_available", 0.0) == 0.0:
            warnings.append("RADAR_UNAVAILABLE_OR_NOT_CONFIGURED")
        if confidence < 0.55:
            warnings.append("LOW_MODEL_CONFIDENCE")

        result = {
            "schema_version": "people_count_prediction.v2",
            "prediction_id": compute_prediction_id(str(window.get("window_id", "")), self.model_version),
            "window_id": window.get("window_id"),
            "room_id": window.get("room_id"),
            "device_id": window.get("device_id"),
            "observed_at": window.get("window_end"),
            "predicted_people_count": pred_float,
            "predicted_people_count_rounded": pred_rounded,
            "occupancy_level": occupancy_level_from_count(pred_rounded),
            "confidence": confidence,
            "model": {
                "name": self.metadata.get(
                    "model_name",
                    PEOPLE_COUNT_MODEL_NAME,
                ),
                "version": self.model_version,
                "feature_schema_version": self.metadata.get("feature_schema_version", PEOPLE_COUNT_FEATURE_SCHEMA_VERSION),
            },
            "warnings": warnings,
        }
        if include_features:
            result["features"] = {name: features.get(name, 0.0) for name in FEATURE_NAMES}

        if apply_single_window_guard:
            _apply_single_window_static_guard(result)

        return result

    def predict_path(
        self,
        input_path: str | Path,
        *,
        out_path: str | Path,
        include_features: bool = False,
        apply_static_heat_guard: bool = True,
    ) -> list[dict[str, Any]]:
        input_path = Path(input_path)
        records: list[dict[str, Any]] = []
        internal_include_features = include_features or apply_static_heat_guard

        # The original input-path/read branches are preserved. Only the in-memory
        # post-processing after prediction is new.
        if input_path.is_dir():
            session_dir = input_path
            windows = read_jsonl(session_dir / "windows.jsonl", strict=False)
            relative_lookup = load_relative_features(session_dir)
            for w in windows:
                records.append(self.predict_window(
                    w,
                    session_dir=session_dir,
                    relative=relative_lookup.get(w.get("window_id")),
                    include_features=internal_include_features,
                ))
        elif input_path.suffix == ".jsonl":
            session_dir = input_path.parent
            relative_lookup = load_relative_features(session_dir)
            for w in read_jsonl(input_path, strict=False):
                records.append(self.predict_window(
                    w,
                    session_dir=session_dir,
                    relative=relative_lookup.get(w.get("window_id")),
                    include_features=internal_include_features,
                ))
        elif input_path.suffix == ".json":
            w = json.loads(input_path.read_text(encoding="utf-8"))
            records.append(self.predict_window(w, session_dir=input_path.parent, include_features=internal_include_features))
        else:
            raise ValueError(f"Unsupported input path: {input_path}")

        if apply_static_heat_guard:
            _apply_sequence_static_heat_guard(records)

        if not include_features:
            for record in records:
                record.pop("features", None)

        out_path = Path(out_path)
        if out_path.suffix == ".jsonl" or len(records) > 1:
            write_jsonl(records, out_path)
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(records[0], indent=2, ensure_ascii=False), encoding="utf-8")
        return records
