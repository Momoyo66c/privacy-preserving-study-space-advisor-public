# Module 3 — Backend and Data Intelligence

FastAPI service for privacy-preserving edge observations, room status/history, deterministic 15/30-minute forecasts, local anonymous-user sessions, selection-driven preference learning, short-lived thermal previews, and the module 4 recommendation adapter boundary.

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

OpenAPI is available at `http://localhost:8000/docs`. The application intentionally uses one worker because thermal and sound previews are process-local and are never persisted.

The sensor dashboard reads `GET /api/v1/rooms/{room_id}/live`, which combines the latest module 2 observation summary with current in-memory thermal and sound previews. It can also poll `GET /api/v1/rooms/{room_id}/sound-preview` for the latest RMS window. These read-only projections do not create another storage path or persist preview values.

To receive Pi traffic on a trusted LAN, explicitly bind `0.0.0.0` and configure `EDGE_API_TOKEN`. When the token is set, both edge write endpoints require `Authorization: Bearer <token>`.

## Login and personalized recommendations

The first release uses a local username and password without collecting a name, email address, or student number. Passwords are Argon2id hashes. Browser sessions use an HttpOnly cookie; the database stores only a SHA-256 token hash. Every authenticated POST/PUT/DELETE request after login must send the `X-CSRF-Token` returned at login (or copied from the `pssa_csrf` cookie).

Important authenticated endpoints:

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/me
DELETE /api/v1/me
GET    /api/v1/me/preferences
PUT    /api/v1/me/preferences
POST   /api/v1/me/preferences/reset-learned
POST   /api/v1/me/recommendations
POST   /api/v1/me/room-selections
GET    /api/v1/me/room-selections
DELETE /api/v1/me/room-selections
```

Only an explicit “choose this room” action creates a selection event. The client reuses the same UUID when retrying. Manual preferences retain at least 60% influence; learned history reaches at most 40% after 20 valid evidence events. Learning can be disabled or reset. Deleting all history also clears learned values, and deleting the account cascades to sessions, history, and learned preferences.

Module 3 keeps the deterministic stub as its default adapter. It now accepts authenticated, server-owned effective preferences and an optional score-breakdown result so module 4 can plug in the formal ranking and provide learning evidence. Module 3 does not implement the final ranking algorithm.

The default stub deliberately returns no score breakdown, so selections are recorded but do not change learned preferences until Module 4 injects its adapter. At the persistence boundary, Module 3 removes unknown rooms, free text and unknown keys; it accepts only bounded component scores (`mode_match`, `quietness`, `current_occupancy`, `future_availability`, `brightness`, `comfort`, `distance`), matching weights, final/base scores and quality factors. This prevents raw sensor or prompt data from entering audit storage.

## Important configuration

- `DATABASE_URL`: default `sqlite:///./study_space.db`.
- `STALE_AFTER_SECONDS`: default 30.
- `EDGE_API_TOKEN`: optional; an empty value disables edge write authentication.
- `CORS_ORIGINS`: JSON list of allowed frontend origins, for example `["http://localhost:5173"]`.
- `SESSION_TTL_SECONDS`: browser session lifetime, default 8 hours.
- `SESSION_COOKIE_SECURE`: forced to true when `APP_ENV=production`.
- `ALLOW_ANONYMOUS_DEMO`: keeps legacy profile/recommendation endpoints available in development; forced off in production.
- `MAX_REQUEST_BODY_BYTES`: default 128 KiB.
- Retention defaults: observations/forecasts 30 days, recommendation records 7 days, selection events 90 days.

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
