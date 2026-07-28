from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from study_space_api.schemas import (
    AuthCredentials,
    AuthSessionResponse,
    AuthenticatedRecommendationRequest,
    DeleteResult,
    MePreferenceUpdate,
    MePreferenceResponse,
    PeopleCountPrediction,
    RoomSelectionAccepted,
    RoomSelectionHistoryResponse,
    RoomSelectionRequest,
    StudyAdvisorRequest,
    StudyAdvisorResponse,
    UserResponse,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("schema_name", "fixture_name"),
    [
        ("edge_observation.schema.json", "edge_observation_valid.json"),
        ("edge_observation.schema.json", "edge_observation_unknown.json"),
        ("thermal_preview.schema.json", "thermal_preview.json"),
        (
            "people_count_prediction.schema.json",
            "people_count_prediction.json",
        ),
        ("preference_profile.schema.json", "preference_profile.json"),
        ("recommendation_request.schema.json", "recommendation_request.json"),
        ("recommendation_response.schema.json", "recommendation_response.json"),
        ("room_metadata.schema.json", "room_metadata.json"),
        ("room_status.schema.json", "room_status_fresh.json"),
        ("room_history.schema.json", "room_history.json"),
        ("forecast_result.schema.json", "forecast_result.json"),
        ("error.schema.json", "error_response.json"),
        ("auth_credentials.schema.json", "auth_credentials.json"),
        ("auth_session_response.schema.json", "auth_session_response.json"),
        (
            "authenticated_recommendation_request.schema.json",
            "authenticated_recommendation_request.json",
        ),
        ("me_preferences.schema.json", "me_preferences.json"),
        ("me_preference_update.schema.json", "me_preference_update.json"),
        ("room_selection_request.schema.json", "room_selection_request.json"),
        ("room_selection_accepted.schema.json", "room_selection_accepted.json"),
        ("room_selection_history.schema.json", "room_selection_history.json"),
        ("user_response.schema.json", "user_response.json"),
        ("delete_result.schema.json", "delete_result.json"),
        ("study_advisor_request.schema.json", "study_advisor_request.json"),
        ("study_advisor_response.schema.json", "study_advisor_response.json"),
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


@pytest.mark.parametrize(
    ("model", "fixture_name"),
    [
        (AuthCredentials, "auth_credentials.json"),
        (AuthSessionResponse, "auth_session_response.json"),
        (
            AuthenticatedRecommendationRequest,
            "authenticated_recommendation_request.json",
        ),
        (MePreferenceResponse, "me_preferences.json"),
        (MePreferenceUpdate, "me_preference_update.json"),
        (RoomSelectionRequest, "room_selection_request.json"),
        (RoomSelectionAccepted, "room_selection_accepted.json"),
        (RoomSelectionHistoryResponse, "room_selection_history.json"),
        (UserResponse, "user_response.json"),
        (DeleteResult, "delete_result.json"),
        (StudyAdvisorRequest, "study_advisor_request.json"),
        (StudyAdvisorResponse, "study_advisor_response.json"),
        (PeopleCountPrediction, "people_count_prediction.json"),
    ],
)
def test_authenticated_fixtures_match_pydantic(model: type, fixture_name: str) -> None:
    fixture = json.loads(
        (ROOT / "shared" / "fixtures" / fixture_name).read_text(encoding="utf-8")
    )
    model.model_validate(fixture)
