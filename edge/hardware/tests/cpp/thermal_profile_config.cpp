#include <stdint.h>

#include "sensor_hub_config.h"

#ifndef EXPECT_I2C_RUNTIME_HZ
#error "EXPECT_I2C_RUNTIME_HZ is required"
#endif
#ifndef EXPECT_SERIAL_BAUD
#error "EXPECT_SERIAL_BAUD is required"
#endif
#ifndef EXPECT_REFRESH_HZ
#error "EXPECT_REFRESH_HZ is required"
#endif
#ifndef EXPECT_PUBLISH_FPS
#error "EXPECT_PUBLISH_FPS is required"
#endif

static_assert(pssa_config::kI2cInitializationFrequencyHz == 400000);
static_assert(pssa_config::kI2cRuntimeFrequencyHz == EXPECT_I2C_RUNTIME_HZ);
static_assert(pssa_config::kHostSerialBaudRate == EXPECT_SERIAL_BAUD);
static_assert(pssa_config::kThermalRefreshRateHz == EXPECT_REFRESH_HZ);
static_assert(pssa_config::kThermalPublishFps == EXPECT_PUBLISH_FPS);
static_assert(!pssa_config::kEnableRadar);
static_assert(pssa_config::kThermalIntervalUs ==
              1000000U / EXPECT_PUBLISH_FPS);
static_assert(pssa_config::kThermalSerialBytesPerSecond * 100 <=
              pssa_config::kSerialBytesPerSecond *
                  pssa_config::kSerialUtilizationLimitPercent);

int main() { return 0; }
