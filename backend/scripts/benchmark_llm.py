from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
from datetime import datetime, timedelta, timezone

from study_space_api.adapters.recommendation import RecommendationContext
from study_space_api.recommendation.adapter import RuleBasedRecommendationAdapter
from study_space_api.recommendation.explanations import OllamaExplanationProvider
from study_space_api.schemas import (
    FeatureSummary,
    ForecastResult,
    RecommendationPreferences,
    RecommendationRequest,
    RoomStatus,
)


def percentile(values: list[float], percentile_value: float) -> float:
    position = max(0, math.ceil(len(values) * percentile_value) - 1)
    return sorted(values)[position]


def room(
    room_id: str,
    name: str,
    state: str,
    occupancy: str,
    sound: float,
) -> RoomStatus:
    now = datetime.now(timezone.utc)
    forecasts = [
        ForecastResult(
            room_id=room_id,
            generated_at=now,
            target_at=now + timedelta(minutes=horizon),
            horizon_minutes=horizon,
            predicted_occupancy_level=occupancy,
            confidence=0.88,
            method="benchmark",
            model_version="gate-c",
            input_start_at=now - timedelta(minutes=5),
            input_end_at=now,
            fallback_reason=None,
        )
        for horizon in (15, 30)
    ]
    return RoomStatus(
        room_id=room_id,
        name=name,
        location="Local benchmark",
        observed_at=now,
        received_at=now,
        room_state=state,
        occupancy_level=occupancy,
        suitability_score=80,
        confidence=0.88,
        features=FeatureSummary(
            sound_rms_mean=sound,
            light_lux=480,
            temperature_c=24.2,
            humidity_pct=52,
        ),
        sensor_health={
            "thermal": "ok",
            "radar": "not_configured",
            "sound": "ok",
            "environment": "ok",
        },
        warnings=[],
        data_age_seconds=5,
        is_stale=False,
        forecasts=forecasts,
    )


def benchmark_context() -> RecommendationContext:
    rooms = [
        room("room_a", "Quiet Commons", "quiet_study_recommended", "low", 0.08),
        room("room_b", "Discussion Hub", "discussion_allowed", "medium", 0.43),
        room(
            "room_c",
            "Busy Atrium",
            "not_recommended_noisy_or_crowded",
            "high",
            0.84,
        ),
    ]
    request = RecommendationRequest(
        schema_version="1.0",
        profile_id="local-benchmark",
        study_mode="quiet",
        preferences=RecommendationPreferences(
            quiet_priority=1,
            low_occupancy_priority=1,
            brightness_priority=0.5,
            comfort_priority=0.5,
            distance_priority=0,
        ),
        candidate_room_ids=[item.room_id for item in rooms],
    )
    return RecommendationContext(request=request, rooms=rooms)


def invariant_payload(result) -> list[dict[str, object]]:
    return [
        item.model_dump(exclude={"explanation", "explanation_source"})
        for item in result.recommendations
    ]


async def run(args: argparse.Namespace) -> dict[str, object]:
    context = benchmark_context()
    template_adapter = RuleBasedRecommendationAdapter()
    provider = OllamaExplanationProvider(
        base_url=args.base_url.rstrip("/"),
        model=args.model,
        timeout_seconds=args.timeout,
        context_tokens=args.context_tokens,
        max_output_tokens=args.max_output_tokens,
        keep_alive=args.keep_alive,
    )
    adapter = RuleBasedRecommendationAdapter(provider)
    health = await provider.health()
    if health["status"] != "ok":
        raise RuntimeError(f"Ollama model is not ready: {health}")

    template = await template_adapter.rank(context)
    warmup = await adapter.rank(context)
    if "LLM_TIMEOUT" in warmup.warnings or "LLM_UNAVAILABLE" in warmup.warnings:
        raise RuntimeError(f"LLM warmup failed: {warmup.warnings}")

    latencies: list[float] = []
    accepted_llm_outputs = 0
    invariant_runs = 0
    warning_counts: dict[str, int] = {}
    for _ in range(args.runs):
        started = time.perf_counter()
        result = await adapter.rank(context)
        latencies.append((time.perf_counter() - started) * 1000)
        if all(item.explanation_source == "llm" for item in result.recommendations):
            accepted_llm_outputs += 1
        if invariant_payload(result) == invariant_payload(template):
            invariant_runs += 1
        for warning in result.warnings:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1

    return {
        "model": args.model,
        "base_url": args.base_url,
        "runs": args.runs,
        "provider_health": health,
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "accepted_llm_outputs": accepted_llm_outputs,
        "ranking_invariant_runs": invariant_runs,
        "warning_counts": warning_counts,
        "keep_alive": args.keep_alive,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the local Gate C explanation provider.")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "qwen3:1.7b"))
    parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434"),
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--context-tokens", type=int, default=2048)
    parser.add_argument("--max-output-tokens", type=int, default=160)
    parser.add_argument("--keep-alive", default="30m")
    args = parser.parse_args()
    if args.runs < 3:
        parser.error("--runs must be at least 3")
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
