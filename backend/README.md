# Module 3 — Backend and Data Intelligence

FastAPI service for privacy-preserving edge observations, room status/history, deterministic 15/30-minute forecasts, account-bound student preferences, short-lived sensor previews, and the module 4 recommendation adapter boundary.

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

To receive Pi traffic on a trusted LAN, explicitly bind `0.0.0.0` and configure `EDGE_API_TOKEN`. When the token is set, both edge write endpoints require `Authorization: Bearer <token>`. Legacy profile endpoints remain available for the shared module contract; the student application uses authenticated `/api/v1/me/*` preference and recommendation endpoints.

## Important configuration

- `DATABASE_URL`: default `sqlite:///./study_space.db`.
- `STALE_AFTER_SECONDS`: default 30.
- `EDGE_API_TOKEN`: optional; an empty value disables edge write authentication.
- `CORS_ORIGINS`: JSON list of allowed frontend origins, for example `["http://localhost:5173"]`.
- `MAX_REQUEST_BODY_BYTES`: default 128 KiB.
- `SESSION_TTL_SECONDS`: signed-in session lifetime; defaults to 8 hours.
- `ALLOW_ANONYMOUS_DEMO`: keeps the legacy anonymous profile/recommendation
  endpoints available in development; production forces it off.
- `RECOMMENDATION_ADAPTER_MODE`: `rule` by default; `stub` is an explicit
  integration/emergency mode.
- `LLM_ENABLED`: when enabled, uses the configured local Ollama provider only
  to explain an already-computed ranking.
- Retention defaults: observations/forecasts 30 days, recommendation records
  7 days, and explicit room-selection events 90 days.

Never put real secrets in `.env.example`, logs, frontend variables, fixtures, or recommendation records.

## Student accounts and preferences

`POST /api/v1/auth/register` creates a pseudonymous student account. Passwords
use Argon2id, never plaintext. A random session token is held in an HttpOnly,
SameSite=Lax cookie while only its SHA-256 hash is stored; authenticated write
requests require the matching session-bound CSRF token.

Each account owns a manual preference profile and a separate learned profile. The
student dashboard reads and updates it through `GET/PUT /api/v1/me/preferences`
and requests personalized ranking from `POST /api/v1/me/recommendations`.
Only an explicit “Choose this room” action creates an idempotent selection event.
Learning can be disabled or reset, selection history can be deleted, and deleting
the account removes its sessions, selections, and learned preferences.

The backend deliberately has no administrator account or role model. The
frontend's administrator console is a mock-mode demonstration, not a production
authorization boundary.

## Campus weather

`GET /api/v1/weather` combines the public NEA real-time air temperature,
relative humidity, wind speed and two-hour forecast feeds. It selects the
available station nearest NUS, converts wind speed to km/h, derives a feels-like
temperature and caches the latest valid response for short upstream outages.

## Live privacy-safe monitoring

`GET /api/v1/rooms/{room_id}/live` combines the latest room observation with
three short-lived edge feeds:

- `PUT /api/v1/edge/rooms/{room_id}/thermal-preview`
- `PUT /api/v1/edge/rooms/{room_id}/sound-preview`
- `PUT /api/v1/edge/rooms/{room_id}/people-count`

The thermal and sound feeds are held in single-process memory and expire after
ten seconds. The people-count result expires after thirty seconds and accepts
the `people_count_prediction.v1` payload produced by the module 2 random-forest
pipeline. The live response also includes privacy-safe connected thermal-region
boxes. These boxes identify hot regions in the 32 x 24 array; they are not
camera-based identity or face detections.

The prototype read endpoint is not role-protected; deploy it only on the trusted
demonstration network. Production deployment requires a real authorization
model before exposing quantitative telemetry.

## Maintenance and evaluation

```powershell
study-space-api cleanup
study-space-api backtest
```

The backtest is ordered in time and compares the deterministic strategy with current-value persistence. Synthetic seed metrics prove only that the pipeline works; they are not real-world accuracy claims.

Measured results and interpretation are in `PERFORMANCE.md`; the OpenAPI/shared-Schema mapping is in `CONTRACT_ALIGNMENT.md`.

## Module 4 recommendation adapter

`create_app()` now uses `study_space_api.recommendation.RuleBasedRecommendationAdapter`
by default. It ranks rooms with deterministic scoring and template explanations;
the module 3 stub is still kept as the timeout/error fallback for
`/api/v1/recommendations`.

The scoring formula is documented in `../frontend/README.md` and implemented in
`src/study_space_api/recommendation/scoring.py`.

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
