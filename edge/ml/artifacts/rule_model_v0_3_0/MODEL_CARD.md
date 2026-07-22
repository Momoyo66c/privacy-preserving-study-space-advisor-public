# Model Card — edge-rule-baseline 0.3.0

## Intended use

Local Raspberry Pi / edge inference for Module 2 integration testing. The model converts a Module 1 `SensorWindow` into a Module 3 `EdgeObservation`.

## Status

This is a deterministic rule baseline, not a real-data-trained model. It exists so the end-to-end interface works before labelled real sessions are available.

## Inputs

Aggregate sensor-window fields from thermal health/frame count, radar anonymous target aggregates, sound level statistics, environment readings, and quality completeness.

## Outputs

- `room_state`
- `occupancy_level`
- `suitability_score`
- `confidence`
- contract-safe feature summary
- warnings

## Limitations

- It cannot claim real-world accuracy.
- Thermal raw frames are optional; if local NPZ files are unavailable, thermal hot-region count is reported as `null` and inference relies more on radar and sound.
- When thermal and radar are both unavailable, the model returns `unknown`.
