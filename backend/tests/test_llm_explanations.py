from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from study_space_api.recommendation.adapter import RuleBasedRecommendationAdapter
from study_space_api.recommendation.explanations import (
    ExplanationProviderError,
    OllamaExplanationProvider,
    validate_explanations,
)
from study_space_api.recommendation.scoring import recommendation_items, rank_rooms

from test_recommendation_scoring import context, make_room, standard_rooms


def run(coroutine):
    return asyncio.run(coroutine)


def test_validate_explanations_accepts_grounded_batch() -> None:
    items = recommendation_items(rank_rooms(context("quiet", standard_rooms())))
    content = json.dumps(
        {
            "explanations": [
                {
                    "room_id": item.room_id,
                    "explanation": item.reasons[0],
                }
                for item in items
            ]
        }
    )
    assert set(validate_explanations(content, items)) == {item.room_id for item in items}


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        json.dumps({"explanations": []}),
        json.dumps(
            {
                "explanations": [
                    {
                        "room_id": "other",
                        "explanation": "Quiet study is currently supported by the room data.",
                    }
                ]
            }
        ),
        json.dumps(
            {
                "explanations": [
                    {
                        "room_id": "quiet_room",
                        "explanation": "Quiet study is supported by current room data. " * 20,
                    }
                ]
            }
        ),
        json.dumps(
            {
                "explanations": [
                    {
                        "room_id": "quiet_room",
                        "explanation": "Temperature and humidity are comfortable for quiet study.",
                    }
                ]
            }
        ),
        json.dumps(
            {
                "explanations": [
                    {
                        "room_id": "quiet_room",
                        "explanation": "There are exactly ten people and twenty seats.",
                    }
                ]
            }
        ),
    ],
)
def test_validate_explanations_rejects_invalid_or_unsupported_claims(content: str) -> None:
    items = recommendation_items(rank_rooms(context("quiet", [standard_rooms()[0]])))
    with pytest.raises(ExplanationProviderError, match="LLM_INVALID_OUTPUT"):
        validate_explanations(content, items)


def test_ollama_provider_uses_structured_privacy_safe_request() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
        captured.update(json.loads(request.content))
        rooms = json.loads(captured["messages"][1]["content"])["rooms"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "explanations": [
                                {
                                    "room_id": room["room_id"],
                                    "explanation": room["approved_facts"][0],
                                }
                                for room in rooms
                            ]
                        }
                    )
                }
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )
    provider = OllamaExplanationProvider(
        base_url="http://ollama.test",
        model="qwen3:4b",
        timeout_seconds=2,
        context_tokens=2048,
        max_output_tokens=160,
        keep_alive="30m",
        client=client,
    )
    ranked = rank_rooms(context("quiet", standard_rooms()))
    items = recommendation_items(ranked)
    rooms = {item.room.room_id: item.room for item in ranked}
    assert run(provider.health())["status"] == "ok"
    result = run(provider.explain(items, rooms, "quiet"))
    run(client.aclose())
    assert set(result) == {item.room_id for item in items}
    assert captured["model"] == "qwen3:4b"
    assert captured["think"] is False
    assert captured["format"]["additionalProperties"] is False
    serialized = json.dumps(captured).lower()
    for forbidden in (
        "thermal_preview",
        "thermal_frame",
        "audio",
        "username",
        "cookie",
        "token",
        "selection_history",
    ):
        assert forbidden not in serialized


def test_ollama_timeout_becomes_non_blocking_template_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow local model", request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )
    provider = OllamaExplanationProvider(
        base_url="http://ollama.test",
        model="qwen3:4b",
        timeout_seconds=0.1,
        context_tokens=2048,
        max_output_tokens=160,
        keep_alive="30m",
        client=client,
    )
    adapter = RuleBasedRecommendationAdapter(provider)
    result = run(adapter.rank(context("quiet", standard_rooms())))
    run(client.aclose())
    assert result.warnings == ["LLM_TIMEOUT"]
    assert result.fallback_reason == "LLM_TIMEOUT"
    assert all(item.explanation_source == "template" for item in result.recommendations)


