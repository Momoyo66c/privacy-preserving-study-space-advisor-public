from .fusion import FeatureBundle, extract_feature_bundle, feature_vector
from .people_count import (
    as_feature_frame,
    extract_window_features,
    resolve_frames_ref,
    thermal_motion_summary_from_frames,
)

__all__ = [
    "FeatureBundle",
    "extract_feature_bundle",
    "feature_vector",
    "as_feature_frame",
    "extract_window_features",
    "resolve_frames_ref",
    "thermal_motion_summary_from_frames",
]
