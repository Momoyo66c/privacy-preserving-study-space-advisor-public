# Core Repository Analysis

## Scope and method

This is a source-reading report, not a dependency-installation or hardware-test report. For each repository, the README, tracked file structure, license, current commit and high-value source files were inspected. No third-party `install.sh`, `curl | bash`, firmware upload, sensor access, model training or full application build was performed.

The project boundary remains unchanged:

- ESP32 is the Sensor Hub and publishes sensor data through Wi-Fi/MQTT.
- Raspberry Pi 5 is the Edge AI Node for feature extraction, time windows, Random Forest inference and state output.
- Laptop hosts the API, database, history/prediction, dashboard and later LLM recommendation.

## Repository comparison

| Repository | Project use | High-value files | Can it run directly? | Useful ideas | Content not suitable for direct use | Later location |
|---|---|---|---|---|---|---|
| SparkFun MLX90640 Arduino Example | Primary low-level reference for ESP32 MLX90640 acquisition | `Firmware/Example1_BasicReadings/Example1_BasicReadings.ino`; `Firmware/Example2_OutputToProcessing/Example2_OutputToProcessing.ino`; `Firmware/Example3_MaxRefreshRate/Example3_MaxRefreshRate.ino`; each example's `MLX90640_API.{h,cpp}` and `MLX90640_I2C_Driver.{h,cpp}` | Not verified as-is on ESP32; examples target Teensy/Arduino and need ESP32 pin, I²C and timing adaptation | Address `0x33`; 400 kHz EEPROM read; parameter extraction; reading both subpages; 768-float matrix; refresh-rate trade-offs; CSV frame output | Processing visualizer and Teensy-specific timing/pin assumptions; do not blindly use 1 MHz I²C or block forever on sensor errors | `esp32/` sensor driver and frame acquisition |
| Adafruit CircuitPython MLX90640 | Raspberry Pi direct-sensor test and cross-check against ESP32 frames | `adafruit_mlx90640.py`; `examples/mlx90640_simpletest.py`; `mlx90640_pil.py`; `mlx90640_camtest.py` | Likely runnable on supported GNU/Linux/Raspberry Pi after controlled dependency setup and I²C configuration; not tested here | `RefreshRate`; 800 kHz example bus; `getFrame(frame)` fills 768 values; two-subpage merge; retry on `ValueError`; explicit frame calibration calculations | Python/BLINKA code cannot be compiled into Arduino ESP32 firmware; Linux-only PIL/OpenCV examples do not run on microcontrollers | `raspberry_pi/` hardware validation and frame comparison |
| PiThermalCam | Heatmap rendering and lightweight streaming reference | `pithermalcam/pi_therm_cam.py`; `pithermalcam/web_server.py`; `examples/live_video.py`; `examples/web_server.py`; `sequential_versions/opencv_therm_cam.py` | Not directly approved for project integration; built on Pi 4, requires several native/Python packages and hardware; not executed | Temperature normalization; `uint8` conversion; OpenCV colour maps; interpolation choices; bilateral filtering; JPEG/MJPEG Flask response; error handling for `ValueError` and `OSError` | AGPL server code must not be copied into a differently licensed backend without accepting AGPL obligations; old setup instructions and global/threaded Flask design need redesign | Raspberry Pi diagnostic viewer; Laptop dashboard heatmap design reference |
| HLK-LD2450 | Best protocol-level reference for LD2450 | `serial_protocol.py`; `print_targets.py`; `plot_targets.py`; `docs/hlk_ld2450_serial_communication.pdf`; datasheet | Python demos can run on Linux with the radar and USB-TTL adapter after installing `pyserial`/`matplotlib`; not executed | Command header `FD FC FB FA`, command tail `04 03 02 01`, report header `AA FF 03 00`, report tail `55 CC`; 30-byte report; three 8-byte targets; little-endian fields; command/configuration operations | Its `read_until(tail)` framing is not sufficient for a robust noisy UART stream; outliers are unfiltered; its sign conversion should be verified against the vendor document before porting | ESP32 UART parser specification; Raspberry Pi protocol test utility |
| Zone Presence Detection LD2450 | ESP32 integration, zone logic and live radar UI reference | `ESP32_PIO/src/main_zone.cpp`; `main_basics.cpp`; `ESP32_PIO/platformio.ini`; React `src/` files | Not verified; depends on PlatformIO libraries and local Wi-Fi credentials. Repository also tracks generated `.pio` artifacts, which should not be reused | `Serial2`-based LD2450 library use; maximum three targets; rectangle containment; Wi-Fi reconnect; `/zones` REST data; `/ws` WebSocket JSON `{id,x,y}` | GPL-3.0 code must not be copied casually; WebSocket/dashboard responsibilities exceed the planned ESP32 role; blocking Wi-Fi reconnect and hard-coded zone defaults need redesign; old `me-no-dev/ESP Async WebServer` dependency needs compatibility review | ESP32 LD2450 proof-of-concept only; Laptop may reuse the data-contract idea, not the code |
| CrowdAware Node | Closest reference to privacy-preserving thermal occupancy detection | `Firmware/src/thermal_image_processor.cpp`; `Firmware/include/thermal_image_processor.h`; `mlx_sensor.cpp`; `thermal_serializer.cpp`; `wifi_transport.cpp`; `Visualization/parser_win.py` | Hardware/board-specific PlatformIO project for Heltec WiFi LoRa 32 V3; not built or run here | Float-to-8-bit thermal frame; running background; update background only with zero detections; erosion/dilation; Gaussian blur; approximate distance transform; connected-region/watershed-like extraction; centroid/area; compact packet fragments | GPL-3.0 code must remain reference-only unless the project adopts compatible licensing; algorithm is heuristic, has thresholds requiring local calibration, and its current processing is on ESP32 whereas this project's main Edge AI processing belongs on Raspberry Pi | Reimplement concepts in `raspberry_pi/`; optionally use only minimal ESP32 frame-quality ideas |
| Classroom Occupancy | Best reference for tabular multisensor data and Random Forest-ready schema | `notebooks/DataWrangling.ipynb`; `data/classification_data.csv`; `regression_data.csv`; `sensor_data.csv`; `occupancy_data.csv` | CSVs and notebook can be inspected/run in a controlled environment, but the notebook is old and was not executed | Timestamp alignment; one-minute resampling; different aggregation rules for continuous sensors and occupancy; door label encoding; features `temp, humidity, co2, light, sound, images, door`; classification target `occupancy_level`; train-ready classification/regression tables | Current repository does not contain the complete Random Forest training/evaluation notebook claimed by the broader project history; data uses camera-image variation and Bluetooth counts, and its labels do not match this project's four states | `raspberry_pi/` dataset schema and later training pipeline design |
| ArduinoJson | ESP32 payload construction | `examples/JsonGeneratorExample/JsonGeneratorExample.ino`; `examples/MsgPackParser/MsgPackParser.ino`; `examples/JsonUdpBeacon/JsonUdpBeacon.ino`; `src/ArduinoJson.h`; `CHANGELOG.md` | Library is current and ESP32-compatible, but was not built in this phase | JSON/MessagePack; stream/buffer serialization; explicit length measurement; custom allocators; ESP32 external RAM support | ArduinoJson 7 removed `StaticJsonDocument` and always uses a heap-backed elastic `JsonDocument`; old v6 examples about fixed static capacity do not apply. Serializing the full 768-float matrix as JSON is bandwidth/RAM inefficient | `esp32/` payload encoder and `shared/` message schema |
| async-mqtt-client | ESP32 MQTT state machine reference | `examples/FullyFeatured-ESP32/FullyFeatured-ESP32.ino`; `docs/1.-Getting-started.md`; `docs/2.-API-reference.md`; `docs/3.-Memory-management.md`; `docs/4.-Limitations-and-known-issues.md` | Not verified with the current ESP32 Arduino core/AsyncTCP stack | Non-blocking callbacks; Wi-Fi and MQTT reconnect timers; `publish`, `subscribe`, QoS callbacks; chunked receive callback using `len/index/total` | TLS limitations are serious: fingerprint validation, no TLS 1.2, and some algorithms can crash according to its own documentation. It also cannot publish a payload larger than available RAM. Do not expose this design directly to the internet | `esp32/` LAN MQTT transport evaluation; consider a better-maintained client if TLS is required |

