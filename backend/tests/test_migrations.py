from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_empty_database_migrates_to_head(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, check=True, capture_output=True, text=True)
    tables = set(inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names())
    assert {
        "rooms",
        "devices",
        "observations",
        "preference_profiles",
        "forecasts",
        "recommendation_records",
        "users",
        "user_sessions",
        "learned_preference_profiles",
        "room_selection_events",
    } <= tables
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0001"],
        cwd=backend,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    downgraded = set(
        inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names()
    )
    assert "rooms" in downgraded
    assert "users" not in downgraded
    assert "room_selection_events" not in downgraded
