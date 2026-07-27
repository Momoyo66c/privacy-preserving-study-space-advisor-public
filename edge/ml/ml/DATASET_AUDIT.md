# Real Classroom Dataset Audit

I inspected the uploaded `data.zip`. The dataset layout is:

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

Current dataset summary:

- 4 sessions.
- 36 windows total.
- 9 windows per session.
- Labels in `labels.csv` are scenario labels, not a direct numeric count.
- Numeric people count can be inferred from `session.json` field `participant_range`.
- Session counts:
  - `empty_or_low_activity`: participant_range `0`.
  - `quiet_study_recommended`: participant_range `1`.
  - `discussion_allowed`: participant_range `2`.
  - `not_recommended_noisy_or_crowded`: participant_range `2`.
- Radar is `not_configured`, so the first real count model mainly uses thermal, sound, light proxy, climate and quality features.
- `environment.light_lux` is null because the light sensor is currently a relative HW-486 proxy. The usable light feature is in `relative_features.jsonl` under `light.normalized.mean` and `light.adc.mean`.
- Sound values are relative microphone values, not calibrated dBA.
- Thermal `.npz` files contain `frames` arrays with shape `(4 or 5, 768)`, which represent 24 x 32 thermal frames flattened to 768 values.

Important limitation: this dataset is enough to smoke-test the full ML pipeline, but it is too small and too session-correlated to claim final model accuracy. Use session-level splits only, and collect more labelled sessions before reporting reliable accuracy.