## Required conclusions

### 1. Best repository for ESP32 MLX90640 reading

Use **SparkFun MLX90640 Arduino Example** as the primary reference because it clearly exposes initialization, EEPROM parameter extraction, the low-level Melexis API, two-subpage acquisition and full 32 × 24 output under the MIT license. It is not an ESP32-ready drop-in; port the concepts and validate its I²C driver on the selected ESP32 board.

Use **CrowdAware Node** only as a secondary ESP32 implementation reference. It demonstrates a newer ESP32/PlatformIO wrapper, but GPL-3.0 prevents casual copying and its on-node processing allocation conflicts with this project's Raspberry Pi edge-processing responsibility.

### 2. Best repository for understanding the LD2450 protocol

Use **HLK-LD2450**. `serial_protocol.py` is small, MIT-licensed and maps command/report headers, tails and per-target fields explicitly. The included vendor PDFs should be treated as the final authority when resolving signed-coordinate encoding.

For an ESP32 usage pattern, consult **Zone Presence Detection LD2450** after the protocol is understood, but reimplement the parser/state machine rather than copying GPL code.

### 3. Repository closest to privacy-preserving occupancy detection

**CrowdAware Node** is the closest conceptual match. It uses MLX90640 input, a running thermal background, foreground processing, connected regions, centroid/area extraction and privacy-preserving compact telemetry. Its algorithms should be independently reimplemented and tested on Raspberry Pi 5.

