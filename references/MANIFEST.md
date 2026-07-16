# Core Reference Repository Manifest

Last verified: 2026-07-16 (Asia/Singapore)

All repositories were cloned by `scripts/clone_references.sh` into `references/github/`. No third-party installer or dependency installation command was run.

| Repository | GitHub URL | Local directory | Clone status | Default branch | Current commit | Latest commit date | Main language | License | Project layer | Primary purpose |
|---|---|---|---|---|---|---|---|---|---|---|
| SparkFun MLX90640 Arduino Example | https://github.com/sparkfun/SparkFun_MLX90640_Arduino_Example.git | `references/github/SparkFun_MLX90640_Arduino_Example` | Success | `master` | `29260f68a86e6b920cd6ec8a7e724e74c9ad8647` | 2021-08-31 | C++ / Arduino | Code: MIT; hardware files: CC BY-SA 4.0 | ESP32 | MLX90640 initialization, EEPROM parameter extraction, two-subpage frame reading, 768-value output |
| Adafruit CircuitPython MLX90640 | https://github.com/adafruit/Adafruit_CircuitPython_MLX90640.git | `references/github/Adafruit_CircuitPython_MLX90640` | Success | `main` | `6a537df6af2fce6ad301e2022a7084da9b25af19` | 2026-04-23 | Python | MIT for code; per-file SPDX/secondary documentation licenses also present | Raspberry Pi | Python driver, refresh-rate control, `getFrame`, Raspberry Pi hardware validation |
| PiThermalCam | https://github.com/tomshaffner/PiThermalCam.git | `references/github/PiThermalCam` | Success | `master` | `cdee56f18ee7779e172f506be6edf624cde5de40` | 2024-10-02 | Python | AGPL-3.0 | Raspberry Pi / Laptop | Thermal-matrix normalization, interpolation, colour mapping, OpenCV display, Flask MJPEG streaming |
| HLK-LD2450 | https://github.com/csRon/HLK-LD2450.git | `references/github/HLK-LD2450` | Success | `main` | `1b65a026873ab2db3d22d3b3bb99ef16fbcdd4f0` | 2024-05-23 | Python | MIT | Raspberry Pi / ESP32 reference | LD2450 command/report framing and three-target x/y/speed/resolution parsing |
| Zone Presence Detection LD2450 | https://github.com/nick28s/IoTProject-ZonePresenceDetection-LD2450.git | `references/github/IoTProject-ZonePresenceDetection-LD2450` | Success | `main` | `d5a93d9473c22b2d54e121bffdb336c3a20daa7c` | 2025-01-23 | C++ / TypeScript | GPL-3.0 | ESP32 / Laptop reference | ESP32 LD2450 reading, three rectangular zones, JSON, REST and WebSocket position data |
| CrowdAware Node | https://github.com/crowdaware-inno-wing-iot/crowdaware-node.git | `references/github/crowdaware-node` | Success | `main` | `d36757924f34a81322d3293127b100fdb5145d9e` | 2026-04-26 | C++ | GPL-3.0 | ESP32 / Raspberry Pi reference | Privacy-aware thermal background model, segmentation, blob centroids, compact telemetry |
| Classroom Occupancy | https://github.com/Kautumn06/classroom-occupancy.git | `references/github/classroom-occupancy` | Success | `master` | `fb51f958b0fb36efb3696a3943fe5cb80d1dcf9f` | 2019-01-13 | Jupyter / CSV | MIT | Machine Learning | Multisensor time-series schema, resampling, cleaning, occupancy labels and train-ready tables |
| ArduinoJson | https://github.com/bblanchon/ArduinoJson.git | `references/github/ArduinoJson` | Success | `7.x` | `7823e4a62b17ea0ee81bdd4e79911c94e637f964` | 2026-07-06 | C++ | MIT | ESP32 / Shared | JSON and MessagePack serialization for sensor and MQTT payloads |
| async-mqtt-client | https://github.com/marvinroger/async-mqtt-client.git | `references/github/async-mqtt-client` | Success | `develop` | `3d93fc7f662e65366f8e2b0d88b108f874f035b9` | 2024-09-25 | C++ | MIT | ESP32 | Asynchronous MQTT publish/subscribe, callbacks and Wi-Fi/MQTT reconnection pattern |

## Clone result

- Successful: 9 of 9.
- Failed: none.
- Execution log: `references/clone-results.log`.
- A second execution of the script is safe: existing repository directories are reported as `already exists` and are not deleted.

## Repository freshness notes

- Actively current at review time: Adafruit CircuitPython MLX90640, ArduinoJson, CrowdAware Node.
- Recent but requiring compatibility checks: PiThermalCam, HLK-LD2450, Zone Presence Detection LD2450, async-mqtt-client.
- Old reference material: SparkFun examples are mainly from 2018 and the repository's latest commit is from 2021; Classroom Occupancy's latest commit is from 2019.
- Commit date alone is not a quality guarantee. Hardware, library, ESP32 core and Python-version compatibility must be tested in the next phase without automatically installing every repository's dependencies.
