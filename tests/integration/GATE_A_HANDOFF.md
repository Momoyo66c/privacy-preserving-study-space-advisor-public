# Gate A Handoff

## Outcome

Gate A is automated from the Module 1 deterministic simulator to the real
Dashboard API mode:

```text
Module 1 SensorWindow
  -> Module 2 EdgeObservation
  -> Module 3 ingestion, status, history, and recommendation APIs
  -> Module 4 Dashboard
```

The test uses a temporary SQLite database and synthetic rooms. It does not need
physical sensors, a persistent database, an edge token, or an LLM key.

## Verification

Install the three Python packages, then run the contract/API smoke:

```bash
python -m pip install -e './edge/hardware' -e './edge/ml[dev,thermal]' -e './backend[dev]'
python -m pytest -q tests/integration/test_gate_a.py
```

Install frontend dependencies and Playwright Chromium, then run the browser
flow against the temporary backend:

```bash
cd frontend
npm ci
npx playwright install chromium
npm run gate-a:e2e
```

The repository workflow `.github/workflows/gate-a-ci.yml` runs both paths on
relevant pull requests and pushes to `main`.

## Privacy assertions

The integration test checks that the transmitted `EdgeObservation` contains no
thermal pixel array, raw audio, or radar tracks. The browser receives only the
summary APIs used by the Dashboard.

## Limits and next gates

- Gate A uses deterministic simulation, not the four physical sensors.
- The backend recommendation adapter remains the Module 3 deterministic stub.
- Gate B should validate the real ESP32/Raspberry Pi transport and timing.
- Gate C should integrate the formal Module 4 recommendation adapter.
