# Module 3 Performance and Forecast Evaluation

Measured locally on 2026-07-16 with Python 3.11.6, SQLite, the fixed synthetic seed, and a real single-worker Uvicorn server over `127.0.0.1` HTTP. These measurements verify prototype headroom, not deployment capacity.

| Operation | Local P95 | Target | Result |
|---|---:|---:|---|
| Observation write | 32.82 ms | < 300 ms | pass |
| All-room status | 58.34 ms | < 500 ms | pass |
| 24-hour/5-minute history | 57.20 ms | < 1,000 ms | pass |
| Recommendation context + stub | 53.22 ms | < 500 ms | pass |

Run `python scripts/benchmark_http.py` from `backend/` to reproduce the Uvicorn HTTP benchmark. It creates a temporary database, selects a free localhost port, terminates the server afterward, and does not retain sensor or preview data. `benchmark_api.py` remains available as the faster in-process diagnostic.

## Container smoke test

`scripts/docker_smoke.ps1` passed locally on 2026-07-16 with Docker Desktop 4.82.0 and Engine 29.6.1. It built the Python 3.11 image, ran Alembic to head, started one Uvicorn worker, received a healthy database/stub-adapter response, and removed the temporary container.

## Chronological backtest

The fixed 24-hour synthetic seed produced 855 ordered evaluation samples:

| Strategy | MAE | Macro F1 |
|---|---:|---:|
| Recent deterministic average | 0.1521 | 0.8722 |
| Current-value persistence | 0.0819 | 0.9239 |

This synthetic pattern favors persistence. The result validates the evaluation and no-future-data pipeline only; it is not evidence of real occupancy forecast accuracy. No Random Forest strategy is enabled. Real data must be evaluated chronologically and beat the persistence baseline before a learned strategy is selected.
