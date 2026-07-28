# Privacy-Preserving Study Space Advisor — Poster Fact Check

Prepared: 2026-07-27
Poster status language: **Implemented**, **Prototype validated**, and **Integration in progress** are intentionally distinct.

## Claims used in the poster

| Poster claim | Status | Evidence | Qualification |
|---|---|---|---|
| The system is camera-free and does not use facial recognition or identity tracking. | Implemented privacy constraint | `docs/module-specs/00_SHARED_CONTRACT.md`, root `README.md`, `backend/MODULE3_HANDOFF.md` | This is an architectural and test constraint, not a claim that every future deployment is automatically compliant. |
| Raw audio is not stored or uploaded; the laptop agent sends only RMS, standard deviation, and peak summaries. | Implemented | `origin/main:README.md`, `origin/main:edge/hardware/MODULE1_HANDOFF.md`, `origin/main:edge/hardware/src/study_space_hardware/remote_sound_agent.py` | The current production demo source is a Windows laptop microphone. HW-485 is not presented as the production sound sensor. |
| MLX90640, HW-486, and DHT11 connect to an ESP32 sensor hub; the Raspberry Pi 5 performs edge processing. | Implemented hardware architecture | Root README, Module 1 handoff, `docs/module-specs/00_SHARED_CONTRACT.md` | HW-486 produces a device-relative value, not lux. |
| Thermal previews are normalized 32×24 values, short-lived, and not persisted by the backend. | Implemented | Shared contract §8.1, `shared/contracts/thermal_preview.schema.json`, `backend/README.md` | Full thermal frames may exist only in local offline sessions. |
| Observation ingestion, room status, history, and 15/30-minute forecast APIs exist. | Implemented | `backend/README.md`, `backend/MODULE3_HANDOFF.md`, shared schemas | Forecast strategy is implemented; real-world forecast accuracy is not established. |
| The simulated sensor-to-dashboard Gate A pipeline is automated. | Prototype validated | `tests/integration/GATE_A_HANDOFF.md`, `.github/workflows/gate-a-ci.yml`, passing GitHub Actions on `main` | Gate A uses deterministic simulation, not the physical sensor chain. |
| Online room-state inference from the current real hardware path is still being integrated. | Integration in progress | `origin/main:README.md` Gate B status | The current live bridge can bypass Module 2 and publish `room_state=unknown`. |
| The formal preference-aware recommendation adapter is not complete. | Integration in progress | `backend/MODULE3_HANDOFF.md`, `frontend/MODULE4_HANDOFF.md` | The current backend uses `StubRecommendationAdapter`. |
| Four independent real sessions contain 36 five-second windows and 176 MLX90640 frames. | Prototype validation dataset | `origin/main:edge/hardware/REAL_DATASET_GUIDE.md`, `origin/main:edge/hardware/MODEL_TRAINING_READINESS_REPORT.md` | One session per class, one room/day/device; the 36 windows must not be randomly split to claim accuracy. |
| Observation-write P95 was 32.82 ms in a local prototype benchmark. | Verified evidence available; not displayed in the current poster | `origin/main:backend/PERFORMANCE.md` | Python 3.11.6, SQLite, fixed synthetic seed, single-worker Uvicorn over localhost. This is not deployment capacity or end-to-end sensor latency. |
| Backend CI, repository checks, and Gate A were passing on the inspected `main`. | Verified CI status | GitHub Actions inspected 2026-07-27 at `c5d9997` | Current at inspection time; branch protection is not enabled and the new people-count suite is not covered by a dedicated Module 2 workflow. |
| The two poster screenshots represent the implemented React UI. | Prototype UI validated | Local captures from `/?mode=mock` and `/thermal?room=room_a&mode=mock` | Both screenshots are explicitly captioned as mock-mode prototype data; they do not claim a live physical-sensor session. |

## Placeholders requiring user confirmation

| Placeholder | Required input |
|---|---|
| `[GROUP_NUMBER]` | Official Summer Workshop group number |
| `[MEMBERS]` | Final member names and preferred ordering |
| `[QR_CODE]` | GitHub or demo URL to encode |
| `[HARDWARE_PHOTO]` | Original hardware panorama; it was not found in the repository, Git history, remote branches, or supplied attachments |

## Content deliberately not claimed

- No Macro F1, classification accuracy, per-class recall, or confusion matrix.
- No real-world forecast accuracy.
- No recommendation-effectiveness or user-study result.
- No number of users or deployment-scale claim.
- No claim that the additive people-count training pipeline is connected to the live room-state flow.
- No claim of generalization across rooms, dates, devices, or sensor positions.
- No claim that the poster screenshots show a live physical-sensor run.

## Unverified items

The only missing evidence needed to replace visible poster placeholders is the hardware panorama, group number, member list, and QR destination. No unverifiable performance number has been inserted.