def test_ollama_model_missing_and_disconnect_are_degraded() -> None:
    def missing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "another-model"}]})

    missing_client = httpx.AsyncClient(
        transport=httpx.MockTransport(missing_handler),
        base_url="http://ollama.test",
    )
    missing_provider = OllamaExplanationProvider(
        base_url="http://ollama.test",
        model="qwen3:1.7b",
        timeout_seconds=2,
        context_tokens=2048,
        max_output_tokens=160,
        keep_alive="30m",
        client=missing_client,
    )
    missing_health = run(missing_provider.health())
    run(missing_client.aclose())
    assert missing_health["status"] == "degraded"
    assert missing_health["llm_status"] == "model_missing"

    def disconnected_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    disconnected_client = httpx.AsyncClient(
        transport=httpx.MockTransport(disconnected_handler),
        base_url="http://ollama.test",
    )
    disconnected_provider = OllamaExplanationProvider(
        base_url="http://ollama.test",
        model="qwen3:1.7b",
        timeout_seconds=2,
        context_tokens=2048,
        max_output_tokens=160,
        keep_alive="30m",
        client=disconnected_client,
    )
    assert run(disconnected_provider.health())["llm_status"] == "unavailable"
    result = run(
        RuleBasedRecommendationAdapter(disconnected_provider).rank(
            context("quiet", standard_rooms())
        )
    )
    run(disconnected_client.aclose())
    assert result.warnings == ["LLM_UNAVAILABLE"]
    assert all(item.explanation_source == "template" for item in result.recommendations)


def test_llm_success_changes_only_explanation_fields() -> None:
    class Provider:
        name = "test-provider"
        model = "test-model"

        async def health(self):
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "llm_status": "available",
            }

        async def explain(self, items, rooms, study_mode):
            return {
                item.room_id: "The current room data supports the selected study mode."
                for item in items
            }

    recommendation_context = context("quiet", standard_rooms())
    template = run(RuleBasedRecommendationAdapter().rank(recommendation_context))
    llm = run(RuleBasedRecommendationAdapter(Provider()).rank(recommendation_context))
    assert [
        item.model_dump(exclude={"explanation", "explanation_source"})
        for item in template.recommendations
    ] == [
        item.model_dump(exclude={"explanation", "explanation_source"})
        for item in llm.recommendations
    ]
    assert all(item.explanation_source == "llm" for item in llm.recommendations)


def test_stale_or_low_confidence_llm_text_requires_uncertainty() -> None:
    stale = make_room(
        "stale_room",
        "quiet_study_recommended",
        "low",
        stale=True,
        confidence=0.4,
    )
    items = recommendation_items(rank_rooms(context("quiet", [stale])))
    content = json.dumps(
        {
            "explanations": [
                {
                    "room_id": "stale_room",
                    "explanation": "Quiet study is fully supported by current occupancy.",
                }
            ]
        }
    )
    with pytest.raises(ExplanationProviderError, match="LLM_INVALID_OUTPUT"):
        validate_explanations(content, items)


@pytest.mark.parametrize("index", range(30))
def test_thirty_fixed_llm_scenarios_never_change_ranking(index: int) -> None:
    class ApprovedFactProvider:
        name = "fixed-provider"
        model = "fixed-model"

        async def health(self):
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "llm_status": "available",
            }

        async def explain(self, items, rooms, study_mode):
            return {item.room_id: item.reasons[0] for item in items}

    rooms = standard_rooms()
    rooms[index % len(rooms)].confidence = (index % 10) / 10
    rooms[(index + 1) % len(rooms)].is_stale = index % 2 == 0
    recommendation_context = context(("quiet", "discussion", "any")[index % 3], rooms)
    template = run(RuleBasedRecommendationAdapter().rank(recommendation_context))
    llm = run(
        RuleBasedRecommendationAdapter(ApprovedFactProvider()).rank(
            recommendation_context
        )
    )
    assert [
        item.model_dump(exclude={"explanation", "explanation_source"})
        for item in template.recommendations
    ] == [
        item.model_dump(exclude={"explanation", "explanation_source"})
        for item in llm.recommendations
    ]
