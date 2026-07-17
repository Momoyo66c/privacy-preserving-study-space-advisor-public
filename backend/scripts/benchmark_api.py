from __future__ import annotations

import json
import math
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from study_space_api.cli import _seed
from study_space_api.config import Settings
from study_space_api.database import Base
from study_space_api.main import create_app


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)]


def measure(action, count: int) -> float:
    values: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        response = action()
        response.raise_for_status()
        values.append((time.perf_counter() - started) * 1000)
    return round(p95(values), 2)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "benchmark.db"
        app = create_app(Settings(database_url=f"sqlite:///{database_path.as_posix()}"))
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session() as session:
            _seed(session, reset=True)
        with TestClient(app) as client:
            counter = 0

            def write_observation():
                nonlocal counter
                counter += 1
                now = datetime.now(timezone.utc).isoformat()
                payload = {
                    "schema_version":"1.0","observation_id":f"benchmark-{counter}","room_id":"room_a","device_id":"benchmark-device","observed_at":now,"window_seconds":5,"room_state":"quiet_study_recommended","occupancy_level":"low","suitability_score":85,"confidence":0.9,
                    "features":{"thermal_hot_region_count":1,"radar_active_target_count":1,"sound_rms_mean":0.1,"light_lux":420,"temperature_c":24.5,"humidity_pct":60},
                    "sensor_health":{"thermal":"ok","radar":"ok","sound":"ok","environment":"ok"},
                    "model":{"name":"benchmark","version":"1","feature_schema_version":"1.0"},"warnings":[]
                }
                return client.post("/api/v1/edge/observations", json=payload)

            recommendation_body = {"schema_version":"1.0","profile_id":"demo-user","study_mode":"quiet","preferences":{"quiet_priority":0.8,"low_occupancy_priority":0.7,"brightness_priority":0.3,"comfort_priority":0.4,"distance_priority":0.2},"candidate_room_ids":["room_a","room_b","room_c"]}
            write_observation()
            client.get("/api/v1/rooms/status")
            client.get("/api/v1/rooms/room_a/history?hours=24&bucket_minutes=5")
            client.post("/api/v1/recommendations", json=recommendation_body)
            results = {
                "observation_write_p95_ms": measure(write_observation, 100),
                "room_status_p95_ms": measure(lambda: client.get("/api/v1/rooms/status"), 50),
                "history_24h_p95_ms": measure(lambda: client.get("/api/v1/rooms/room_a/history?hours=24&bucket_minutes=5"), 50),
                "recommendation_context_p95_ms": measure(lambda: client.post("/api/v1/recommendations", json=recommendation_body), 50),
                "environment": "local SQLite, synthetic seed, FastAPI TestClient",
            }
            print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
