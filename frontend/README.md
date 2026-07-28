# Module 4 — Recommendation and Frontend

React/Vite dashboard plus the module 4 recommendation adapter integrated into
`backend/src/study_space_api/recommendation/`.

The UI applies one presentation-only room-state override: when the calibrated
relative light summary is below `0.2`, every current-state label displays
`Closed`. The shared backend `room_state` enum and recommendation inputs remain
unchanged; a value of exactly `0.2` does not trigger the override.

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Mock mode is the default:

```text
VITE_API_MODE=mock
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_REFRESH_SECONDS=10
VITE_LIVE_SENSOR_POLL_MS=1000
```

Set `VITE_API_MODE=real` after the FastAPI backend is running at
`VITE_API_BASE_URL`.

## Temporary public demo

For a temporary HTTPS tunnel, run a second Vite process with the dedicated
same-origin proxy configuration:

```powershell
cd frontend
npx vite --config vite.public.config.ts
```

Expose only `http://127.0.0.1:5174` through the tunnel. This configuration
forces real API mode, proxies browser API requests to the local backend, and
returns `403` for every `/api/v1/edge/*` request so public viewers cannot write
sensor observations or thermal previews. It is a demonstration boundary, not a
production deployment or authentication gateway.

## Backend recommendation adapter

The default backend app now injects
`RuleBasedRecommendationAdapter`, which implements the module 4 deterministic
ranking. The module 3 stub remains only as the API-level fallback if the formal
adapter raises or times out.

Scoring uses this formula:

```text
dimension_weight = base_weight * (0.5 + user_priority)
normalized_score = sum(subscore * normalized_weight)
final_score = normalized_score * freshness_confidence_factor
```

Missing dimensions, such as distance or unavailable environment readings, are
removed before weight normalization. They are not treated as zero.

The first implementation scores mode match, current occupancy, 30-minute
availability, brightness, and temperature/humidity comfort. Distance is disabled
until room coordinates are available in the module 3 status response.

## Application structure

- Real API mode requires a local pseudonymous student account. Mock mode also
  exposes a clearly separated administrator-console demonstration.
- The language icon switches the complete interface between Simplified Chinese
  and professional English, persists the selection locally and updates the
  document language for assistive technology.
- Student navigation is divided into Home, Rooms, AI Advisor, Preferences and
  Account.
- The student home shows a time-aware greeting, daily sentence, date, live
  NEA weather from the station nearest NUS and personalized qualitative recommendations.
- The backend weather endpoint combines the NEA temperature, humidity, wind and
  two-hour forecast feeds, caches fresh responses and can serve the last valid
  reading during a short upstream outage.
- The room directory uses image-led cards. Opening a room reveals its qualitative
  preference match, current state, exact location, access note and opening hours.
- Nine NUS spaces are included, with official venue details and photographs for
  the ERC and Stephen Riady Centre teaching rooms.
- Every room card uses a repository-local image and falls back to
  `/rooms/nus-erc-alr.jpg` if an asset cannot be decoded; the UI has no runtime
  image-host dependency.
- Student-facing room pages deliberately hide raw scores and sensor values.
- The administrator console keeps quantitative suitability, confidence,
  environment and sensor-health data in separate Overview, Live Monitor, Rooms
  and System views.
- Live Monitor polls the backend once per second, draws a 32 x 24 thermal frame,
  overlays privacy-safe thermal-region boxes, reports the module 2 people-count
  prediction and shows all four module 2 room-state classifications.
- The dedicated `/thermal` view renders the short-lived MLX90640 preview in a
  stable responsive stage. Its backing canvas observes the stage rather than
  itself and is capped at 4096 pixels per edge to prevent resize feedback loops.
- Numeric student preferences are persisted by the backend and immediately
  affect deterministic ranking.
- AI Advisor shows the current saved-preference top three and accepts a
  transient description of today's task. Deterministic keyword interpretation
  adjusts only the current request; the formal adapter ranks rooms and the
  local LLM explains the best grounded match.
- Explicit “Choose this room” actions are recorded idempotently and can update a
  learned preference profile. The Account page can disable learning, reset the
  learned values, delete selection history, retry a failed selection with the
  same ID, or delete the account.

Mock mode includes `student / study12345` and `admin / admin12345` demo accounts.
For real API mode, create a student account from the interface. The local
administrator demo is also available while real room data is enabled, but it
does not create a backend administrator role and must not be treated as a
production authorization boundary.

## Tests

```bash
cd backend
python -m pytest

cd ../frontend
npm run test
npm run e2e
npm run build
```

## Privacy notes

The browser never receives LLM keys. Thermal previews are displayed only as
short-lived 32 x 24 normalized values and are never sent to the LLM request
builder. The UI does not collect names, student IDs or email addresses. It
records only explicit room choices, and users can disable learning, erase their
history, or delete their account.

AI Advisor goals are limited to 500 characters, privacy-filtered before the
local model call, and not stored in recommendation audits or preference
profiles. The LLM cannot change deterministic room ranking.

Classroom photographs and factual venue details are sourced from official NUS
pages. See `public/rooms/README.md` for attribution and operational caveats.
