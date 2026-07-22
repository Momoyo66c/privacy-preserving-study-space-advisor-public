# Module 4 Handoff

## What changed

- Added the formal deterministic recommendation adapter in
  `backend/src/study_space_api/recommendation/`.
- Switched `create_app()` to use `RuleBasedRecommendationAdapter` by default.
- Kept `StubRecommendationAdapter` as the safety fallback for adapter errors.
- Added a React/Vite dashboard in `frontend/` with mock and real API modes.

## URLs and commands

Backend:

```bash
cd backend
python -m pip install -e ".[dev]"
alembic upgrade head
study-space-api seed-demo --reset
uvicorn study_space_api.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Dashboard URL: `http://127.0.0.1:5173`

## Configuration

- `VITE_API_MODE=mock` runs the dashboard without a backend.
- `VITE_API_MODE=real` calls the backend at `VITE_API_BASE_URL`.
- `VITE_REFRESH_SECONDS` controls dashboard polling.
- LLM provider calls are abstracted server-side only. The default provider is
  intentionally not configured and uses template fallback.

## Recommendation behavior

Ranking is always deterministic. LLM text, when later configured, can only
replace the explanation text after validation; it cannot change rank, score,
state, forecast or reasons.

The adapter computes 0-100 subscores for:

- study mode match
- current occupancy
- 30-minute future availability
- brightness comfort
- temperature/humidity comfort

Distance is excluded from normalization until backend room status includes
coordinates or another distance input. Missing environment data is excluded from
weight normalization instead of becoming zero.

Tie-breakers are deterministic: group penalty, score, freshness, confidence,
then `room_id`.

## Degradation behavior

- `room_state=unknown`, stale data, low confidence and degraded sensors reduce
  score and remain visible in the UI.
- LLM timeout, missing provider, exception or unsafe output keeps the ranking
  and uses template explanations with `LLM_TEMPLATE_FALLBACK` or
  `LLM_OUTPUT_REJECTED`.
- Backend connection failures in the frontend preserve the last successful
  dashboard data and show a non-blocking warning.

## Privacy constraints

- No RGB image, identity, raw audio, raw radar frame or full thermal frame is
  sent to the LLM provider.
- The frontend only displays 32 x 24 normalized thermal preview values.
- Preferences use the anonymous `demo-user` profile and do not collect personal
  identifiers.

## Demo flow

1. Open the dashboard in mock mode and show the privacy line.
2. Confirm Quiet Commons ranks first for quiet study.
3. Switch to Discussion and apply preferences; Discussion Hub ranks first.
4. Open Atrium Tables to show stale, degraded and low-confidence labels.
5. Show the history chart and unavailable thermal preview state.
6. Point out `LLM_TEMPLATE_FALLBACK`; recommendations still work without LLM.

## Known limitations

- Frontend dependencies must be installed before local UI tests can run.
- The first UI version uses native SVG charts to avoid extra runtime packages.
- Distance priority is displayed but disabled until location data is available
  from backend responses.
