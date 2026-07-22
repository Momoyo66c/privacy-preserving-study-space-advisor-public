# Module 4 Handoff

## What changed

- Added a React/Vite dashboard in `frontend/` with mock and real API modes.
- Added a real-backend Gate A browser test covering Module 1 simulation through
  Module 2, Module 3 APIs, and the Dashboard.
- The backend still uses `StubRecommendationAdapter`; the formal deterministic
  Module 4 adapter has not been implemented yet.

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

Gate A verification from the repository root:

```bash
python -m pytest -q tests/integration/test_gate_a.py
cd frontend
npm run gate-a:e2e
```

Dashboard URL: `http://127.0.0.1:5173`

## Configuration

- `VITE_API_MODE=mock` runs the dashboard without a backend.
- `VITE_API_MODE=real` calls the backend at `VITE_API_BASE_URL`.
- `VITE_REFRESH_SECONDS` controls dashboard polling.
- The current backend has no LLM provider integration.

## Recommendation behavior

The current stub sorts deterministically from the backend context so that the
API and UI can be integrated without a Module 4 algorithm. It does not yet
implement the planned weighted subscores, quality factors, bucket ordering, or
template/LLM explanation policy. Those behaviors must be implemented and tested
before Gate C can pass.

## Degradation behavior

- `room_state=unknown`, stale data, low confidence and degraded sensors reduce
  score and remain visible in the UI.
- The mock UI includes LLM fallback states for demonstration; the real backend
  does not yet implement an LLM explanation provider.
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
- Formal Module 4 recommendation ranking is still pending; Gate A intentionally
  verifies the backend stub contract only.
- The first UI version uses native SVG charts to avoid extra runtime packages.
- Distance priority is displayed but disabled until location data is available
  from backend responses.
