from study_space_ml import MODEL_VERSION, SCHEMA_VERSION
from study_space_ml.constants import (
    DEFAULT_ORDERED_FEATURES,
    PEOPLE_COUNT_MODEL_NAME,
    SENSOR_HEALTH_VALUES,
)
from study_space_ml.features import extract_feature_bundle
from study_space_ml.people_count_features import extract_window_features


def test_online_and_people_count_interfaces_coexist():
    assert SCHEMA_VERSION == "1.0"
    assert MODEL_VERSION == "0.3.0"
    assert "not_configured" in SENSOR_HEALTH_VALUES
    assert "sound_rms_mean" in DEFAULT_ORDERED_FEATURES
    assert PEOPLE_COUNT_MODEL_NAME == "people-count-random-forest"
    assert callable(extract_feature_bundle)
    assert callable(extract_window_features)
