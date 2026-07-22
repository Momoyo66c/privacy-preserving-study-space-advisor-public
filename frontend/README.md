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

## Dashboard coverage

- Anonymous study preferences for quiet, discussion, or any mode.
- Deterministic recommendation list with score, confidence, stale and degraded
  labels.
- Room detail with current status, 15/30 minute forecast, history chart and
  32 x 24 thermal preview.
- Mock scenarios for fresh, stale, unknown, degraded, LLM fallback, empty data
  and unavailable thermal preview.
- Non-blocking backend error behavior that preserves the last successful data.

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
# Module 4 — Recommendation and Frontend

负责人在此实现推荐规则、LLM fallback 和 Dashboard；推荐 adapter 的服务端部分按模块 3 约定集成到后端。

开始前阅读：

- `../docs/module-specs/00_SHARED_CONTRACT.md`
- `../docs/module-specs/04_RECOMMENDATION_FRONTEND.md`

实现后补充 mock/真实后端运行、构建、测试和 E2E 演示命令。
