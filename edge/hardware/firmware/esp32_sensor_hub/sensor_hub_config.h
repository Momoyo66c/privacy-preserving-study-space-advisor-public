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

constexpr int kDht11DataPin = 27;
constexpr int kSoundAdcPin = 34;
constexpr int kLightAdcPin = 35;
constexpr uint16_t kAdcMaximum = 4095;
constexpr uint16_t kAudioChunkFrames = 400;
constexpr uint32_t kAudioSampleIntervalUs = 250;
// A quiet microphone may have almost no short-window variation.  Only reject
// a mean pinned close to an ADC rail, which indicates an unusable signal.
constexpr uint16_t kSoundRailGuardCounts = 8;
constexpr uint8_t kLightOversampleCount = 16;

constexpr bool kEnableThermal = true;
// Keep disabled until the LD2450 arrives and is physically connected.
constexpr bool kEnableRadar = false;
constexpr bool kEnableLight = true;
constexpr bool kEnableClimate = true;
constexpr bool kEnableAnalogSound = true;

constexpr uint32_t kHostSerialBaudRate = 460800;
constexpr uint32_t kHeartbeatIntervalMs = 1000;
constexpr uint32_t kThermalIntervalMs = 500;
constexpr uint32_t kSoundIntervalMs = 250;
constexpr uint32_t kLightIntervalMs = 1000;
// DHT11 requires at least about two seconds between real reads.
constexpr uint32_t kClimateIntervalMs = 2000;
constexpr uint32_t kInitializationRetryIntervalMs = 5000;
constexpr uint32_t kRadarOfflineAfterMs = 3000;
constexpr uint8_t kOfflineFailureThreshold = 3;

}  // namespace pssa_config
