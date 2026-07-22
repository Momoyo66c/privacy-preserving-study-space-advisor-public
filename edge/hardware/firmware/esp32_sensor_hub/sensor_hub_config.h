#pragma once

#include <stdint.h>

namespace pssa_config {

// Thermal performance profiles are selected at compile time with
// -DPSSA_THERMAL_PROFILE=<value>.  The validated analytics profile remains the
// default, so a normal build never opts into an unverified high-rate mode.
#define PSSA_THERMAL_PROFILE_ANALYTICS 0
#define PSSA_THERMAL_PROFILE_SMOOTH 1
#define PSSA_THERMAL_PROFILE_LIVE_MAX 2

#ifndef PSSA_THERMAL_PROFILE
#define PSSA_THERMAL_PROFILE PSSA_THERMAL_PROFILE_ANALYTICS
#endif

// Generic ESP32 DevKit pin allocation. Confirm the printed labels on the
// actual board before wiring or powering sensors.
constexpr int kI2cSdaPin = 21;
constexpr int kI2cSclPin = 22;
// MLX90640 EEPROM access must remain at or below 400 kHz.  Faster profiles
// switch to 1 MHz only after begin() has read calibration data.
constexpr uint32_t kI2cInitializationFrequencyHz = 400000;

constexpr int kRadarRxPin = 16;
constexpr int kRadarTxPin = 17;
constexpr uint32_t kRadarBaudRate = 256000;

constexpr int kDht11DataPin = 27;
constexpr int kSoundAdcPin = 34;
constexpr int kLightAdcPin = 35;
constexpr uint16_t kAdcMaximum = 4095;
constexpr uint16_t kAudioChunkFrames = 400;
constexpr uint32_t kAudioSampleIntervalUs = 250;
constexpr uint8_t kLightOversampleCount = 16;

constexpr bool kEnableThermal = true;
// The final hardware baseline omits LD2450. UART2 support remains available in
// the firmware source, but production builds must not advertise radar data.
constexpr bool kEnableRadar = false;
constexpr bool kEnableLight = true;
constexpr bool kEnableClimate = true;
constexpr bool kEnableAnalogSound = true;

// A thermal packet carries 1538 payload bytes.  The conservative wire budget
// includes the 16-byte header, CRC32, worst-case COBS overhead and delimiter.
constexpr uint32_t kThermalWireBytesPerFrame = 1566;
constexpr uint32_t kSerialBitsPerByte = 10;  // UART 8N1
constexpr uint32_t kSerialUtilizationLimitPercent = 80;

#if PSSA_THERMAL_PROFILE == PSSA_THERMAL_PROFILE_ANALYTICS
constexpr uint32_t kI2cRuntimeFrequencyHz = 400000;
constexpr uint32_t kHostSerialBaudRate = 460800;
constexpr uint32_t kThermalRefreshRateHz = 8;   // subpages per second
constexpr uint32_t kThermalPublishFps = 2;      // complete 32 x 24 frames
#elif PSSA_THERMAL_PROFILE == PSSA_THERMAL_PROFILE_SMOOTH
constexpr uint32_t kI2cRuntimeFrequencyHz = 1000000;
constexpr uint32_t kHostSerialBaudRate = 460800;
constexpr uint32_t kThermalRefreshRateHz = 32;
constexpr uint32_t kThermalPublishFps = 16;
#elif PSSA_THERMAL_PROFILE == PSSA_THERMAL_PROFILE_LIVE_MAX
constexpr uint32_t kI2cRuntimeFrequencyHz = 1000000;
constexpr uint32_t kHostSerialBaudRate = 921600;
constexpr uint32_t kThermalRefreshRateHz = 64;
constexpr uint32_t kThermalPublishFps = 32;
#else
#error "unsupported PSSA_THERMAL_PROFILE"
#endif

constexpr uint32_t kThermalIntervalUs =
    1000000U / kThermalPublishFps;
constexpr uint32_t kThermalSerialBytesPerSecond =
    kThermalWireBytesPerFrame * kThermalPublishFps;
constexpr uint32_t kSerialBytesPerSecond =
    kHostSerialBaudRate / kSerialBitsPerByte;

static_assert(kThermalRefreshRateHz == 8 || kThermalRefreshRateHz == 32 ||
                  kThermalRefreshRateHz == 64,
              "unsupported MLX90640 refresh rate");
static_assert(kThermalPublishFps * 2 <= kThermalRefreshRateHz,
              "complete-frame rate cannot exceed half the subpage rate");
static_assert(kThermalRefreshRateHz <= 8 ||
                  kI2cRuntimeFrequencyHz >= 1000000,
              "high-rate thermal profiles require 1 MHz I2C");
static_assert(kThermalSerialBytesPerSecond * 100 <=
                  kSerialBytesPerSecond * kSerialUtilizationLimitPercent,
              "thermal stream exceeds 80 percent of UART capacity");

constexpr uint32_t kHeartbeatIntervalMs = 1000;
constexpr uint32_t kSoundIntervalMs = 250;
constexpr uint32_t kLightIntervalMs = 1000;
// DHT11 requires at least about two seconds between real reads.
constexpr uint32_t kClimateIntervalMs = 2000;
constexpr uint32_t kInitializationRetryIntervalMs = 5000;
constexpr uint32_t kRadarOfflineAfterMs = 3000;
constexpr uint8_t kOfflineFailureThreshold = 3;

}  // namespace pssa_config
