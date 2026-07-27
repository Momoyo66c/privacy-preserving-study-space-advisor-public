from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from . import models
from .config import get_settings
from .database import Database
from .repositories import cleanup_expired
from .services.backtest import run_backtest

ROOMS = [
    ("room_a", "ERC The Study", "Education Resource Centre · Level 2", "medium"),
    ("room_b", "NUS-ISS Collaborative Classroom", "NUS-ISS · Level 3", "medium"),
    ("room_c", "NUS-ISS Inspire Theatre", "NUS-ISS · Levels 2–4", "large"),
    ("room_d", "NUS-ISS Seminar Theatre", "NUS-ISS · Level 4", "large"),
    ("room_e", "ERC Seminar Room 1", "ERC Level 2 · UT23-02-07", "medium"),
    ("room_f", "ERC Seminar Room 2", "ERC Level 2 · UT23-02-08", "medium"),
    ("room_g", "ERC Seminar Room 8", "ERC Level 2 · UT23-02-14", "medium"),
    ("room_h", "ERC Activity Learning Room", "ERC Level 2 · UT23-02-13", "large"),
    ("room_i", "SRC Global Learning Room", "Stephen Riady Centre · Level 1 · UT25-01-10", "large"),
]


def _seed(session: object, reset: bool) -> dict[str, int]:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    if reset:
        session.execute(delete(models.Forecast))
        session.execute(delete(models.RecommendationRecord))
        session.execute(delete(models.Observation).where(models.Observation.synthetic.is_(True)))
    for room_id, name, location, capacity in ROOMS:
        room = session.get(models.Room, room_id)
        if room is None:
            session.add(models.Room(id=room_id, name=name, location=location, capacity_band=capacity, active=True, created_at=now, updated_at=now))
        else:
            room.name = name
            room.location = location
            room.capacity_band = capacity
            room.active = True
            room.updated_at = now
        device_id = f"demo-{room_id}"
        if session.get(models.Device, device_id) is None:
            session.add(models.Device(id=device_id, room_id=room_id, model="synthetic", firmware_version="1.0", last_seen_at=now, active=True))
    session.flush()
    if session.get(models.PreferenceProfile, "demo-user") is None:
        session.add(models.PreferenceProfile(profile_id="demo-user", study_mode="quiet", quiet_priority=0.8, low_occupancy_priority=0.7, brightness_priority=0.3, comfort_priority=0.4, distance_priority=0.2, preferred_temperature_c=None, created_at=now, updated_at=now))

    random.seed(20260716)
    created = 0
    for room_index, (room_id, _, _, _) in enumerate(ROOMS):
        scenario = room_index % 3
        for step in range(288):
            observed_at = now - timedelta(minutes=5 * (287 - step))
            hour = observed_at.hour + observed_at.minute / 60
            base = [0.7, 1.5, 2.4][scenario]
            daytime = 0.7 if 9 <= hour <= 21 else -0.5
            wave = 0.4 * math.sin(step / 15 + room_index)
            value = max(0, min(3, base + daytime + wave + random.uniform(-0.15, 0.15)))
            level = "empty" if value < 0.5 else "low" if value < 1.5 else "medium" if value < 2.5 else "high"
            state = ["quiet_study_recommended", "discussion_allowed", "not_recommended_noisy_or_crowded"][scenario]
            score = [88, 68, 35][scenario]
            public_id = f"seed-{room_id}-{observed_at.strftime('%Y%m%dT%H%M%SZ')}"
            if session.query(models.Observation).filter_by(observation_id=public_id).first() is not None:
                continue
            people_count = [2, 4, 7][scenario]
            session.add(models.Observation(observation_id=public_id,payload_hash=hashlib.sha256(public_id.encode()).hexdigest(),room_id=room_id,device_id=f"demo-{room_id}",observed_at=observed_at,received_at=observed_at + timedelta(seconds=1),window_seconds=5,room_state=state,occupancy_level=level,suitability_score=score,confidence=0.86,feature_summary_json={"thermal_hot_region_count": people_count,"radar_active_target_count": people_count,"sound_rms_mean": [0.12, 0.35, 0.72][scenario],"light_lux": [430, 360, 500][scenario],"temperature_c": 24.5,"humidity_pct": 60.0},sensor_health_json={"thermal":"ok","radar":"ok","sound":"ok","environment":"ok"},warnings_json=["synthetic_seed"],model_name="synthetic-demo",model_version="1.0",feature_schema_version="1.0",synthetic=True))
            created += 1
    session.commit()
    return {"rooms": len(ROOMS), "observations_created": created}


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 3 maintenance commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed-demo")
    seed_parser.add_argument("--reset", action="store_true")
    subparsers.add_parser("cleanup")
    subparsers.add_parser("backtest")
    args = parser.parse_args()
    settings = get_settings()
    database = Database(settings.database_url)
    with database.session() as session:
        if args.command == "seed-demo":
            result = _seed(session, args.reset)
        elif args.command == "cleanup":
            now = datetime.now(timezone.utc)
            result = cleanup_expired(session, now - timedelta(days=settings.observation_retention_days), now - timedelta(days=settings.forecast_retention_days), now - timedelta(days=settings.recommendation_retention_days))
            session.commit()
        else:
            result = run_backtest(session)
    database.dispose()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
