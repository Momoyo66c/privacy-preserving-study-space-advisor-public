# Module 2 — Sensor Interface, Features, and Edge ML Pipeline

This module turns Module 1 `SensorWindow` records into privacy-preserving `EdgeObservation` payloads.

Current baseline:

```text
shared fixture / windows.jsonl / session directory
  -> sensor-interface validation
  -> feature extraction
  -> deterministic rule model baseline
  -> EdgeObservation JSON / JSONL
  -> optional POST to backend /api/v1/edge/observations
```

The baseline is deterministic because real labelled data is still being collected. It is suitable for integration testing and demos, but it is not a real-data-trained performance claim.

## What Module 1 gives us

Module 2 reads either:

```text
shared/fixtures/sensor_window_*.json
```

or a collected session:

```text
data/sessions/<session_id>/
├── session.json
├── windows.jsonl
├── thermal/
│   └── <window_id>.npz
└── checksums.json
```

Each `windows.jsonl` line is one `SensorWindow` with:

```text
thermal.health + frame_count + optional frames_ref
radar.health + sample_count + tracks[].targets[]
sound.health + rms_mean + rms_std + peak
environment.light_lux + temperature_c + humidity_pct
quality.completeness + warnings
```

See `SENSOR_INTERFACE_AUDIT.md` for the detailed field-by-field interface check.

## Local setup

From the repository root:

```bash
cd edge/ml
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

Windows PowerShell:

```powershell
cd edge/ml
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

To extract thermal features from Module 1 NPZ files, install the optional thermal extra:

```bash
python -m pip install -e '.[dev,thermal]'
```

## Inspect the sensor interface

For a real/simulated Module 1 session:

```bash
study-space-ml-interface ../../data/sessions/<session_id>
```

This reports the detected file path, first-window shape, sensor health counts, and validation errors/warnings.

## Run on shared fixtures

```bash
study-space-ml-predict-window ../../shared/fixtures/sensor_window_quiet.json --out /tmp/edge_observation.json
cat /tmp/edge_observation.json
```

## Run on Module 1 `windows.jsonl`

```bash
study-space-ml-validate ../../data/sessions/<session_id>/windows.jsonl
study-space-ml-features ../../data/sessions/<session_id>/windows.jsonl --out /tmp/features.jsonl
study-space-ml-predict-jsonl ../../data/sessions/<session_id>/windows.jsonl --out /tmp/edge_observations.jsonl
```

You can also pass the session directory directly:

```bash
study-space-ml-run-pipeline ../../data/sessions/<session_id> \
  --features-out /tmp/features.jsonl \
  --observations-out /tmp/edge_observations.jsonl
```

## Post observations to the backend

Start the backend first and seed demo rooms. Then:

```bash
study-space-ml-post /tmp/edge_observations.jsonl --url http://127.0.0.1:8000
```

With write auth enabled:

```bash
export EDGE_API_TOKEN="replace-with-token"
study-space-ml-post /tmp/edge_observations.jsonl --url http://127.0.0.1:8000
```

## Labels for future training

Runtime sensor windows must not contain labels. Put labels here:

```text
edge/ml/data/labels.csv
```

Expected columns:

```csv
session_id,window_id,label,annotator,notes
```

Allowed training labels:

```text
empty_or_low_activity
quiet_study_recommended
discussion_allowed
not_recommended_noisy_or_crowded
```

`unknown` is only produced by online degradation logic. It should not be used as a normal training label.

## Recalibrate rule thresholds once labels exist

```bash
study-space-ml-train-rule \
  --windows ../../data/sessions/<session_id>/windows.jsonl \
  --labels data/labels.csv \
  --out artifacts/rule_model_custom
```

Then run inference with the new artifact:

```bash
study-space-ml-predict-jsonl ../../data/sessions/<session_id>/windows.jsonl \
  --artifact artifacts/rule_model_custom \
  --out /tmp/edge_observations.jsonl
```

## Privacy boundary

- The backend payload only contains aggregate feature summaries.
- Raw audio is never required or loaded.
- Radar `target_id` values are not used as cross-window identities.
- Thermal NPZ files are only read locally for aggregate features when available.
