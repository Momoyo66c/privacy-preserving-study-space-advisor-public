"""Shared constants for the online classifier and optional people-count model.

The unprefixed names are part of the existing Module 2 online-inference
interface.  People-count training uses prefixed names so it cannot silently
change Gate A observation metadata.
"""

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

PEOPLE_COUNT_MODEL_NAME = "people-count-random-forest"
PEOPLE_COUNT_MODEL_VERSION = "0.1.0"
PEOPLE_COUNT_FEATURE_SCHEMA_VERSION = "people-count-features-v1"

PEOPLE_COUNT_FEATURE_NAMES = [
    "thermal_available",
    "thermal_frame_count_window",
    "thermal_frame_count_npz",
    "thermal_mean",
    "thermal_std",
    "thermal_min",
    "thermal_max",
    "thermal_p90",
    "thermal_p95",
    "thermal_p99",
    "thermal_hot_threshold",
    "thermal_hot_area_ratio",
    "thermal_hot_region_count",
    "thermal_temporal_std_mean",
    "thermal_frame_diff_mean",
    "thermal_heat_delta_p95_median",
    "radar_available",
    "radar_sample_count",
    "radar_track_count",
    "radar_valid_target_count",
    "radar_target_count_total",
    "radar_mean_speed_cm_s",
    "radar_max_speed_cm_s",
    "sound_available",
    "sound_rms_mean",
    "sound_rms_std",
    "sound_peak",
    "sound_rms_min",
    "sound_rms_max",
    "sound_sample_count",
    "sound_log_rms_mean",
    "sound_peak_to_rms",
    "light_proxy_available",
    "light_normalized_mean",
    "light_normalized_std",
    "light_adc_mean",
    "light_adc_std",
    "light_sample_count",
    "env_temperature_c",
    "env_humidity_pct",
    "env_temp_missing",
    "env_humidity_missing",
    "env_light_lux_missing",
    "quality_completeness",
    "quality_warning_count",
    "sensor_unavailable_count",
    "sensor_degraded_count",
    "window_seconds_actual",
]

# Compatibility alias for callers of the first people-count branch revision.
FEATURE_NAMES = PEOPLE_COUNT_FEATURE_NAMES
