from __future__ import annotations

import json
from pathlib import Path

from study_space_ml.features import extract_feature_bundle


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_fixture(name: str) -> dict:
    return json.loads((repo_root() / "shared" / "fixtures" / name).read_text(encoding="utf-8"))


def test_quiet_fixture_features() -> None:
    window = load_fixture("sensor_window_quiet.json")
    bundle = extract_feature_bundle(window)
    assert bundle.features["radar_max_target_count"] == 1
    assert bundle.features["sound_rms_mean"] == 0.121
    assert bundle.summary["radar_active_target_count"] == 1
    assert bundle.summary["thermal_hot_region_count"] is None


def test_crowded_fixture_features() -> None:
    window = load_fixture("sensor_window_crowded.json")
    bundle = extract_feature_bundle(window)
    assert bundle.features["radar_max_target_count"] == 3
    assert bundle.features["sound_peak"] == 0.98
