# Module 2: People-Count ML Pipeline

This folder contains the existing room-state edge inference pipeline plus a
first people-count training pipeline for the real sensor dataset. The
people-count code is additive: Gate A continues to use
`study_space_ml.inference.EdgePredictor` and the shared `schema_version=1.0`
observation contract.

It supports:

1. Reading `windows.jsonl` and `relative_features.jsonl`.
2. Reading thermal matrices from `.npz`.
3. Extracting privacy-preserving features.
4. Loading labels from `labels.csv`.
5. Inferring numeric people count from `session.json` when labels only contain scenario labels.
6. Training a `RandomForestRegressor`.
7. Saving a reusable model artifact.
8. Predicting people count for one window, one `windows.jsonl`, or a whole session directory.

## Data layout expected

After unzipping your real data, keep this shape:

```text
data/real_classroom_v1/
├── dataset_manifest.json
├── labels.csv
└── session-*/
    ├── session.json
    ├── windows.jsonl
    ├── relative_features.jsonl
    └── thermal/*.npz
```

## Install locally

From the project root:

```bash
cd edge/ml
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,thermal,sklearn]'
```

Windows PowerShell:

```powershell
cd edge/ml
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,thermal,sklearn]"
```

## Run tests

```powershell
python -m pytest
```

## Inspect the dataset

```powershell
study-space-ml-count-inspect data/real_classroom_v1
```
```
cd D:\college\nus_AIoT\v05
& "python" ./edge/ml/scripts/inspect_dataset.py ./edge/ml/data/real_classroom_v1
```

or without installing entry points:

```powershell
python scripts/inspect_dataset.py data/real_classroom_v1
```

## Extract features

```powershell
study-space-ml-count-features data/real_classroom_v1 \
  --labels data/real_classroom_v1/labels.csv \
  --out outputs/features_with_labels.csv
```
cd D:\college\nus_AIoT\v05
& "python" ./edge/ml/scripts/extract_features.py ./edge/ml/data/real_classroom_v1 --labels ./edge/ml/data/real_classroom_v1/labels.csv --out ./edge/ml/outputs/features_with_labels.csv

## Train the people-count model

```powershell
study-space-ml-count-train data/real_classroom_v1 \
  --labels data/real_classroom_v1/labels.csv \
  --out-dir artifacts/people_count_rf_custom
```
cd D:\college\nus_AIoT\v05
& "python" ./edge/ml/scripts/train_people_count.py ./edge/ml/data/real_classroom_v1 --labels ./edge/ml/data/real_classroom_v1/labels.csv --out-dir ./edge/ml/artifacts/people_count_rf_custom

The artifact folder will contain:

```text
model.joblib
metadata.json
metrics.json
feature_importance.csv
training_table.csv
```

## Predict a full session

```powershell
study-space-ml-count-predict data/real_classroom_v1/session-20260723T103741176Z-ffae7d8c \
  --artifact artifacts/people_count_rf_custom \
  --out outputs/predictions.jsonl
```
cd D:\college\nus_AIoT\v05
& "python" ./edge/ml/scripts/predict_people_count.py ./edge/ml/data/real_classroom_v1/session-20260723T103741176Z-ffae7d8c --artifact ./edge/ml/artifacts/people_count_rf_custom --out ./edge/ml/outputs/predictions.jsonl

## Predict a single window JSON or windows.jsonl

Use an actual `.json` SensorWindow file if you have one. In this repository, the ready-to-use real input is the session's `windows.jsonl` file:

```powershell
study-space-ml-count-predict data/real_classroom_v1/session-20260723T103741176Z-ffae7d8c/windows.jsonl \
  --artifact artifacts/people_count_rf_custom \
  --out outputs/predictions.jsonl
```

If you have your own `.json` SensorWindow file, run:

```powershell
study-space-ml-count-predict path/to/sensor_window.json \
  --artifact artifacts/people_count_rf_custom \
  --out outputs/prediction.json
```

## About the included artifact

This package includes a smoke-test artifact trained on the uploaded real dataset:

```text
artifacts/people_count_rf_real_v0_1/
```
cd D:\college\nus_AIoT\v05
& "python" ./edge/ml/scripts/predict_people_count.py ./edge/ml/path/to/windows.jsonl --artifact ./edge/ml/artifacts/people_count_rf_custom --out ./edge/ml/outputs/predictions.jsonl

Because the dataset has only 4 sessions and 36 windows, use this model as a pipeline baseline, not as a final accuracy benchmark. Retrain after collecting more labelled sessions.

## Feature sources

The first model uses:

- thermal matrix summaries from `.npz`;
- sound summaries from `windows.jsonl` and `relative_features.jsonl`;
- relative light proxy from `relative_features.jsonl`;
- temperature and humidity from `windows.jsonl`;
- quality/completeness and warning count.

Radar is included in the feature schema, but the current real dataset has `radar.health = not_configured`.
