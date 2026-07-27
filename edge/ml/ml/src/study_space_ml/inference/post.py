from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def post_observation(payload: dict[str, Any], *, base_url: str, token: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/v1/edge/observations"
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    auth_token = token if token is not None else os.environ.get("EDGE_API_TOKEN")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {"status": response.status}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST failed {exc.code}: {body}") from exc


def post_observations(payloads: list[dict[str, Any]], *, base_url: str, token: str | None = None, timeout: float = 10.0) -> list[dict[str, Any]]:
    """POST a batch sequentially while preserving backend response order."""

    return [
        post_observation(payload, base_url=base_url, token=token, timeout=timeout)
        for payload in payloads
    ]
