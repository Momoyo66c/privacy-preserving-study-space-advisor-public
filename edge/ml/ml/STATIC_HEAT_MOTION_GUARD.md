# Static Heat Motion Guard

## Purpose

This version adds a guard for the case where a laptop/computer/projector/charger appears as a thermal hotspot and may be mistaken for a person.

## Important constraint

The file-reading logic is not changed.

Unchanged reader files:

```text
src/study_space_ml/io.py
src/study_space_ml/data/io.py
```

The existing `windows.jsonl`, `relative_features.jsonl`, and thermal `.npz` layout is still used.

## New logic

For each thermal window:

1. Load the same `.npz` frames as before.
2. Reshape `(N, 768)` to `(N, 24, 32)`.
3. Find the dominant hot connected component in each thermal frame.
4. Track its centroid across frames.
5. Compute whether that heat source moves.

New features:

```text
thermal_main_hot_centroid_x
thermal_main_hot_centroid_y
thermal_main_hot_centroid_x_std
thermal_main_hot_centroid_y_std
thermal_main_hot_centroid_path_px
thermal_main_hot_centroid_max_step_px
thermal_hot_motion_ratio
thermal_static_heat_score
```

## Decision idea

```text
clear hot source + almost no movement + low sound + no radar target
→ possible static electronics, not necessarily a person
```

Single-window output may include:

```text
STATIC_HEAT_SOURCE_CANDIDATE_SINGLE_WINDOW
STATIC_HEAT_SOURCE_SOFT_ADJUSTMENT_SINGLE_WINDOW
```

Sequence output may include:

```text
STATIC_HEAT_SOURCE_POSSIBLE_COMPUTER_SEQUENCE_GUARD
```

## Run prediction

```powershell
python scripts/predict_people_count.py data/real_classroom_v1/session-xxx `
  --artifact artifacts/people_count_rf_motion_v0_2 `
  --out outputs/predictions.jsonl
```

Disable the guard for comparison:

```powershell
python scripts/predict_people_count.py data/real_classroom_v1/session-xxx `
  --artifact artifacts/people_count_rf_motion_v0_2 `
  --out outputs/predictions_no_guard.jsonl `
  --no-static-heat-guard
```

## Limitation

A very still person may look static in a short window. Therefore the logic is conservative: one still window is only a warning/soft adjustment, while the stronger correction requires the hotspot to stay fixed across several consecutive windows.
