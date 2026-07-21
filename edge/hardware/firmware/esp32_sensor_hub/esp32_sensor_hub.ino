#include <Arduino.h>
#include <Wire.h>

#include <Adafruit_MLX90640.h>
#include <DHT.h>

#include <math.h>
#include <string.h>

#include "protocol.h"
#include "sensor_hub_config.h"

namespace {

using pssa::MessageType;

constexpr uint8_t kRadarHeader[] = {0xAA, 0xFF, 0x03, 0x00};
constexpr uint8_t kRadarTail[] = {0x55, 0xCC};
constexpr size_t kRadarFrameBytes = 30;
constexpr size_t kThermalPixels = 32 * 24;
constexpr size_t kThermalPayloadBytes = 2 + kThermalPixels * 2;

enum class HealthStatus : uint8_t {
  kOk = 0,
  kDegraded = 1,
  kOffline = 2,
};

enum class ErrorCode : uint16_t {
  kNone = 0,
  kDisabled = 1,
  kInitializationFailed = 2,
  kReadFailed = 3,
  kInvalidValue = 4,
  kAwaitingData = 5,
  kDataStale = 6,
};

struct SensorState {
  MessageType type;
  bool available;
  HealthStatus status;
  ErrorCode error;
  uint8_t consecutive_failures;
  uint32_t total_failures;
};

SensorState thermal_state{MessageType::kThermal, false,
                          HealthStatus::kOffline, ErrorCode::kDisabled, 0, 0};
SensorState radar_state{MessageType::kRadar, false,
                        HealthStatus::kOffline, ErrorCode::kDisabled, 0, 0};
SensorState sound_state{MessageType::kSound, false,
                        HealthStatus::kOffline, ErrorCode::kDisabled, 0, 0};
SensorState light_state{MessageType::kLight, false,
                        HealthStatus::kOffline, ErrorCode::kDisabled, 0, 0};
SensorState climate_state{MessageType::kClimate, false,
                          HealthStatus::kOffline, ErrorCode::kDisabled, 0, 0};

Adafruit_MLX90640 mlx90640;
DHT dht11(pssa_config::kDht11DataPin, DHT11);

bool thermal_initialized = false;
bool light_initialized = false;
bool climate_initialized = false;
bool sound_initialized = false;

float thermal_frame[kThermalPixels];
uint8_t thermal_payload[kThermalPayloadBytes];
uint16_t audio_samples[pssa_config::kAudioChunkFrames];
uint8_t encoded_frame[pssa::kMaxEncodedFrameBytes];
uint8_t radar_frame[kRadarFrameBytes];
size_t radar_frame_length = 0;

uint32_t sequence_number = 0;
uint32_t capability_mask = 0;
uint32_t dropped_samples = 0;
uint32_t last_heartbeat_ms = 0;
uint32_t last_thermal_us = 0;
uint32_t last_sound_ms = 0;
uint32_t last_light_ms = 0;
uint32_t last_climate_ms = 0;
uint32_t last_radar_frame_ms = 0;
uint32_t last_initialization_retry_ms = 0;

uint32_t capabilityBit(MessageType type) {
  switch (type) {
    case MessageType::kThermal:
      return 1U << 0;
    case MessageType::kRadar:
      return 1U << 1;
    case MessageType::kSound:
      return 1U << 2;
    case MessageType::kLight:
      return 1U << 3;
    case MessageType::kClimate:
      return 1U << 4;
    default:
      return 0;
  }
}

void writeLe16(uint8_t* output, uint16_t value) {
  output[0] = static_cast<uint8_t>(value & 0xFF);
  output[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

void writeLe32(uint8_t* output, uint32_t value) {
  output[0] = static_cast<uint8_t>(value & 0xFF);
  output[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
  output[2] = static_cast<uint8_t>((value >> 16) & 0xFF);
  output[3] = static_cast<uint8_t>((value >> 24) & 0xFF);
}

void writeFloatLe(uint8_t* output, float value) {
  uint32_t bits = 0;
  static_assert(sizeof(bits) == sizeof(value), "float must be 32-bit");
  memcpy(&bits, &value, sizeof(bits));
  writeLe32(output, bits);
}

bool sendPacket(MessageType type, const uint8_t* payload,
                uint16_t payload_length) {
  const uint32_t current_sequence = sequence_number++;
  const size_t encoded_length = pssa::encodeFrame(
      type, current_sequence, millis(), payload, payload_length,
      encoded_frame, sizeof(encoded_frame));
  if (encoded_length == 0) {
    ++dropped_samples;
    return false;
  }
  const size_t written = Serial.write(encoded_frame, encoded_length);
  if (written != encoded_length) {
    ++dropped_samples;
    return false;
  }
  return true;
}

void sendHealth(const SensorState& state) {
  uint8_t payload[8];
  payload[0] = static_cast<uint8_t>(state.type);
  payload[1] = static_cast<uint8_t>(state.status);
  writeLe16(payload + 2, static_cast<uint16_t>(state.error));
  writeLe32(payload + 4, state.total_failures);
  sendPacket(MessageType::kHealth, payload, sizeof(payload));
}

void updateState(SensorState& state, bool available, HealthStatus status,
                 ErrorCode error, bool force_report = false) {
  const bool changed = state.available != available || state.status != status ||
                       state.error != error;
  state.available = available;
  state.status = status;
  state.error = error;
  const uint32_t bit = capabilityBit(state.type);
  if (available) {
    capability_mask |= bit;
  } else {
    capability_mask &= ~bit;
  }
  if (changed || force_report) {
    sendHealth(state);
  }
}

void recordSuccess(SensorState& state) {
  state.consecutive_failures = 0;
  updateState(state, true, HealthStatus::kOk, ErrorCode::kNone);
}

void recordFailure(SensorState& state, ErrorCode error) {
  ++state.total_failures;
  if (state.consecutive_failures < 0xFF) {
    ++state.consecutive_failures;
  }
  const bool offline =
      state.consecutive_failures >= pssa_config::kOfflineFailureThreshold;
  updateState(state, !offline && state.available,
              offline ? HealthStatus::kOffline : HealthStatus::kDegraded,
              error);
}

void sendHeartbeat() {
  uint8_t payload[8];
  writeLe32(payload, capability_mask);
  writeLe32(payload + 4, dropped_samples);
  sendPacket(MessageType::kHeartbeat, payload, sizeof(payload));
}

bool i2cPresent(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void initializeThermal() {
  if (!pssa_config::kEnableThermal) {
    updateState(thermal_state, false, HealthStatus::kOffline,
                ErrorCode::kDisabled, true);
    return;
  }
  Wire.setClock(pssa_config::kI2cInitializationFrequencyHz);
  if (!i2cPresent(MLX90640_I2CADDR_DEFAULT) ||
      !mlx90640.begin(MLX90640_I2CADDR_DEFAULT, &Wire)) {
    recordFailure(thermal_state, ErrorCode::kInitializationFailed);
    return;
  }
  mlx90640.setMode(MLX90640_CHESS);
  mlx90640.setResolution(MLX90640_ADC_18BIT);
#if PSSA_THERMAL_PROFILE == PSSA_THERMAL_PROFILE_ANALYTICS
  mlx90640.setRefreshRate(MLX90640_8_HZ);
#elif PSSA_THERMAL_PROFILE == PSSA_THERMAL_PROFILE_SMOOTH
  mlx90640.setRefreshRate(MLX90640_32_HZ);
#elif PSSA_THERMAL_PROFILE == PSSA_THERMAL_PROFILE_LIVE_MAX
  mlx90640.setRefreshRate(MLX90640_64_HZ);
#endif
  Wire.setClock(pssa_config::kI2cRuntimeFrequencyHz);
  thermal_initialized = true;
  recordSuccess(thermal_state);
}

void initializeLight() {
  if (!pssa_config::kEnableLight) {
    updateState(light_state, false, HealthStatus::kOffline,
                ErrorCode::kDisabled, true);
    return;
  }
  pinMode(pssa_config::kLightAdcPin, INPUT);
  analogSetPinAttenuation(pssa_config::kLightAdcPin, ADC_11db);
  light_initialized = true;
  updateState(light_state, false, HealthStatus::kDegraded,
              ErrorCode::kAwaitingData, true);
}

void initializeClimate() {
  if (!pssa_config::kEnableClimate) {
    updateState(climate_state, false, HealthStatus::kOffline,
                ErrorCode::kDisabled, true);
    return;
  }
  dht11.begin();
  climate_initialized = true;
  updateState(climate_state, false, HealthStatus::kDegraded,
              ErrorCode::kAwaitingData, true);
}

void initializeSound() {
  if (!pssa_config::kEnableAnalogSound) {
    updateState(sound_state, false, HealthStatus::kOffline,
                ErrorCode::kDisabled, true);
    return;
  }
  pinMode(pssa_config::kSoundAdcPin, INPUT);
  analogSetPinAttenuation(pssa_config::kSoundAdcPin, ADC_11db);
  sound_initialized = true;
  updateState(sound_state, false, HealthStatus::kDegraded,
              ErrorCode::kAwaitingData, true);
}

void initializeRadar() {
  if (!pssa_config::kEnableRadar) {
    updateState(radar_state, false, HealthStatus::kOffline,
                ErrorCode::kDisabled, true);
    return;
  }
  Serial2.setRxBufferSize(2048);
  Serial2.begin(pssa_config::kRadarBaudRate, SERIAL_8N1,
                pssa_config::kRadarRxPin, pssa_config::kRadarTxPin);
  updateState(radar_state, false, HealthStatus::kDegraded,
              ErrorCode::kAwaitingData, true);
}

void retryFailedInitializations(uint32_t now) {
  if (static_cast<uint32_t>(now - last_initialization_retry_ms) <
      pssa_config::kInitializationRetryIntervalMs) {
    return;
  }
  last_initialization_retry_ms = now;
  if (pssa_config::kEnableThermal && !thermal_initialized) {
    initializeThermal();
  }
  if (pssa_config::kEnableLight && !light_initialized) {
    initializeLight();
  }
  if (pssa_config::kEnableClimate && !climate_initialized) {
    initializeClimate();
  }
  if (pssa_config::kEnableAnalogSound && !sound_initialized) {
    initializeSound();
  }
}

void serviceThermal(uint32_t now_us) {
  if (!thermal_initialized ||
      static_cast<uint32_t>(now_us - last_thermal_us) <
          pssa_config::kThermalIntervalUs) {
    return;
  }
  last_thermal_us = now_us;
  if (mlx90640.getFrame(thermal_frame) != 0) {
    recordFailure(thermal_state, ErrorCode::kReadFailed);
    return;
  }

  thermal_payload[0] = 32;
  thermal_payload[1] = 24;
  for (size_t index = 0; index < kThermalPixels; ++index) {
    const float value = thermal_frame[index];
    if (!isfinite(value) || value < -40.0F || value > 300.0F) {
      recordFailure(thermal_state, ErrorCode::kInvalidValue);
      return;
    }
    const int16_t centi_celsius =
        static_cast<int16_t>(lroundf(value * 100.0F));
    writeLe16(thermal_payload + 2 + index * 2,
              static_cast<uint16_t>(centi_celsius));
  }
  if (sendPacket(MessageType::kThermal, thermal_payload,
                 sizeof(thermal_payload))) {
    recordSuccess(thermal_state);
  }
}

void serviceLight() {
  if (!light_initialized) {
    return;
  }
  uint32_t total = 0;
  for (uint8_t index = 0; index < pssa_config::kLightOversampleCount;
       ++index) {
    total += static_cast<uint16_t>(analogRead(pssa_config::kLightAdcPin));
    delayMicroseconds(200);
  }
  const uint16_t raw = static_cast<uint16_t>(
      total / pssa_config::kLightOversampleCount);
  if (raw > pssa_config::kAdcMaximum) {
    recordFailure(light_state, ErrorCode::kInvalidValue);
    return;
  }
  const float normalized =
      static_cast<float>(raw) / pssa_config::kAdcMaximum;
  uint8_t payload[11];
  writeLe16(payload, raw);
  writeFloatLe(payload + 2, normalized);
  // Reserved calibrated-lux field.  It is ignored while flags bit 0 is zero.
  writeFloatLe(payload + 6, 0.0F);
  payload[10] = 0;
  if (sendPacket(MessageType::kLight, payload, sizeof(payload))) {
    recordSuccess(light_state);
  }
}

void serviceClimate() {
  if (!climate_initialized) {
    return;
  }
  const float humidity = dht11.readHumidity();
  const float temperature = dht11.readTemperature();
  if (!isfinite(temperature) || temperature < -20.0F ||
      temperature > 80.0F || !isfinite(humidity) || humidity < 0.0F ||
      humidity > 100.0F) {
    recordFailure(climate_state, ErrorCode::kInvalidValue);
    return;
  }
  uint8_t payload[8];
  writeFloatLe(payload, temperature);
  writeFloatLe(payload + 4, humidity);
  if (sendPacket(MessageType::kClimate, payload, sizeof(payload))) {
    recordSuccess(climate_state);
  }
}

void serviceEnvironment(uint32_t now) {
  if (static_cast<uint32_t>(now - last_light_ms) >=
      pssa_config::kLightIntervalMs) {
    last_light_ms = now;
    serviceLight();
  }
  if (static_cast<uint32_t>(now - last_climate_ms) >=
      pssa_config::kClimateIntervalMs) {
    last_climate_ms = now;
    serviceClimate();
  }
}

void serviceSound(uint32_t now) {
  if (!sound_initialized ||
      static_cast<uint32_t>(now - last_sound_ms) <
          pssa_config::kSoundIntervalMs) {
    return;
  }
  last_sound_ms = now;
  double sum = 0.0;
  for (uint16_t index = 0; index < pssa_config::kAudioChunkFrames; ++index) {
    const uint16_t raw =
        static_cast<uint16_t>(analogRead(pssa_config::kSoundAdcPin));
    audio_samples[index] = raw;
    sum += raw;
    delayMicroseconds(pssa_config::kAudioSampleIntervalUs);
  }

  const double mean_raw = sum / pssa_config::kAudioChunkFrames;
  double centered_squares = 0.0;
  double peak = 0.0;
  for (uint16_t index = 0; index < pssa_config::kAudioChunkFrames; ++index) {
    const double centered =
        (static_cast<double>(audio_samples[index]) - mean_raw) /
        pssa_config::kAdcMaximum;
    centered_squares += centered * centered;
    const double magnitude = fabs(centered);
    if (magnitude > peak) {
      peak = magnitude;
    }
  }
  const float standard_deviation = static_cast<float>(
      sqrt(centered_squares / pssa_config::kAudioChunkFrames));
  const float rms = standard_deviation;
  const float peak_value = static_cast<float>(peak);
  if (!isfinite(rms) || !isfinite(standard_deviation) ||
      !isfinite(peak_value)) {
    recordFailure(sound_state, ErrorCode::kInvalidValue);
    return;
  }

  uint8_t payload[14];
  writeFloatLe(payload, rms);
  writeFloatLe(payload + 4, standard_deviation);
  writeFloatLe(payload + 8, peak_value);
  writeLe16(payload + 12, pssa_config::kAudioChunkFrames);
  if (sendPacket(MessageType::kSound, payload, sizeof(payload))) {
    recordSuccess(sound_state);
  }
}

bool radarEndsWithHeader() {
  if (radar_frame_length < sizeof(kRadarHeader)) {
    return false;
  }
  return memcmp(radar_frame + radar_frame_length - sizeof(kRadarHeader),
                kRadarHeader, sizeof(kRadarHeader)) == 0;
}

void acceptRadarByte(uint8_t value) {
  if (radar_frame_length < sizeof(kRadarHeader)) {
    const uint8_t expected = kRadarHeader[radar_frame_length];
    if (value == expected) {
      radar_frame[radar_frame_length++] = value;
    } else {
      radar_frame_length = value == kRadarHeader[0] ? 1 : 0;
      if (radar_frame_length == 1) {
        radar_frame[0] = value;
      }
    }
    return;
  }

  radar_frame[radar_frame_length++] = value;
  if (radar_frame_length > sizeof(kRadarHeader) && radarEndsWithHeader()) {
    memcpy(radar_frame, kRadarHeader, sizeof(kRadarHeader));
    radar_frame_length = sizeof(kRadarHeader);
    return;
  }
  if (radar_frame_length < kRadarFrameBytes) {
    return;
  }

  const bool valid = memcmp(radar_frame, kRadarHeader,
                            sizeof(kRadarHeader)) == 0 &&
                     memcmp(radar_frame + kRadarFrameBytes - sizeof(kRadarTail),
                            kRadarTail, sizeof(kRadarTail)) == 0;
  if (valid && sendPacket(MessageType::kRadar, radar_frame,
                          kRadarFrameBytes)) {
    last_radar_frame_ms = millis();
    recordSuccess(radar_state);
  } else if (!valid) {
    recordFailure(radar_state, ErrorCode::kInvalidValue);
  }
  radar_frame_length = 0;
}

void serviceRadar(uint32_t now) {
  if (!pssa_config::kEnableRadar) {
    return;
  }
  while (Serial2.available() > 0) {
    const int value = Serial2.read();
    if (value >= 0) {
      acceptRadarByte(static_cast<uint8_t>(value));
    }
  }
  if (radar_state.available &&
      static_cast<uint32_t>(now - last_radar_frame_ms) >=
          pssa_config::kRadarOfflineAfterMs) {
    recordFailure(radar_state, ErrorCode::kDataStale);
  }
}

}  // namespace

void setup() {
  Serial.begin(pssa_config::kHostSerialBaudRate);
  Wire.begin(pssa_config::kI2cSdaPin, pssa_config::kI2cSclPin);
  Wire.setClock(pssa_config::kI2cInitializationFrequencyHz);

  initializeRadar();
  initializeThermal();
  initializeLight();
  initializeClimate();
  initializeSound();

  const uint32_t now = millis();
  last_heartbeat_ms = now;
  last_thermal_us = micros();
  last_sound_ms = now;
  last_light_ms = now;
  last_climate_ms = now;
  last_initialization_retry_ms = now;
  sendHeartbeat();
}

void loop() {
  const uint32_t now = millis();
  serviceRadar(now);
  retryFailedInitializations(now);
  serviceThermal(micros());
  serviceSound(now);
  serviceEnvironment(now);
  if (static_cast<uint32_t>(now - last_heartbeat_ms) >=
      pssa_config::kHeartbeatIntervalMs) {
    last_heartbeat_ms = now;
    sendHeartbeat();
  }
  delay(1);
}
