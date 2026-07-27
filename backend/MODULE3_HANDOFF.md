# Module 3 Handoff

## Runtime

- Package: `study_space_api`
- Development API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Default database: `backend/study_space.db` (ignored by Git)
- Python: 3.11+; the full suite, migrations and real Uvicorn HTTP benchmark were verified on Python 3.11.6.

Run `alembic upgrade head`, `study-space-api seed-demo --reset`, then `uvicorn study_space_api.main:app --host 127.0.0.1 --port 8000`.

## Integration boundaries

Module 2 posts the `shared/contracts/edge_observation.schema.json` payload to `/api/v1/edge/observations`. Retries must reuse the same ID and identical payload. Known missing feature summaries may be omitted or null; raw heat frames, audio, and persistent tracks are rejected by the strict model.

Thermal preview uses its separate edge endpoint. It is fixed at 32 x 24 normalized values, held in one process for at most 30 seconds, and never reaches SQLAlchemy, backups, history, recommendations, or ordinary logs.

The dashboard can fetch `GET /api/v1/rooms/{room_id}/live` to receive the latest `RoomStatus`, ephemeral thermal preview, and current sound RMS in one read. It can poll `GET /api/v1/rooms/{room_id}/sound-preview` independently for lower-latency sound display. These endpoints are additive projections only: module 2 continues writing through the existing observation contract, and the Pi bridge writes previews through their dedicated edge endpoints.

Module 4 implements the asynchronous `RecommendationAdapter` protocol in
`study_space_api.recommendation`. The default is now
`module4-rule-based-v1`; the visibly marked deterministic stub is retained only
for an explicit configuration or complete adapter failure. The protocol accepts
server-owned effective preferences and returns per-room score breakdowns.
Module 3 consumes those breakdowns for selection learning.

The rule adapter provides per-candidate `components` in the 0–100 range for
`mode_match`, `quietness`, `current_occupancy`, `future_availability`,
`brightness`, `comfort`, and `distance`; optional matching `weights` are 0–1,
`base_score`/`final_score` are 0–100, and
`confidence_factor`/`freshness_factor`/`health_factor` are 0–1. Module 3 strips
unknown rooms, unknown fields, free text, non-finite values, and out-of-range
values before persistence or learning. Prompts, model responses and raw sensor
inputs are not audit fields.

## Authentication, selection, and learning

- Local usernames are normalized to lowercase and do not require identity attributes.
- Passwords use Argon2id. Sessions use a 32-byte random token in an HttpOnly, SameSite=Lax cookie; only its SHA-256 hash is stored.
- Authenticated writes require a session-bound double-submit CSRF token.
- Failed login attempts are limited per normalized username/IP in a 15-minute in-process window.
- `selection_id` is the idempotency key. Insertion and learned-profile EMA updates share one transaction.
- Evidence compares the chosen room with other valid candidates using the saved score breakdown. Missing/offline sensor dimensions do not create evidence.
- Effective preference is `manual * (1 - influence) + learned * influence`, where `influence=min(count/20,1)*0.40`.
- Learning can be disabled without suppressing selection history. Reset clears derived values only; deleting history clears both events and derived values.
- Selection events are retained for 90 days. Passwords, tokens, cookies, raw audio, thermal frames, tracks, and precise personal location never enter recommendation or selection audit JSON.

## Forecasting

The active strategy uses recent exponential averaging, then same-weekday/time-slot history, current-value persistence, and finally unknown. Unknown observations are missing data, not empty rooms. Forecast results record their method, input time range, confidence, and fallback reason. The `backtest` command uses chronological evaluation and reports MAE/Macro F1 against persistence.

The current synthetic backtest favors persistence over recent averaging. See `PERFORMANCE.md`; do not interpret either result as real-world model quality.

## Privacy and security

- No RGB, raw audio, complete thermal arrays in Observation, or cross-window identity data.
- Logs and recommendation records contain IDs and summaries only.
- Configure `EDGE_API_TOKEN` before accepting writes beyond localhost.
- This prototype has local user authentication but no password recovery, school SSO, administrator console, or multi-tenant role model.

## Known limitations

- SQLite and the in-memory preview cache target a single-process course prototype.
- Login rate-limit state is process-local. Production deployment needs a shared rate-limit store and HTTPS termination.
- Synthetic history is for demonstrations and does not validate forecast accuracy.
- Repository-level CI now includes dedicated Python 3.11 test/migration and Docker health-check jobs; `CI_HANDOFF.md` documents the required branch-protection checks.
- Docker Desktop 4.82.0 / Engine 29.6.1 was smoke-tested locally on 2026-07-16: the Python 3.11 image built, migrations completed, the single Uvicorn worker became healthy, and the temporary container was removed.
- The authentication increment passed all 61 tests on Python 3.11.6. Docker smoke was rerun successfully on 2026-07-22 with Engine 29.6.1: the Python 3.11 image built, Alembic upgraded through `0002`, `/health` returned 200 with `database=ok`, and the temporary container was removed.
- Module 2 must continue to mark missing/unhealthy features accurately so the
  rule adapter can omit and renormalize those dimensions.
- Module 4 now owns the formal ranking and template/Ollama explanation package
  integrated through the existing Module 3 boundary.
