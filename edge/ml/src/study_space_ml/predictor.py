from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, MODEL_NAME, MODEL_VERSION
from .features import extract_window_features
from .io import load_relative_features, read_jsonl, write_jsonl


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


class PeopleCountPredictor:
    def __init__(self, artifact_dir: str | Path):
        self.artifact_dir = Path(artifact_dir)
        self.model = joblib.load(self.artifact_dir / "model.joblib")
        meta_path = self.artifact_dir / "metadata.json"
        self.metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        self.feature_names = self.metadata.get("feature_names", FEATURE_NAMES)
        self.model_version = self.metadata.get("model_version", MODEL_VERSION)

    def _confidence(self, X: pd.DataFrame, features: dict[str, Any]) -> float:
        # For RandomForestRegressor, use disagreement across trees as uncertainty.
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
        return float(_clamp(conf, 0.05, 0.99))

    def predict_window(
        self,
        window: dict[str, Any],
        *,
        session_dir: str | Path | None = None,
        relative: dict[str, Any] | None = None,
        include_features: bool = True,
    ) -> dict[str, Any]:
        features = extract_window_features(window, session_dir=session_dir, relative=relative)
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
            "schema_version": "people_count_prediction.v1",
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
                "name": self.metadata.get("model_name", MODEL_NAME),
                "version": self.model_version,
                "feature_schema_version": self.metadata.get("feature_schema_version", FEATURE_SCHEMA_VERSION),
            },
            "warnings": warnings,
        }
        if include_features:
            result["features"] = {name: features.get(name, 0.0) for name in self.feature_names}
        return result

    def predict_path(
        self,
        input_path: str | Path,
        *,
        out_path: str | Path,
        include_features: bool = False,
    ) -> list[dict[str, Any]]:
        input_path = Path(input_path)
        records: list[dict[str, Any]] = []

        if input_path.is_dir():
            session_dir = input_path
            windows = read_jsonl(session_dir / "windows.jsonl", strict=False)
            relative_lookup = load_relative_features(session_dir)
            for w in windows:
                records.append(self.predict_window(
                    w,
                    session_dir=session_dir,
                    relative=relative_lookup.get(w.get("window_id")),
                    include_features=include_features,
                ))
        elif input_path.suffix == ".jsonl":
            session_dir = input_path.parent
            relative_lookup = load_relative_features(session_dir)
            for w in read_jsonl(input_path, strict=False):
                records.append(self.predict_window(
                    w,
                    session_dir=session_dir,
                    relative=relative_lookup.get(w.get("window_id")),
                    include_features=include_features,
                ))
        elif input_path.suffix == ".json":
            w = json.loads(input_path.read_text(encoding="utf-8"))
            records.append(self.predict_window(w, session_dir=input_path.parent, include_features=include_features))
        else:
            raise ValueError(f"Unsupported input path: {input_path}")

        out_path = Path(out_path)
        if out_path.suffix == ".jsonl" or len(records) > 1:
            write_jsonl(records, out_path)
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(records[0], indent=2, ensure_ascii=False), encoding="utf-8")
        return records
