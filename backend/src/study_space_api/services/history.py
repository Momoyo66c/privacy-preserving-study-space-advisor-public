from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from statistics import fmean

from ..models import Observation
from ..schemas import HistoryPoint, OccupancyLevel, RoomState

OCCUPANCY_TO_NUMBER = {"empty": 0, "low": 1, "medium": 2, "high": 3}


def number_to_occupancy(value: float | None) -> str:
    if value is None:
        return OccupancyLevel.UNKNOWN.value
    if value < 0.5:
        return OccupancyLevel.EMPTY.value
    if value < 1.5:
        return OccupancyLevel.LOW.value
    if value < 2.5:
        return OccupancyLevel.MEDIUM.value
    return OccupancyLevel.HIGH.value


def _mean_optional(values: list[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return fmean(present) if present else None


def build_history_points(
    observations: list[Observation],
    start: datetime,
    end: datetime,
    bucket_minutes: int,
    expected_interval_seconds: int,
) -> list[HistoryPoint]:
    bucket_delta = timedelta(minutes=bucket_minutes)
    buckets: dict[int, list[Observation]] = {}
    for observation in observations:
        index = int((observation.observed_at - start).total_seconds() // bucket_delta.total_seconds())
        if index >= 0:
            buckets.setdefault(index, []).append(observation)

    point_count = int((end - start).total_seconds() // bucket_delta.total_seconds())
    points: list[HistoryPoint] = []
    expected = max(1, int(bucket_delta.total_seconds() / expected_interval_seconds))
    for index in range(point_count):
        bucket_start = start + index * bucket_delta
        bucket_end = bucket_start + bucket_delta
        rows = buckets.get(index, [])
        if not rows:
            points.append(
                HistoryPoint(
                    bucket_start=bucket_start,
                    bucket_end=bucket_end,
                    observation_count=0,
                    coverage=0,
                    dominant_room_state=RoomState.UNKNOWN,
                    last_room_state=RoomState.UNKNOWN,
                    occupancy_level=OccupancyLevel.UNKNOWN,
                )
            )
            continue

        valid_occupancy = [OCCUPANCY_TO_NUMBER[row.occupancy_level] for row in rows if row.occupancy_level in OCCUPANCY_TO_NUMBER]
        occupancy_mean = fmean(valid_occupancy) if valid_occupancy else None
        states = [row.room_state for row in rows]
        dominant = sorted(Counter(states).items(), key=lambda item: (-item[1], item[0]))[0][0]
        points.append(
            HistoryPoint(
                bucket_start=bucket_start,
                bucket_end=bucket_end,
                observation_count=len(rows),
                coverage=min(1.0, len(rows) / expected),
                dominant_room_state=dominant,
                last_room_state=rows[-1].room_state,
                occupancy_level=number_to_occupancy(occupancy_mean),
                occupancy_mean=occupancy_mean,
                suitability_mean=_mean_optional([row.suitability_score for row in rows]),
                confidence_mean=_mean_optional([row.confidence for row in rows]),
                sound_rms_mean=_mean_optional([row.feature_summary_json.get("sound_rms_mean") for row in rows]),
                light_lux_mean=_mean_optional([row.feature_summary_json.get("light_lux") for row in rows]),
                temperature_c_mean=_mean_optional([row.feature_summary_json.get("temperature_c") for row in rows]),
                humidity_pct_mean=_mean_optional([row.feature_summary_json.get("humidity_pct") for row in rows]),
            )
        )
    return points
