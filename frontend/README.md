# Module 4: Recommendation and Sensor Dashboard

This React/Vite dashboard serves two jobs. Students can compare rooms and save preferences through the Module 3 API. Operators can inspect the current privacy-safe sensor summary, including a 32 x 24 thermal preview, relative sound RMS, relative light, temperature and humidity.

The backend still uses `StubRecommendationAdapter`. Formal Module 4 scoring, template explanations and the optional LLM provider remain Gate C work.

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
- Mock states for offline, stale, degraded and unavailable previews

The deterministic backend stub supports integration tests. It is not the final personalized ranking algorithm.

## Run checks

```bash
cd backend
python -m pytest

cd ../frontend
npm run test
npm run build
npm run e2e
npm run gate-a:e2e
```

`gate-a:e2e` starts a temporary backend, sends a Module 1 simulated window through Module 2 and verifies the real API in the browser. See [`../tests/integration/README.md`](../tests/integration/README.md).

## Privacy limits

- The UI does not collect names, email addresses or student numbers.
- The browser never receives LLM keys.
- No RGB image, raw audio, raw radar frame or full-temperature thermal matrix reaches recommendation code.
- The heatmap displays only the latest 0-1 normalized 32 x 24 preview.
- Relative sound and light values must not be labeled as calibrated dB or lux.
