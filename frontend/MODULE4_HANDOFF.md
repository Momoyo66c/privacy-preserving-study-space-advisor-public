# Module 4 Handoff

## What changed

- Added a React/Vite dashboard in `frontend/` with mock and real API modes.
- Added a real-backend Gate A browser test covering Module 1 simulation through
  Module 2, Module 3 APIs, and the Dashboard.
- Merged the Module 1 live sensor view into the React application. Real mode now
  shows current temperature, humidity, relative light, four-decimal sound RMS
  and the short-lived 32 x 24 thermal preview. Stale or failed live reads clear
  the sensor panel instead of displaying cached values as current.
- Added `/thermal` as a dedicated live MLX90640 monitor. It provides a large
  false-colour canvas, smooth and source-pixel display modes, an optional grid,
  freeze/full-screen controls, room selection and relative-intensity frame
  statistics. Interpolation is explicitly labelled as a display treatment, not
  additional sensor resolution.
- Added `RuleBasedRecommendationAdapter` under the backend adapter boundary.
  It returns bounded score breakdowns for preference learning and uses stable
  fresh/stale/unknown buckets and deterministic tie-breaking.
- Added template explanations plus a privacy-filtered local Ollama provider.
  LLM failure never changes ranking and falls back to the entire template batch.
- Added structured-output, timeout, model-missing, invalid-output, privacy and
  ranking-invariance tests, plus a repeatable real Ollama benchmark.

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

Gate C local verification:

```powershell
cd backend
python -m pytest
python -m pytest -q ..\tests\integration\test_gate_c.py
python scripts\benchmark_llm.py --model qwen3:1.7b --runs 10 --timeout 2
```

Dashboard URL: `http://127.0.0.1:5173`

Thermal monitor URL:
`http://127.0.0.1:5173/thermal?room=room_a&mode=api`

## Configuration

- `VITE_API_MODE=mock` runs the dashboard without a backend.
- `VITE_API_MODE=real` calls the backend at `VITE_API_BASE_URL`.
- `VITE_REFRESH_SECONDS` controls dashboard polling.
- `VITE_LIVE_SENSOR_POLL_MS` controls the selected-room live snapshot interval.
- `VITE_SOUND_POLL_MS` controls current RMS polling and defaults to 250 ms.
- The legacy field URL `/?mode=api` also switches the React app to real mode.
- `RECOMMENDATION_ADAPTER_MODE=rule` selects the formal adapter; `stub` is an
  explicit emergency/integration mode only.
- `LLM_ENABLED=false` keeps formal ranking and uses templates.
- The verified Windows configuration is `LLM_MODEL=qwen3:1.7b`,
  `LLM_TIMEOUT_SECONDS=2.0`, `LLM_CONTEXT_TOKENS=2048`,
  `LLM_MAX_OUTPUT_TOKENS=160` and `LLM_KEEP_ALIVE=30m`.
- Native Windows uses `http://127.0.0.1:11434`; a backend container uses
  `http://host.docker.internal:11434`.

## Recommendation behavior

The formal adapter weights mode match at 30%, quietness at 10%, current
occupancy at 20%, 15/30-minute availability at 15%, calibrated brightness at
10%, comfort at 10% and distance at 5%. User priorities multiply the applicable
base weights; missing or unhealthy dimensions leave the score and the remaining
weights are renormalized. Confidence, freshness and configured-sensor health
then reduce the score. The LLM receives the completed result and cannot alter
any of these values.

## Degradation behavior

- `room_state=unknown`, stale data, low confidence and degraded sensors reduce
  score and remain visible in the UI.
- `LLM_DISABLED`, `LLM_UNAVAILABLE`, `LLM_TIMEOUT` and `LLM_INVALID_OUTPUT`
  produce template explanations without blocking the response.
- Only an exception in the complete formal adapter invokes the visibly marked
  deterministic stub.
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
6. Stop Ollama or set `LLM_ENABLED=false`, request recommendations again and
   show that rank/score are unchanged while the source becomes `template`.

## Known limitations

- Frontend dependencies must be installed before local UI tests can run.
- The first UI version uses native SVG charts to avoid extra runtime packages.
- Distance priority is displayed but disabled until location data is available
  from backend responses.
- Ollama 0.32.4 on the verified RTX 4060 Laptop machine fully offloaded
  `qwen3:1.7b` to the GPU. With the final concise prompt its 10-run provider
  P50/P95 was 1.38/1.40 seconds; the real stale/unknown recommendation endpoint
  was 1.98/2.28 seconds. Cold loading is outside those numbers and must be
  handled by prewarming.
- Model weights are external machine state under `E:\Ollama\models`; they are
  not Git artifacts and CI uses mocked provider responses.
