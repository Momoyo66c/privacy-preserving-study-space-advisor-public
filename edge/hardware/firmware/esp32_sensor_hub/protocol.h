#pragma once

#include <stddef.h>
#include <stdint.h>

namespace pssa {

constexpr uint8_t kProtocolVersion = 2;
constexpr size_t kMaxPayloadBytes = 2048;
constexpr size_t kHeaderBytes = 16;
constexpr size_t kCrcBytes = 4;
constexpr size_t kMaxDecodedFrameBytes =
    kHeaderBytes + kMaxPayloadBytes + kCrcBytes;
constexpr size_t kMaxEncodedFrameBytes =
    kMaxDecodedFrameBytes + (kMaxDecodedFrameBytes / 254) + 2;

enum class MessageType : uint8_t {
  kHeartbeat = 0x01,
  kHealth = 0x02,
  kThermal = 0x10,
  kRadar = 0x11,
  kSound = 0x12,
  kLight = 0x13,
  kClimate = 0x14,
};

uint32_t crc32(const uint8_t* data, size_t length);

size_t cobsEncode(const uint8_t* input, size_t input_length,
                  uint8_t* output, size_t output_capacity);

size_t encodeFrame(MessageType message_type, uint32_t sequence,
                   uint32_t device_uptime_ms, const uint8_t* payload,
                   uint16_t payload_length, uint8_t* output,
                   size_t output_capacity);

}  // namespace pssa
