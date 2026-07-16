#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST_ROOT="${PROJECT_ROOT}/references/github"

mkdir -p "${DEST_ROOT}"

clone_repository() {
  local name="$1"
  local url="$2"
  local destination="${DEST_ROOT}/${name}"

  if [[ -d "${destination}" ]]; then
    echo "[SKIP] ${name}: already exists"
    return 0
  fi

  echo "[CLONE] ${name}: ${url}"
  if git clone "${url}" "${destination}"; then
    echo "[OK] ${name}: cloned successfully"
  else
    local status=$?
    echo "[FAIL] ${name}: git clone exited with status ${status}" >&2
    return 0
  fi
}

clone_repository "SparkFun_MLX90640_Arduino_Example" \
  "https://github.com/sparkfun/SparkFun_MLX90640_Arduino_Example.git"
clone_repository "Adafruit_CircuitPython_MLX90640" \
  "https://github.com/adafruit/Adafruit_CircuitPython_MLX90640.git"
clone_repository "PiThermalCam" \
  "https://github.com/tomshaffner/PiThermalCam.git"
clone_repository "HLK-LD2450" \
  "https://github.com/csRon/HLK-LD2450.git"
clone_repository "IoTProject-ZonePresenceDetection-LD2450" \
  "https://github.com/nick28s/IoTProject-ZonePresenceDetection-LD2450.git"
clone_repository "crowdaware-node" \
  "https://github.com/crowdaware-inno-wing-iot/crowdaware-node.git"
clone_repository "classroom-occupancy" \
  "https://github.com/Kautumn06/classroom-occupancy.git"
clone_repository "ArduinoJson" \
  "https://github.com/bblanchon/ArduinoJson.git"
clone_repository "async-mqtt-client" \
  "https://github.com/marvinroger/async-mqtt-client.git"

echo "[DONE] Reference clone pass completed."
