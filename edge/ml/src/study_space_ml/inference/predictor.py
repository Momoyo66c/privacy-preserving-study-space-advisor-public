from __future__ import annotations

from pathlib import Path
from typing import Any

from study_space_ml.data.validation import validate_sensor_window
from study_space_ml.features import extract_feature_bundle
from study_space_ml.inference.model import RuleModel
from study_space_ml.inference.payload import build_edge_observation, sensor_health_summary, validate_edge_observation


class EdgePredictor:
    def __init__(self, *, artifact_dir: str | Path | None = None) -> None:
        self.model = RuleModel.load(artifact_dir)

    def predict_window(self, window: dict[str, Any], *, session_dir: str | Path | None = None, strict: bool = True) -> dict[str, Any]:
        validation = validate_sensor_window(window)
        if strict and validation.errors:
            raise ValueError("SensorWindow validation failed: " + "; ".join(validation.errors))
        feature_bundle = extract_feature_bundle(window, session_dir=session_dir)
        health = sensor_health_summary(window)
        model_output = self.model.predict(feature_bundle.features, health)
        payload = build_edge_observation(
            window,
            model=self.model,
            model_output=model_output,
            feature_summary=feature_bundle.summary,
            warnings=[*validation.warnings, *feature_bundle.warnings],
        )
        payload_errors = validate_edge_observation(payload)
        if strict and payload_errors:
            raise ValueError("EdgeObservation validation failed: " + "; ".join(payload_errors))
        return payload
