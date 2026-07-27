from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


COUNT_COLUMNS = ["count", "people_count", "person_count", "occupancy_count", "participant_count"]


DEFAULT_LABEL_TO_COUNT = {
    "empty_or_low_activity": 0,
    "quiet_study_recommended": 1,
    "discussion_allowed": 2,
    "not_recommended_noisy_or_crowded": 2,
}


def parse_participant_range(value: Any) -> float | None:
    """Parse participant_range values like '0', '1', '2', '1-2', '2+'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("+"):
        text = text[:-1]
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)", text)
    if match:
        lo, hi = float(match.group(1)), float(match.group(2))
        return (lo + hi) / 2.0
    return None


def load_labels(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"session_id", "window_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"labels.csv missing columns: {sorted(missing)}")
    return df


def normalize_labels(
    labels_df: pd.DataFrame,
    *,
    session_meta_by_id: dict[str, dict],
) -> pd.DataFrame:
    """Return labels with a numeric people_count column.

    The uploaded real dataset has labels.csv with scenario labels only. In that
    case we infer the numeric count from session.json participant_range. If a
    future labels.csv already has count/people_count, that value is used instead.
    """
    df = labels_df.copy()
    count_col = next((c for c in COUNT_COLUMNS if c in df.columns), None)

    counts: list[float | None] = []
    for _, row in df.iterrows():
        count = None
        if count_col is not None:
            raw = row.get(count_col)
            if pd.notna(raw):
                count = float(raw)

        if count is None:
            meta = session_meta_by_id.get(str(row["session_id"]), {})
            count = parse_participant_range(meta.get("participant_range"))

        if count is None and "label" in df.columns:
            count = DEFAULT_LABEL_TO_COUNT.get(str(row["label"]))

        counts.append(count)

    df["people_count"] = counts
    before = len(df)
    df = df.dropna(subset=["people_count"]).copy()
    if len(df) < before:
        print(f"Warning: dropped {before - len(df)} label rows without usable people_count.")
    df["people_count"] = df["people_count"].astype(float)
    return df
