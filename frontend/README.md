# Module 4 — Recommendation and Frontend

React/Vite dashboard with mock and real Module 3 API modes. The dashboard is
integrated with the backend contracts; the formal Module 4 ranking adapter is
still pending and the backend currently uses its deterministic stub.

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

The default backend app injects `StubRecommendationAdapter`. It provides stable
ordering for contract and Gate A integration tests, but it is not the formal
Module 4 rule-based recommendation algorithm. Formal scoring, quality factors,
and template/LLM explanations remain Gate C work.

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
npm run gate-a:e2e
npm run build
```

`gate-a:e2e` starts a temporary real backend, feeds it a Module 1 simulated
window through Module 2, and verifies the resulting Dashboard. See
`../tests/integration/README.md` for Python setup.

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
