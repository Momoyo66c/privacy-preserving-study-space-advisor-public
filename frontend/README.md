# Module 4 — Recommendation and Frontend

React/Vite dashboard plus the module 4 recommendation adapter integrated into
`backend/src/study_space_api/recommendation/`.

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

- A required sign-in screen separates student and administrator accounts.
- The language icon switches the complete interface between Simplified Chinese
  and professional English, persists the selection locally and updates the
  document language for assistive technology.
- Student navigation is divided into Home, Rooms, Preferences and Account.
- The student home shows a time-aware greeting, daily sentence, date, live
  NEA weather from the station nearest NUS and personalized qualitative recommendations.
- The backend weather endpoint combines the NEA temperature, humidity, wind and
  two-hour forecast feeds, caches fresh responses and can serve the last valid
  reading during a short upstream outage.
- The room directory uses image-led cards. Opening a room reveals its qualitative
  preference match, current state, exact location, access note and opening hours.
- Nine NUS spaces are included, with official venue details and photographs for
  the ERC and Stephen Riady Centre teaching rooms.
- Student-facing room pages deliberately hide raw scores and sensor values.
- The administrator console keeps quantitative suitability, confidence,
  environment and sensor-health data in separate Overview, Live Monitor, Rooms
  and System views.
- Live Monitor polls the backend once per second, draws a 32 x 24 thermal frame,
  overlays privacy-safe thermal-region boxes, reports the module 2 people-count
  prediction and shows all four module 2 room-state classifications.
- Numeric student preferences are persisted by the backend and immediately
  affect deterministic ranking.

Mock mode includes `student / study1234` and `admin / admin1234` demo accounts.
For real API mode, create student accounts from the interface and configure
`ADMIN_USERNAME` and `ADMIN_PASSWORD` in the backend environment.

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
builder. The UI does not collect names, student IDs or email addresses.

Classroom photographs and factual venue details are sourced from official NUS
pages. See `public/rooms/README.md` for attribution and operational caveats.
