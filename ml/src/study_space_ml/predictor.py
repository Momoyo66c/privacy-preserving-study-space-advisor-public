from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import validate_payload
from .features import extract_features
from .payload import build_edge_observation
from .rules import RuleModel


def default_model_path() -> Path:
    return Path(__file__).resolve().parents[2] / "artifacts" / "rule_model_v0_1_0" / "model.json"


class EdgePredictor:
    """Load a model package and convert SensorWindow records to EdgeObservation."""

    def __init__(self, model_path: str | Path | None = None, *, validate_contracts: bool = True) -> None:
        self.model_path = Path(model_path) if model_path else default_model_path()
        self.model = RuleModel.load(self.model_path)
        self.validate_contracts = validate_contracts

    def predict_window(self, window: dict[str, Any]) -> dict[str, Any]:
        if self.validate_contracts:
            validate_payload(window, "sensor_window.schema.json")
        extracted = extract_features(window)
        prediction = self.model.predict(extracted)
        observation = build_edge_observation(window, extracted, prediction, self.model)
        if self.validate_contracts:
            validate_payload(observation, "edge_observation.schema.json")
        return observation

    def predict_json_line(self, line: str) -> dict[str, Any]:
        return self.predict_window(json.loads(line))


def predict_window(window: dict[str, Any]) -> dict[str, Any]:
    return EdgePredictor().predict_window(window)
