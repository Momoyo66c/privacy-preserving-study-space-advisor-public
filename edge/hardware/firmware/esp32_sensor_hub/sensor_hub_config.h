#pragma once

#include <stdint.h>

namespace pssa_config {

// Generic ESP32 DevKit pin allocation. Confirm the printed labels on the
// actual board before wiring or powering sensors.
constexpr int kI2cSdaPin = 21;
constexpr int kI2cSclPin = 22;
constexpr uint32_t kI2cFrequencyHz = 400000;

constexpr int kRadarRxPin = 16;
constexpr int kRadarTxPin = 17;
constexpr uint32_t kRadarBaudRate = 256000;

constexpr int kI2sBclkPin = 26;
constexpr int kI2sWsPin = 25;
constexpr int kI2sDataInPin = 33;
constexpr uint32_t kAudioSampleRateHz = 8000;
constexpr uint16_t kAudioChunkFrames = 800;

constexpr bool kEnableThermal = true;
constexpr bool kEnableRadar = true;
constexpr bool kEnableLight = true;
constexpr bool kEnableClimate = true;

// Keep disabled until an I2S microphone is physically connected. A classic
// ESP32-D0WD-V3 cannot host the existing USB microphone directly.
constexpr bool kEnableI2sSound = false;

constexpr uint32_t kHostSerialBaudRate = 460800;
constexpr uint32_t kHeartbeatIntervalMs = 1000;
constexpr uint32_t kThermalIntervalMs = 500;
constexpr uint32_t kSoundIntervalMs = 250;
constexpr uint32_t kEnvironmentIntervalMs = 1000;
constexpr uint32_t kInitializationRetryIntervalMs = 5000;
constexpr uint32_t kRadarOfflineAfterMs = 3000;
constexpr uint8_t kOfflineFailureThreshold = 3;

}  // namespace pssa_config
