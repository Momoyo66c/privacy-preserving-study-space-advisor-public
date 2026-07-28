# Module 2: People-Count ML Pipeline

This folder contains a complete first version of the ML pipeline for predicting classroom people count from the real sensor dataset.

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
cd ml
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Windows PowerShell:

```powershell
cd ml
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
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
cd D:\college\nus_AIoT\v07\ml
study-space-ml-count-features data/real_classroom_v1 --labels data/real_classroom_v1/labels.csv --out outputs/features_with_labels.csv
```

or without installing entry points:

```powershell
python scripts/inspect_dataset.py data/real_classroom_v1
```

## Extract features

```powershell
study-space-ml-count-features data/real_classroom_v1 --labels data/real_classroom_v1/labels.csv --out outputs/features_with_labels.csv
```
study-space-ml-count-train data/real_classroom_v1 --labels data/real_classroom_v1/labels.csv --out-dir artifacts/people_count_rf_custom

## Train the people-count model

```powershell
study-space-ml-count-train data/real_classroom_v1 \
  --labels data/real_classroom_v1/labels.csv \
  --out-dir artifacts/people_count_rf_custom
```
study-space-ml-count-train data/real_classroom_v1 --labels data/real_classroom_v1/labels.csv --out-dir artifacts/people_count_rf_custom

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
# 先确保输出目录存在
New-Item -ItemType Directory -Path outputs -Force

# 遍历所有 session 文件夹，逐个执行预测
Get-ChildItem data\real_classroom_v1 -Directory -Filter session-* | ForEach-Object {
    $sessionName = $_.Name
    Write-Host "正在预测会话: $sessionName"
    study-space-ml-count-predict "data/real_classroom_v1/$sessionName" `
      --artifact artifacts/people_count_rf_custom `
      --out "outputs/predictions_$sessionName.jsonl"
}

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


## Static Heat Motion Guard

This optimized version adds thermal hotspot movement detection to reduce false positives from laptops/computers.

Use the optimized artifact:

```powershell
python scripts/train_people_count.py data/real_classroom_v1 --labels data/real_classroom_v1/labels.csv --out-dir artifacts/people_count_rf_motion_v0_2
python scripts/predict_people_count.py data/real_classroom_v1/session-20260723T103741176Z-ffae7d8c --artifact artifacts/people_count_rf_motion_v0_2 --out outputs/predictions.jsonl
```

To compare with the guard disabled:

```powershell
python scripts/predict_people_count.py data/real_classroom_v1/session-20260723T103741176Z-ffae7d8c --artifact artifacts/people_count_rf_motion_v0_2 --out outputs/predictions_no_guard.jsonl --no-static-heat-guard
```

See `STATIC_HEAT_MOTION_GUARD.md` for details.

## Live people count and room-state fusion

The production demo entry point composes Module 1 acquisition with Module 2
inference. It consumes the completed five-second window in memory, predicts a
people count, fuses that count with relative sound, relative light, temperature
and humidity, and publishes two privacy-safe payloads:

- `people_count_prediction.v1` for the live numeric count;
- `EdgeObservation` for occupancy, the four-state room label, suitability,
  confidence, feature summaries and sensor health.

```bash
cd /home/pi/privacy-study-space-advisor
PYTHONPATH=edge/hardware/src:edge/ml/src \
  edge/hardware/.venv/bin/python edge/ml/scripts/stream_live.py \
  --config /home/pi/.config/pssa/esp32-hub-windows-mic.local.yaml \
  --backend-url http://WINDOWS_LAN_IP:8000 \
  --people-count-artifact /home/pi/.config/pssa/models/people_count_rf_motion_v0_2
```

The fusion rule uses count plus sound to choose
`empty_or_low_activity`, `quiet_study_recommended`,
`discussion_allowed`, or `not_recommended_noisy_or_crowded`. Relative light
and temperature/humidity change suitability. Missing thermal/count/sound
evidence returns `unknown`; it is never interpreted as an empty room.

Raw MLX90640 arrays are accepted only as an in-process argument to feature
extraction. They are not included in the count payload, Observation, database,
recommendation context, LLM input, or logs. The frontend must use the published
count and must not estimate people by counting heat-map regions.

The current real-data artifact is a demo baseline trained from 36 windows in
four single-session scenarios. Its labels cover only zero to two people.
Leave-one-session evaluation is materially weaker than the within-session
holdout, including failure on the held-out empty session; do not claim
production accuracy or use it for crowded-room capacity enforcement. Collect
independent sessions and wider count labels before deployment.

For the constrained zero-to-four-person demonstration, the live path also
supports a one-shot local thermal calibration file. Calibrate an empty view,
then one and two people for two windows each:

```bash
printf '%s\n' '{"request_id":"empty-1","people_count":0,"sample_windows":1}' \
  > /tmp/pssa-thermal-count-calibration.json
printf '%s\n' '{"request_id":"one-1","people_count":1,"sample_windows":2}' \
  > /tmp/pssa-thermal-count-calibration.json
printf '%s\n' '{"request_id":"two-1","people_count":2,"sample_windows":2}' \
  > /tmp/pssa-thermal-count-calibration.json
```

The process consumes and removes each command. It persists only median
foreground area and excess-heat summaries in
`~/.config/pssa/thermal-count-calibration.json`. Counts three and four are
extrapolated from the one/two-person anchors, capped at four, and require two
consecutive windows before the displayed count changes. Keep the sensor fixed
and avoid complete person-to-person occlusion.

Once a one-person anchor exists, foreground evidence below 35% of the
area/heat-weighted single-person reference is treated as zero. This rejects
tiny warm-chair or sensor-noise remnants instead of forcing every non-zero
region to be one person.

See [MODULE2_HANDOFF.md](MODULE2_HANDOFF.md) for the Pi service and end-to-end
handoff.
