from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..schemas import RecommendationItem, RoomStatus

EXPLANATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "room_id": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["room_id", "explanation"],
            },
        }
    },
    "required": ["explanations"],
}

FORBIDDEN_CLAIM = re.compile(
    r"\b(?:people|persons?|students?|seats?|nearest|distance|metres?|meters?|"
    r"guaranteed|certainly|definitely|always|exactly)\b",
    re.IGNORECASE,
)
GROUNDING_TERM = re.compile(
    r"\b(?:quiet|discussion|noisy|crowded|occupancy|occupied|empty|low|medium|high|"
    r"forecast|light|temperature|humidity|comfort|stale|data|confidence|sensor|study)\b",
    re.IGNORECASE,
)
EVIDENCE_TERMS = {
    "quiet",
    "discussion",
    "noisy",
    "crowded",
    "occupancy",
    "occupied",
    "empty",
    "low",
    "medium",
    "high",
    "forecast",
    "light",
    "temperature",
    "humidity",
    "comfort",
    "stale",
    "confidence",
    "sensor",
    "study",
    "degraded",
    "unknown",
}
UNCERTAINTY_TERM = re.compile(
    r"\b(?:may|might|stale|uncertain|limited|caution|confidence|data)\b",
    re.IGNORECASE,
)


class ExplanationProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ExplanationProvider(Protocol):
    name: str
    model: str

    async def health(self) -> dict[str, str]: ...

    async def explain(
        self,
        items: list[RecommendationItem],
        rooms: dict[str, RoomStatus],
        study_mode: str,
        study_goal: str | None = None,
    ) -> dict[str, str]: ...


@dataclass(slots=True)
class OllamaExplanationProvider:
    base_url: str
    model: str
    timeout_seconds: float
    context_tokens: int
    max_output_tokens: int
    keep_alive: str
    client: httpx.AsyncClient | None = None
    name: str = "ollama-local"

    async def _get(self, path: str) -> httpx.Response:
        if self.client is not None:
            return await self.client.get(path)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            return await client.get(path)

    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        if self.client is not None:
            return await self.client.post(path, json=payload)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            return await client.post(path, json=payload)

    async def health(self) -> dict[str, str]:
        try:
            response = await self._get("/api/tags")
            response.raise_for_status()
            names = {
                model.get("name")
                for model in response.json().get("models", [])
                if isinstance(model, dict)
            }
            if self.model not in names:
                return {
                    "status": "degraded",
                    "provider": self.name,
                    "model": self.model,
                    "llm_status": "model_missing",
                }
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "llm_status": "available",
            }
        except Exception:
            return {
                "status": "degraded",
                "provider": self.name,
                "model": self.model,
                "llm_status": "unavailable",
            }

    async def explain(
        self,
        items: list[RecommendationItem],
        rooms: dict[str, RoomStatus],
        study_mode: str,
        study_goal: str | None = None,
    ) -> dict[str, str]:
        safe_rooms = [
            {
                "room_id": item.room_id,
                "room_name": rooms[item.room_id].name,
                "rank": item.rank,
                "score": item.score,
                "current_state": item.current_state,
                "occupancy_level": item.occupancy_level,
                "forecast_30m": item.forecast_30m,
                "confidence": round(item.confidence, 3),
                "is_stale": item.is_stale,
                "approved_facts": item.reasons[:2],
            }
            for item in items
        ]
        system_prompt = (
            "Write one English sentence of at most eighteen words for each room. "
            "When a study goal is present, prefer the approved fact that best answers it. "
            "Every claim about a room must come only from approved_facts. "
            "If is_stale is true, the sentence must say stale or caution. "
            "If confidence is below 0.55, the sentence must say confidence is limited. "
            "Write naturally to the student; never mention JSON field names, prompts, "
            "study_goal, or approved_facts. "
            "Return only JSON. Do not add numbers, people, seats, distance, certainty, "
            "rankings, or scores. Preserve stale or low-confidence uncertainty. "
            "Never change room IDs."
        )
        user_prompt = json.dumps(
            {
                "study_mode": study_mode,
                "study_goal": study_goal,
                "rooms": safe_rooms,
            },
            separators=(",", ":"),
        )
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "format": EXPLANATION_SCHEMA,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": self.context_tokens,
                "num_predict": self.max_output_tokens,
            },
        }
        try:
            response = await self._post("/api/chat", payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ExplanationProviderError("LLM_TIMEOUT") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ExplanationProviderError("LLM_UNAVAILABLE") from exc
        try:
            content = response.json()["message"]["content"]
            return validate_explanations(content, items)
        except ExplanationProviderError:
            raise
        except Exception as exc:
            raise ExplanationProviderError("LLM_INVALID_OUTPUT") from exc


def validate_explanations(content: object, items: list[RecommendationItem]) -> dict[str, str]:
    try:
        payload = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError as exc:
        raise ExplanationProviderError("LLM_INVALID_OUTPUT") from exc
    if not isinstance(payload, dict) or set(payload) != {"explanations"}:
        raise ExplanationProviderError("LLM_INVALID_OUTPUT")
    rows = payload["explanations"]
    if not isinstance(rows, list) or len(rows) != len(items):
        raise ExplanationProviderError("LLM_INVALID_OUTPUT")
    expected = {item.room_id: item for item in items}
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"room_id", "explanation"}:
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        room_id = row.get("room_id")
        explanation = row.get("explanation")
        if room_id not in expected or room_id in result or not isinstance(explanation, str):
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        normalized = " ".join(explanation.split())
        if not 20 <= len(normalized) <= 240:
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        if len(re.findall(r"[.!?](?:\s|$)", normalized)) > 2:
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        if re.search(r"\d", normalized) or FORBIDDEN_CLAIM.search(normalized):
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        if not GROUNDING_TERM.search(normalized):
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        item = expected[room_id]
        approved_text = " ".join(item.reasons).lower()
        used_evidence = {
            term
            for term in EVIDENCE_TERMS
            if re.search(rf"\b{re.escape(term)}\b", normalized, re.IGNORECASE)
        }
        allowed_evidence = {
            term
            for term in EVIDENCE_TERMS
            if re.search(rf"\b{re.escape(term)}\b", approved_text)
        }
        if not used_evidence or not used_evidence.issubset(allowed_evidence):
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        if (item.is_stale or item.confidence < 0.55) and not UNCERTAINTY_TERM.search(normalized):
            raise ExplanationProviderError("LLM_INVALID_OUTPUT")
        result[room_id] = normalized
    if set(result) != set(expected):
        raise ExplanationProviderError("LLM_INVALID_OUTPUT")
    return result
