# Module 2 - Edge ML rule model bridge

This package is a first, contract-safe ML integration for Module 2. It is intentionally rule-based because the project has not started collecting real data yet. The goal is to make the full interface runnable now:

```text
Module 1 windows.jsonl -> edge/ml rule predictor -> EdgeObservation JSON/JSONL -> backend POST /api/v1/edge/observations
```

The rule model is not a validated real-data classifier. It is a reproducible baseline and integration bridge. Replace `artifacts/rule_model_v0_1_0/model.json` with a trained model package later while keeping the same `predict_window()` interface.

## Install

From the repository root:

```bash
cd edge/ml
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
```

## Predict one shared fixture

```bash
study-space-ml-predict-window ../../shared/fixtures/sensor_window_quiet.json --out /tmp/edge_observation.json
cat /tmp/edge_observation.json
```

## Predict Module 1 JSONL output

Module 1 writes each `SensorWindow` as one line in `data/sessions/<session_id>/windows.jsonl`. Run:

```bash
study-space-ml-predict-jsonl ../../data/sessions/<session_id>/windows.jsonl --out /tmp/edge_observations.jsonl
```

A session directory is also accepted:

```bash
study-space-ml-predict-jsonl ../../data/sessions/<session_id> --out /tmp/edge_observations.jsonl
```

## Post observations to backend

Start the backend and seed demo rooms first. Then:

```bash
study-space-ml-post-observation /tmp/edge_observations.jsonl --url http://127.0.0.1:8000
```

If the backend has `EDGE_API_TOKEN` configured:

```bash
export EDGE_API_TOKEN='your-token'
study-space-ml-post-observation /tmp/edge_observations.jsonl --url http://127.0.0.1:8000
```

## Labels for future real data

Keep runtime sensor windows privacy-safe and unlabeled. Put labels in a separate CSV, for example `edge/ml/data/labels.csv`:

```csv
session_id,window_id,label,annotator,notes
session-20260716T063000Z-a1b2c3d4,room_a-20260716T063005.000Z,quiet_study_recommended,manual,
```

Valid labels are:

- `empty_or_low_activity`
- `quiet_study_recommended`
- `discussion_allowed`
- `not_recommended_noisy_or_crowded`

`unknown` is only produced by online degradation logic and should not be a normal training label.

Validate a data folder and separate labels file:

```bash
study-space-ml-validate-dataset ../../data/sessions --labels data/labels.csv
```

## Test

```bash
cd edge/ml
python -m pytest
```
