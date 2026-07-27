# Leave-one-session-out Evaluation

## Purpose

For the current dataset, random window split is not reliable because windows in
the same session are very similar. This evaluation holds out one full session at a
time.

## Method

If there are 4 sessions:

```text
Fold 1: train on sessions 2,3,4; test on session 1
Fold 2: train on sessions 1,3,4; test on session 2
Fold 3: train on sessions 1,2,4; test on session 3
Fold 4: train on sessions 1,2,3; test on session 4
```

## Run

```bash
python scripts/leave_one_session_eval.py data/real_classroom_v1 \
  --labels data/real_classroom_v1/labels.csv \
  --out-dir outputs/leave_one_session
```

## Outputs

```text
leave_one_session_predictions.csv
leave_one_session_metrics_by_session.csv
leave_one_session_metrics_overall.json
leave_one_session_confusion_matrix.csv
leave_one_session_report.md
leave_one_session_report.html
charts/
```

## How to report

Use the metrics in `leave_one_session_metrics_overall.json` as the more realistic
accuracy estimate. Do not report same-session prediction accuracy as real
generalization accuracy.
