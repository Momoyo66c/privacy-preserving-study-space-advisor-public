# Model Card: room-state-rule-baseline v0.1.0

## Purpose

This is a deterministic rule baseline for integrating Module 2 before real data collection starts.

## Intended use

- Verify `SensorWindow -> EdgeObservation` conversion.
- Test JSONL ingestion from Module 1.
- Test backend posting and idempotent retry behavior.
- Provide a transparent baseline to compare against future Random Forest training.

## Not intended for

- Claiming real classification accuracy.
- Final demo claims about model performance.
- Personal identification, tracking, or use of raw audio/RGB data.

## Inputs

Privacy-safe `SensorWindow` records from `shared/contracts/sensor_window.schema.json`.

## Outputs

`EdgeObservation` records that pass `shared/contracts/edge_observation.schema.json`.

## Limitations

The thresholds are hand-written. They should be replaced or calibrated after real labeled sessions are collected in `windows.jsonl` plus a separate `labels.csv`.
