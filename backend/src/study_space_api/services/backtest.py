from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Observation
from .history import OCCUPANCY_TO_NUMBER, number_to_occupancy


def _macro_f1(actual: list[str], predicted: list[str]) -> float:
    labels = ["empty", "low", "medium", "high"]
    scores: list[float] = []
    for label in labels:
        tp = sum(a == label and p == label for a, p in zip(actual, predicted))
        fp = sum(a != label and p == label for a, p in zip(actual, predicted))
        fn = sum(a == label and p != label for a, p in zip(actual, predicted))
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return sum(scores) / len(scores)


def run_backtest(session: Session) -> dict:
    rows = list(session.scalars(select(Observation).order_by(Observation.room_id, Observation.observed_at)))
    by_room: dict[str, list[Observation]] = defaultdict(list)
    for row in rows:
        if row.occupancy_level in OCCUPANCY_TO_NUMBER:
            by_room[row.room_id].append(row)

    actual: list[str] = []
    predicted: list[str] = []
    persistence: list[str] = []
    forecast_errors: list[float] = []
    persistence_errors: list[float] = []
    for room_rows in by_room.values():
        for index in range(3, len(room_rows)):
            prior = room_rows[max(0, index - 12) : index]
            value = sum(OCCUPANCY_TO_NUMBER[row.occupancy_level] for row in prior) / len(prior)
            forecast_level = number_to_occupancy(value)
            actual_level = room_rows[index].occupancy_level
            persistence_level = room_rows[index - 1].occupancy_level
            actual.append(actual_level)
            predicted.append(forecast_level)
            persistence.append(persistence_level)
            forecast_errors.append(abs(value - OCCUPANCY_TO_NUMBER[actual_level]))
            persistence_errors.append(abs(OCCUPANCY_TO_NUMBER[persistence_level] - OCCUPANCY_TO_NUMBER[actual_level]))
    return {
        "samples": len(actual),
        "deterministic": {
            "mae": round(sum(forecast_errors) / len(forecast_errors), 4) if forecast_errors else None,
            "macro_f1": round(_macro_f1(actual, predicted), 4) if actual else None,
        },
        "persistence_baseline": {
            "mae": round(sum(persistence_errors) / len(persistence_errors), 4) if persistence_errors else None,
            "macro_f1": round(_macro_f1(actual, persistence), 4) if actual else None,
        },
        "note": "Synthetic data validates the pipeline only and is not evidence of real-world accuracy.",
    }
