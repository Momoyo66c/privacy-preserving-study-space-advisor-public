from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def observation_endpoint(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/api/v1/edge/observations"):
        return trimmed
    return trimmed + "/api/v1/edge/observations"


def post_observation(observation: dict[str, Any], *, base_url: str, token: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    body = json.dumps(observation, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    effective_token = token if token is not None else os.getenv("EDGE_API_TOKEN")
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"
    request = urllib.request.Request(observation_endpoint(base_url), data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {"status": response.status}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Backend rejected observation with HTTP {exc.code}: {detail}") from exc