### 4. Best repository for heatmap display

**PiThermalCam** is the strongest visual reference for interpolation, colour maps, OpenCV frame generation and Flask MJPEG streaming. Because it is AGPL-3.0, copy neither the whole package nor server code into the formal Laptop system unless the team deliberately accepts AGPL terms. Reimplement the needed matrix-to-heatmap pipeline.

### 5. Best repository for Random Forest data structure

**Classroom Occupancy** is the best of the provided repositories for data organization. `classification_data.csv` contains 4,522 rows with:

`datetime, temp, humidity, co2, light, sound, images, door, occupancy_level`

Its notebook shows cleaning, timestamp resampling, categorical encoding and construction of classification/regression tables. It is not a complete Random Forest implementation in its current form, so it should guide schema and preprocessing only.

### 6. Repositories that should be reference-only

- Mandatory reference-only unless compatible licensing is deliberately adopted: PiThermalCam (AGPL-3.0), Zone Presence Detection LD2450 (GPL-3.0), CrowdAware Node (GPL-3.0).
- Reference/port rather than copy wholesale: SparkFun examples (platform adaptation required), HLK-LD2450 Python parser (language/platform change), Classroom Occupancy (different sensors and labels), async-mqtt-client (TLS and maintenance concerns).
- Permissive libraries that may later be used with notices: Adafruit driver, ArduinoJson and MIT-licensed portions of SparkFun/HLK-LD2450/Classroom Occupancy/async-mqtt-client.

### 7. Old or potentially obsolete repositories/dependencies

- Classroom Occupancy is the oldest: latest commit 2019-01-13. Its notebook likely needs modern pandas/scikit-learn API updates; the current repository omits the original model notebooks.
- SparkFun's example code is mainly from 2018 and latest repository activity is 2021. The sensor protocol remains relevant, but ESP32 I²C behaviour and current toolchains must be tested.
- PiThermalCam's core file was updated in 2024, but documentation still references Pi 4 and older system packages such as `libatlas-base-dev` and `python-smbus`.
- Zone Presence Detection pins `me-no-dev/ESP Async WebServer@^1.2.4` and tracks generated `.pio` files. Verify compatibility with the current ESP32 Arduino core and maintained AsyncTCP/WebServer forks.
- async-mqtt-client has recent repository activity, but its documented TLS limitations make its secure-network path unsuitable for a new internet-facing design.

### 8. Raspberry Pi code not suitable for ESP32

- Adafruit's Python driver and Linux-only PIL/OpenCV examples.
- PiThermalCam's NumPy, SciPy, OpenCV, cmapy, Flask and filesystem/display code.
- HLK-LD2450's `pyserial`, matplotlib and Python threading/queue demos.
- Classroom Occupancy's pandas/Jupyter preprocessing.

These can inform algorithms or test harnesses, but they cannot be compiled into Arduino firmware.

### 9. ESP32 code not directly runnable on Raspberry Pi

- SparkFun Arduino sketches and `Wire`-based I²C driver.
- Zone Presence Detection's Arduino/PlatformIO firmware, `Serial2`, ESP Wi-Fi and ESPAsyncWebServer code.
- CrowdAware firmware's Arduino `Wire`, board-specific configuration and embedded buffers.
- async-mqtt-client's ESP8266/ESP32 AsyncTCP implementation.

Raspberry Pi equivalents require Linux I²C/serial libraries and a Python/C++ service architecture.

## Recommended next-phase starting point

Implement one isolated module first: **ESP32 MLX90640 frame acquisition and validation**.

Acceptance boundary for that module:

1. Initialize MLX90640 at `0x33`.
2. Read both subpages and produce exactly 768 calibrated Celsius values.
3. Add bounded retry/error counters instead of permanent blocking.
4. Emit a versioned test frame over serial first; do not add MQTT yet.
5. Compare the same static scene against the Adafruit Raspberry Pi driver.
6. Measure acquisition time, missing/invalid frame rate, RAM use and practical refresh rate.

This validates the largest sensor payload and the highest-risk low-level data source before combining radar, environmental sensors or MQTT.

## Proposed shared data-contract direction for later work

Do not implement it in this phase, but reserve a versioned schema with:

- `schema_version`, `device_id`, `sequence`, `captured_at_ms`
- `thermal.width = 32`, `thermal.height = 24`, `thermal.unit`
- thermal payload encoding and byte length
- LD2450 target list containing `valid, x_mm, y_mm, speed_cm_s, resolution_mm`
- sound/light/temperature/humidity summaries
- quality flags and sensor error counters

For the full thermal frame, benchmark binary or MessagePack against JSON. A JSON array of 768 floating-point values is easy to inspect but is a poor default for ESP32 RAM, network bandwidth and MQTT packet size.
