# Module 2 Live Inference Handoff

## Delivered boundary

`study-space-ml-live` is the production demo entry point. It composes the
Module 1 orchestrator with `LiveInferenceProcessor`, so the same completed
sensor window drives:

1. an in-memory MLX90640 people-count prediction;
2. a privacy-safe `people_count_prediction.v1` live payload;
3. an `EdgeObservation` containing the fused occupancy/state/suitability;
4. the existing short-lived thermal and sound previews.

The frontend never infers people from rendered heat-map regions. The backend
live count is the only numeric source.

## Raspberry Pi deployment

The verified demo uses:

```text
repository: /home/pi/privacy-study-space-advisor
venv:       /home/pi/privacy-study-space-advisor/edge/hardware/.venv
artifact:   /home/pi/.config/pssa/models/people_count_rf_motion_v0_2
drop-in:    ~/.config/systemd/user/pssa-dashboard-bridge.service.d/module2-live.conf
```

The Pi venv needs the Module 1 dependencies plus NumPy, pandas, SciPy,
scikit-learn, joblib and tabulate. After synchronizing the source and artifact:

```bash
systemctl --user daemon-reload
systemctl --user restart pssa-dashboard-bridge.service
systemctl --user status pssa-dashboard-bridge.service --no-pager
journalctl --user -u pssa-dashboard-bridge.service -n 100 --no-pager
```

## State fusion

- Count and relative sound select the four public room states.
- Relative light and temperature/humidity adjust suitability.
- Offline thermal/count or unavailable sound produces `unknown`.
- Missing lux does not fabricate a value; calibrated relative light can still
  contribute to the live suitability summary.
- Sensor health and input warnings are preserved in the Observation.

## Privacy

Raw 32 × 24 frames exist only during local feature extraction and preview
normalization. Raw audio is never recorded. Count/Observation payloads contain
only bounded summaries and no face, image, waveform, trajectory, or identity.
The LLM receives only the already-ranked structured room facts.

## Validation and limitation

Windows validation:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -m pytest tests -q
```

The current artifact was trained from 36 real five-second windows and only
zero-to-two-person labels. It is suitable for the course demonstration and
pipeline validation, not for safety, access control, or general crowd counting.
The leave-one-session evaluation is the relevant warning: independent sessions,
additional empty-room variation, and labels above two people are still needed.

The live demo adds a local, aggregate zero-to-four calibration overlay. An
empty command resets the thermal background; one- and two-person commands
record two median foreground-area/excess-heat samples. Counts three and four
are extrapolated and capped at four. Two consecutive five-second windows are
required for an unlabelled count transition. The calibration profile contains
no frame, position, trajectory, or identity and is stored at:

```text
~/.config/pssa/thermal-count-calibration.json
```

The one-shot command path is:

```text
/tmp/pssa-thermal-count-calibration.json
```

For best demo accuracy, keep the MLX90640 fixed, establish an empty background
after every restart, and keep participants from fully occluding one another.
Tiny residual warm regions whose weighted area/heat evidence is below 35% of
the calibrated single-person anchor are classified as zero.
