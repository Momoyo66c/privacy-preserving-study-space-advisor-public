# Module 4: Recommendation and Sensor Dashboard

This React/Vite dashboard serves two jobs. Students can compare rooms and save preferences through the Module 3 API. Operators can inspect the current privacy-safe sensor summary, including a 32 x 24 thermal preview, relative sound RMS, relative light, temperature and humidity.

The backend now uses Module 4's deterministic `RuleBasedRecommendationAdapter`
by default. Ranking never depends on an LLM. Template explanations are always
available, and an optional local Ollama provider may rewrite only the
already-approved structured reasons.

## Start the dashboard

Requirements:

- Node.js 22
- A running FastAPI backend for real mode

Install and start:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`.

The dedicated thermal monitor is available at:

```text
http://127.0.0.1:5173/thermal?room=room_a&mode=api
```

It renders the current normalized MLX90640 preview as a large false-colour
canvas. Smooth mode interpolates the 32 x 24 source for readability; sensor
pixel mode shows the original grid. Neither mode creates additional sensor
detail or converts relative values into absolute temperature.

Mock mode is the default:

```text
VITE_API_MODE=mock
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_REFRESH_SECONDS=10
VITE_LIVE_SENSOR_POLL_MS=1000
VITE_SOUND_POLL_MS=250
```

Set `VITE_API_MODE=real` after the backend is ready. The existing field URL `http://127.0.0.1:5173/?mode=api` also selects real mode, which keeps old Raspberry Pi handoff commands valid.

## Real sensor display

The React UI uses the current Module 3 endpoints:

| Endpoint | Purpose | Browser interval |
|---|---|---|
| `GET /api/v1/rooms/{room_id}/live` | Latest room summary and in-memory thermal/sound previews | `VITE_LIVE_SENSOR_POLL_MS`, default 1000 ms |
| `GET /api/v1/rooms/{room_id}/sound-preview` | Current HW-485 RMS window | `VITE_SOUND_POLL_MS`, default 250 ms |
| `GET /api/v1/rooms/{room_id}/history` | Aggregated historical trend | Main dashboard refresh |

The sensor panel hides preview values when the room is stale or the request fails. It never substitutes the last reading as live data. Sound uses the current RMS window, not a release envelope or historical peak. HW-486 remains an uncalibrated relative value unless `light_lux` is present.

Thermal previews contain 768 normalized values. They stay in process memory for at most 30 seconds and never enter history, recommendations or the LLM request builder.

## Recommendation coverage

- Anonymous quiet, discussion and any-mode preferences
- Authenticated local accounts, manual preferences and explicit room selection
- Deterministic recommendation list with confidence, stale and degraded labels
- Student and operations views
- History, forecast and low-resolution thermal display
- Dedicated full-screen thermal monitor with smooth/pixel modes, grid, freeze,
  room selection and relative-intensity scale
- Mock states for offline, stale, degraded and unavailable previews

The formal adapter combines mode match, quietness, current and forecast
occupancy, calibrated light and temperature/humidity comfort. Missing inputs
leave the calculation and the remaining weights are renormalized. Distance
remains excluded until the backend receives an approved coarse location input.
Fresh, stale and unknown/mode-mismatch rooms are bucketed before deterministic
tie-breaking.

## Local LLM explanations

The Windows demo uses Ollama on loopback only. On the verified RTX 4060 Laptop
machine the model directory is `E:\Ollama\models` and the selected model is
`qwen3:1.7b` Q4_K_M. `qwen3:4b` remains installed for comparison but exceeded
the two-second explanation target in three consecutive benchmark groups.

Backend configuration:

```text
RECOMMENDATION_ADAPTER_MODE=rule
LLM_ENABLED=true
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen3:1.7b
LLM_TIMEOUT_SECONDS=2.0
LLM_KEEP_ALIVE=30m
```

When the backend runs in Docker, use
`LLM_BASE_URL=http://host.docker.internal:11434`. Ollama is never called by the
browser. See [`../docs/GATE_C_LOCAL_LLM.md`](../docs/GATE_C_LOCAL_LLM.md) for
installation, benchmark and fallback verification.

## Run checks

```bash
cd backend
python -m pytest
python scripts/benchmark_llm.py --runs 10 --timeout 2

cd ../frontend
npm run test
npm run build
npm run e2e
npm run gate-a:e2e

cd ..
python -m pytest -q tests/integration/test_gate_c.py
```

`gate-a:e2e` starts a temporary backend, sends a Module 1 simulated window through Module 2 and verifies the real API in the browser. See [`../tests/integration/README.md`](../tests/integration/README.md).

## Privacy limits

- The UI does not collect names, email addresses or student numbers.
- The browser never receives LLM keys.
- No RGB image, raw audio, raw radar frame or full-temperature thermal matrix reaches recommendation code.
- The LLM request contains only room IDs/names, final rank/score, approved
  reasons, state enums, forecast, confidence, stale and non-identifying
  effective preferences.
- The heatmap displays only the latest 0-1 normalized 32 x 24 preview.
- Relative sound and light values must not be labeled as calibrated dB or lux.
