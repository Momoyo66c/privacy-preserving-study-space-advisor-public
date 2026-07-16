from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("schema_name", "fixture_name"),
    [
        ("edge_observation.schema.json", "edge_observation_valid.json"),
        ("edge_observation.schema.json", "edge_observation_unknown.json"),
        ("thermal_preview.schema.json", "thermal_preview.json"),
        ("preference_profile.schema.json", "preference_profile.json"),
        ("recommendation_request.schema.json", "recommendation_request.json"),
        ("recommendation_response.schema.json", "recommendation_response.json"),
        ("room_metadata.schema.json", "room_metadata.json"),
        ("room_status.schema.json", "room_status_fresh.json"),
        ("room_history.schema.json", "room_history.json"),
        ("forecast_result.schema.json", "forecast_result.json"),
        ("error.schema.json", "error_response.json"),
    ],
)
def test_shared_fixture_matches_schema(schema_name: str, fixture_name: str) -> None:
    schema = json.loads((ROOT / "shared" / "contracts" / schema_name).read_text(encoding="utf-8"))
    fixture = json.loads((ROOT / "shared" / "fixtures" / fixture_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(fixture)


def test_unknown_fixture_does_not_forge_zero_features() -> None:
    fixture = json.loads((ROOT / "shared" / "fixtures" / "edge_observation_unknown.json").read_text(encoding="utf-8"))
    assert fixture["features"]["thermal_hot_region_count"] is None
    assert fixture["occupancy_level"] == "unknown"
