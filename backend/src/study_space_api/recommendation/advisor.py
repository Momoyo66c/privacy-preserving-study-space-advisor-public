from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import RecommendationPreferences

SENSITIVE_INPUT = re.compile(
    r"(?:\b[A-Z]\d{7}[A-Z]\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\b\d{7,}\b|\b(?:password|passcode|api[\s_-]?key|access[\s_-]?token|"
    r"cookie|secret)\b)",
    re.IGNORECASE,
)

DISCUSSION_TERMS = (
    "discuss",
    "discussion",
    "group",
    "meeting",
    "presentation",
    "brainstorm",
    "project team",
    "讨论",
    "小组",
    "开会",
    "汇报",
    "组会",
    "合作",
)
QUIET_TERMS = (
    "quiet",
    "focus",
    "concentration",
    "exam",
    "revision",
    "read",
    "write",
    "coding",
    "安静",
    "专注",
    "复习",
    "考试",
    "阅读",
    "写作",
    "编程",
    "自习",
)
LOW_OCCUPANCY_TERMS = (
    "empty",
    "seat",
    "less crowded",
    "low occupancy",
    "人少",
    "空位",
    "不拥挤",
    "低占用",
)
BRIGHT_TERMS = ("bright", "lighting", "well-lit", "明亮", "光线", "照明")
COMFORT_TERMS = (
    "comfortable",
    "temperature",
    "humidity",
    "cool",
    "舒适",
    "温度",
    "湿度",
    "凉快",
)


@dataclass(frozen=True, slots=True)
class InterpretedStudyGoal:
    study_mode: str
    needs: list[str]
    preferences: RecommendationPreferences


def sanitize_study_goal(value: str) -> str:
    normalized = " ".join(value.split())
    if SENSITIVE_INPUT.search(normalized):
        raise ValueError("Study goals must not include identifiers, contact details, credentials, or secrets")
    return normalized


def interpret_study_goal(
    goal: str,
    saved_mode: str,
    saved_preferences: RecommendationPreferences,
) -> InterpretedStudyGoal:
    normalized = goal.casefold()
    discussion = _contains(normalized, DISCUSSION_TERMS)
    quiet = _contains(normalized, QUIET_TERMS)
    if discussion and not quiet:
        study_mode = "discussion"
    elif quiet and not discussion:
        study_mode = "quiet"
    else:
        study_mode = saved_mode

    values = saved_preferences.model_dump()
    needs: list[str] = []
    if quiet:
        needs.append("quiet")
        values["quiet_priority"] = max(values["quiet_priority"], 0.9)
    if discussion:
        needs.append("discussion")
    if _contains(normalized, LOW_OCCUPANCY_TERMS):
        needs.append("low_occupancy")
        values["low_occupancy_priority"] = max(values["low_occupancy_priority"], 0.9)
    if _contains(normalized, BRIGHT_TERMS):
        needs.append("bright")
        values["brightness_priority"] = max(values["brightness_priority"], 0.9)
    if _contains(normalized, COMFORT_TERMS):
        needs.append("comfortable")
        values["comfort_priority"] = max(values["comfort_priority"], 0.9)
    if not needs:
        needs.append("saved_preferences")

    return InterpretedStudyGoal(
        study_mode=study_mode,
        needs=needs,
        preferences=RecommendationPreferences.model_validate(values),
    )


def _contains(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)
