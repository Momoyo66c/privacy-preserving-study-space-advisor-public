from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from datetime import datetime, timezone
from pathlib import Path

from study_space_api.cli import _seed
from study_space_api.database import Base, Database


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def call(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = dict(headers or {})
    if body:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers=request_headers,
    )
    request_opener = opener or urllib.request.build_opener()
    with request_opener.open(request, timeout=10) as response:
        return json.loads(response.read())


def measure(action, count: int) -> float:
    values: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        action()
        values.append((time.perf_counter() - started) * 1000)
    return round(p95(values), 2)


def wait_until_ready(base_url: str, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Uvicorn exited before becoming ready: {process.returncode}")
        try:
            call(base_url, "GET", "/health")
            return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise TimeoutError("Uvicorn did not become ready")


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "http-benchmark.db"
        database_url = f"sqlite:///{database_path.as_posix()}"
        database = Database(database_url)
        Base.metadata.create_all(database.engine)
        with database.session() as session:
            _seed(session, reset=True)
        database.dispose()

        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment["DATABASE_URL"] = database_url
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "study_space_api.main:app", "--host", "127.0.0.1", "--port", str(port), "--workers", "1", "--log-level", "warning"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        try:
            wait_until_ready(base_url, process)
            counter = 0

            def write_observation() -> dict:
                nonlocal counter
                counter += 1
                payload = {
                    "schema_version":"1.0","observation_id":f"http-benchmark-{counter}","room_id":"room_a","device_id":"http-benchmark-device","observed_at":datetime.now(timezone.utc).isoformat(),"window_seconds":5,"room_state":"quiet_study_recommended","occupancy_level":"low","suitability_score":85,"confidence":0.9,
                    "features":{"thermal_hot_region_count":1,"radar_active_target_count":1,"sound_rms_mean":0.1,"light_lux":420,"temperature_c":24.5,"humidity_pct":60},
                    "sensor_health":{"thermal":"ok","radar":"ok","sound":"ok","environment":"ok"},
                    "model":{"name":"benchmark","version":"1","feature_schema_version":"1.0"},"warnings":[]
                }
                return call(base_url, "POST", "/api/v1/edge/observations", payload)

            recommendation = {"schema_version":"1.0","profile_id":"demo-user","study_mode":"quiet","preferences":{"quiet_priority":0.8,"low_occupancy_priority":0.7,"brightness_priority":0.3,"comfort_priority":0.4,"distance_priority":0.2},"candidate_room_ids":["room_a","room_b","room_c"]}
            authenticated_opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(CookieJar())
            )
            auth = call(
                base_url,
                "POST",
                "/api/v1/auth/register",
                {
                    "schema_version": "1.0",
                    "username": "benchmark.user",
                    "password": "benchmark-password-only",
                },
                opener=authenticated_opener,
            )
            csrf_headers = {"X-CSRF-Token": auth["csrf_token"]}
            selection_counter = 0

            def record_selection() -> dict:
                nonlocal selection_counter
                selection_counter += 1
                return call(
                    base_url,
                    "POST",
                    "/api/v1/me/room-selections",
                    {
                        "schema_version": "1.0",
                        "selection_id": f"00000000-0000-4000-8000-{selection_counter:012d}",
                        "room_id": "room_a",
                        "recommendation_request_id": None,
                        "source": "room_detail",
                    },
                    opener=authenticated_opener,
                    headers=csrf_headers,
                )

            write_observation()
            call(base_url, "GET", "/api/v1/rooms/status")
            call(base_url, "GET", "/api/v1/rooms/room_a/history?hours=24&bucket_minutes=5")
            call(base_url, "POST", "/api/v1/recommendations", recommendation)
            record_selection()
            result = {
                "python": sys.version.split()[0],
                "transport": "Uvicorn HTTP over 127.0.0.1",
                "observation_write_p95_ms": measure(write_observation, 100),
                "room_status_p95_ms": measure(lambda: call(base_url, "GET", "/api/v1/rooms/status"), 50),
                "history_24h_p95_ms": measure(lambda: call(base_url, "GET", "/api/v1/rooms/room_a/history?hours=24&bucket_minutes=5"), 50),
                "recommendation_context_p95_ms": measure(lambda: call(base_url, "POST", "/api/v1/recommendations", recommendation), 50),
                "selection_record_p95_ms": measure(record_selection, 100),
            }
            print(json.dumps(result, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
