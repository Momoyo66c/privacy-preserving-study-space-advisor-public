# Module 3 — Backend and Data Intelligence

FastAPI service for privacy-preserving edge observations, room status/history, deterministic 15/30-minute forecasts, anonymous preferences, short-lived thermal previews, and the module 4 recommendation adapter boundary.

## Requirements and installation

- Python 3.11+
- SQLite for the prototype

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Database, seed and run

```powershell
alembic upgrade head
study-space-api seed-demo --reset
uvicorn study_space_api.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI is available at `http://localhost:8000/docs`. The application intentionally uses one worker because thermal previews are process-local and are never persisted.

The sensor dashboard reads `GET /api/v1/rooms/{room_id}/live`. This read-only projection combines the latest module 2 observation summary with the current in-memory thermal preview; it does not create a second storage path or persist thermal values.

To receive Pi traffic on a trusted LAN, explicitly bind `0.0.0.0` and configure `EDGE_API_TOKEN`. When the token is set, both edge write endpoints require `Authorization: Bearer <token>`. Preferences and recommendation reads remain anonymous demo endpoints.

## Important configuration

- `DATABASE_URL`: default `sqlite:///./study_space.db`.
- `STALE_AFTER_SECONDS`: default 30.
- `EDGE_API_TOKEN`: optional; an empty value disables edge write authentication.
- `CORS_ORIGINS`: JSON list of allowed frontend origins, for example `["http://localhost:5173"]`.
- `MAX_REQUEST_BODY_BYTES`: default 128 KiB.
- Retention defaults: observations/forecasts 30 days, recommendation records 7 days.

Never put real secrets in `.env.example`, logs, frontend variables, fixtures, or recommendation records.

## Maintenance and evaluation

```powershell
study-space-api cleanup
study-space-api backtest
```

The backtest is ordered in time and compares the deterministic strategy with current-value persistence. Synthetic seed metrics prove only that the pipeline works; they are not real-world accuracy claims.

Measured results and interpretation are in `PERFORMANCE.md`; the OpenAPI/shared-Schema mapping is in `CONTRACT_ALIGNMENT.md`.

For a real single-worker HTTP smoke test and P95 benchmark:

```powershell
python scripts/benchmark_http.py
```

After installing Docker Desktop, build, start, health-check and remove a temporary container with:

```powershell
.\scripts\docker_smoke.ps1
```

## Tests

```powershell
python -m pytest
alembic downgrade base
alembic upgrade head
```

Fixtures in `../shared/fixtures/` validate module 2 → 3 and module 3 → 4 boundaries. Full API behavior and limitations are documented in `MODULE3_HANDOFF.md`.
