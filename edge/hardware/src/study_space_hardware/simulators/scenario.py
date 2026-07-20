"""Scenario definitions shared by all simulated sensors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScenarioName(StrEnum):
    EMPTY = "empty_or_low_activity"
    QUIET = "quiet_study_recommended"
    DISCUSSION = "discussion_allowed"
    CROWDED = "not_recommended_noisy_or_crowded"
    DEGRADED_THERMAL = "degraded_thermal"
    DEGRADED_RADAR = "degraded_radar"
    INTERMITTENT_FAILURE = "intermittent_failure"


@dataclass(frozen=True, slots=True)
class ScenarioProfile:
    thermal_hotspots: int
    radar_targets: int
    sound_rms: float
    light_lux: float
    temperature_c: float
    humidity_pct: float


_PROFILES = {
    ScenarioName.EMPTY: ScenarioProfile(0, 0, 0.035, 380.0, 24.0, 58.0),
    ScenarioName.QUIET: ScenarioProfile(2, 1, 0.12, 430.0, 24.6, 60.0),
    ScenarioName.DISCUSSION: ScenarioProfile(3, 3, 0.34, 410.0, 25.0, 62.0),
    ScenarioName.CROWDED: ScenarioProfile(5, 3, 0.67, 360.0, 26.3, 67.0),
    ScenarioName.DEGRADED_THERMAL: ScenarioProfile(2, 2, 0.18, 420.0, 24.8, 61.0),
    ScenarioName.DEGRADED_RADAR: ScenarioProfile(2, 2, 0.18, 420.0, 24.8, 61.0),
    ScenarioName.INTERMITTENT_FAILURE: ScenarioProfile(
        2, 2, 0.24, 400.0, 25.1, 63.0
    ),
}


def get_profile(name: str | ScenarioName) -> ScenarioProfile:
    try:
        scenario = ScenarioName(name)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ScenarioName)
        raise ValueError(f"unknown simulator scenario {name!r}; choose {allowed}") from exc
    return _PROFILES[scenario]
