# Module 1 → Module 2 Sensor Interface Audit

This file documents the exact interfaces Module 1 leaves for the ML pipeline.

## Interface A: shared single-window fixtures

Path:

```text
shared/fixtures/sensor_window_*.json
```

Use these for contract tests and local development before a full session exists.

## Interface B: collected session JSONL

Path:

```text
data/sessions/<session_id>/windows.jsonl
```

Each line is one complete `SensorWindow` JSON object. The companion session folder can also contain:

```text
session.json
checksums.json
thermal/<window_id>.npz
```

`thermal/*.npz` is local-only and may be used for offline feature extraction. It must not be sent to the backend.

## SensorWindow shape

Top-level fields:

```text
schema_version, window_id, room_id, device_id, window_start, window_end,
thermal, radar, sound, environment, quality
```

Thermal:

```json
{
  "health": "ok|degraded|offline|not_configured",
  "frame_count": 10,
  "frames_ref": "local://<session_id>/thermal/<window_id>.npz"
}
```

`frames_ref` is optional. The ML package reads it only when a session directory is provided and NumPy is installed.

Radar:

```json
{
  "health": "ok|degraded|offline|not_configured",
  "sample_count": 50,
  "tracks": [
    {
      "sample_offset_ms": 0,
      "targets": [
        {
          "x_mm": -810,
          "y_mm": 1540,
          "speed_cm_s": 12,
          "distance_resolution_mm": 120,
          "valid": true,
          "target_id": "target-a1b2c3d4-1"
        }
      ]
    }
  ]
}
```

Important: `target_id` is anonymous and window-local. Do not use it as a cross-window person identity.

Sound:

```json
{
  "health": "ok|degraded|offline|not_configured",
  "rms_mean": 0.121,
  "rms_std": 0.012,
  "peak": 0.231
}
```

Raw audio is never persisted and is not required by Module 2.

Environment:

```json
{
  "light_lux": 429.8,
  "temperature_c": 24.6,
  "humidity_pct": 60.1
}
```

Missing environment readings are represented as `null`. There is no separate environment health field in `SensorWindow`; Module 2 derives backend environment health from the null pattern.

Quality:

```json
{
  "completeness": 0.99,
  "warnings": []
}
```

Module 2 uses `completeness` and `warnings` for degradation and confidence reduction.

## Output produced by this package

The ML pipeline emits `EdgeObservation` objects aligned with:

```text
shared/contracts/edge_observation.schema.json
```

The backend payload only includes summary features:

```text
thermal_hot_region_count,
radar_active_target_count,
sound_rms_mean,
light_lux,
temperature_c,
humidity_pct
```

## Interface checks added in this package

- Validates required SensorWindow fields before inference.
- Checks radar target fields instead of trusting arbitrary target objects.
- Warns about low completeness and mismatched radar sample/track counts.
- Resolves `local://<session_id>/thermal/*.npz` only inside the supplied session directory.
- Derives environment health because Module 1 exposes light/climate values, not a single environment health field.
- Keeps deterministic observation IDs while preserving the hash suffix under the backend 128-character limit.

## Useful commands

```bash
study-space-ml-interface ../../data/sessions/<session_id>
study-space-ml-validate ../../data/sessions/<session_id>
study-space-ml-run-pipeline ../../data/sessions/<session_id> \
  --features-out /tmp/features.jsonl \
  --observations-out /tmp/edge_observations.jsonl
```
