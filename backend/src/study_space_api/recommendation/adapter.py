from __future__ import annotations

from ..adapters.recommendation import AdapterResult, RecommendationContext
from ..adapters.recommendation_stub import StubRecommendationAdapter
from ..config import Settings
from .explanations import (
    ExplanationProvider,
    ExplanationProviderError,
    OllamaExplanationProvider,
)
from .scoring import rank_rooms, recommendation_items


class RuleBasedRecommendationAdapter:
    name = "module4-rule-based-v1"

    def __init__(self, provider: ExplanationProvider | None = None) -> None:
        self.provider = provider

    async def health(self) -> dict[str, str]:
        if self.provider is None:
            return {
                "status": "ok",
                "name": self.name,
                "mode": "template",
                "provider": "disabled",
                "model": "none",
                "llm_status": "disabled",
            }
        provider_status = await self.provider.health()
        return {
            "status": provider_status["status"],
            "name": self.name,
            "mode": "llm" if provider_status["status"] == "ok" else "template",
            "provider": provider_status["provider"],
            "model": provider_status["model"],
            "llm_status": provider_status["llm_status"],
        }

    async def rank(self, context: RecommendationContext) -> AdapterResult:
        ranked = rank_rooms(context)
        items = recommendation_items(ranked)
        score_breakdown = {item.room.room_id: item.breakdown() for item in ranked}
        warnings: list[str] = []
        fallback_reason: str | None = None

        if not context.explanations_enabled:
            return AdapterResult(items, warnings, self.name, score_breakdown)
        if self.provider is None:
            warnings.append("LLM_DISABLED")
            return AdapterResult(
                items,
                warnings,
                self.name,
                score_breakdown,
                fallback_reason="LLM_DISABLED",
            )

        try:
            explanation_items = (
                items[: context.explanation_limit]
                if context.explanation_limit is not None
                else items
            )
            if context.study_goal is None:
                explanations = await self.provider.explain(
                    explanation_items,
                    {room.room_id: room for room in context.rooms},
                    context.request.study_mode,
                )
            else:
                explanations = await self.provider.explain(
                    explanation_items,
                    {room.room_id: room for room in context.rooms},
                    context.request.study_mode,
                    study_goal=context.study_goal,
                )
            items = [
                item.model_copy(
                    update={
                        "explanation": explanations[item.room_id],
                        "explanation_source": "llm",
                    }
                )
                if item.room_id in explanations
                else item
                for item in items
            ]
        except ExplanationProviderError as exc:
            warnings.append(exc.code)
            fallback_reason = exc.code
        except Exception:
            warnings.append("LLM_UNAVAILABLE")
            fallback_reason = "LLM_UNAVAILABLE"
        return AdapterResult(
            items,
            warnings,
            self.name,
            score_breakdown,
            fallback_reason=fallback_reason,
        )


def build_recommendation_adapter(settings: Settings):
    if settings.recommendation_adapter_mode == "stub":
        return StubRecommendationAdapter()
    provider: ExplanationProvider | None = None
    if settings.llm_enabled:
        provider = OllamaExplanationProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            context_tokens=settings.llm_context_tokens,
            max_output_tokens=settings.llm_max_output_tokens,
            keep_alive=settings.llm_keep_alive,
        )
    return RuleBasedRecommendationAdapter(provider)
