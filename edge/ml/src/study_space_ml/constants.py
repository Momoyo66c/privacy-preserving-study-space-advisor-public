SCHEMA_VERSION = "1.0"
MODEL_NAME = "edge-rule-baseline"
MODEL_VERSION = "0.3.0"
FEATURE_SCHEMA_VERSION = "1.0"

ROOM_STATES = {
    "empty_or_low_activity",
    "quiet_study_recommended",
    "discussion_allowed",
    "not_recommended_noisy_or_crowded",
    "unknown",
}

TRAINING_LABELS = {
    "empty_or_low_activity",
    "quiet_study_recommended",
    "discussion_allowed",
    "not_recommended_noisy_or_crowded",
}

OCCUPANCY_LEVELS = {"empty", "low", "medium", "high", "unknown"}
SENSOR_HEALTH_VALUES = {"ok", "degraded", "offline", "not_configured"}

DEFAULT_ORDERED_FEATURES = [
    "thermal_frame_count",
    "thermal_hot_region_count",
    "thermal_missing",
    "radar_latest_target_count",
    "radar_max_target_count",
    "radar_active_frame_ratio",
    "radar_mean_abs_speed_cm_s",
    "radar_mean_distance_mm",
    "sound_rms_mean",
    "sound_rms_std",
    "sound_peak",
    "sound_missing",
    "light_lux",
    "temperature_c",
    "humidity_pct",
    "environment_missing_count",
    "temperature_comfort_delta",
    "humidity_comfort_delta",
    "quality_completeness",
]
