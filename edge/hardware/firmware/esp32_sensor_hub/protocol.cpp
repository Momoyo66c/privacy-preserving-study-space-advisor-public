#include "protocol.h"

#include <string.h>

namespace pssa {
namespace {

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

}  // namespace

uint32_t crc32(const uint8_t* data, size_t length) {
  uint32_t crc = 0xFFFFFFFFUL;
  for (size_t index = 0; index < length; ++index) {
    crc ^= data[index];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const uint32_t mask = 0U - (crc & 1U);
      crc = (crc >> 1) ^ (0xEDB88320UL & mask);
    }
  }
  return ~crc;
}

size_t cobsEncode(const uint8_t* input, size_t input_length,
                  uint8_t* output, size_t output_capacity) {
  if (output == nullptr || output_capacity == 0) {
    return 0;
  }
  if (input_length > 0 && input == nullptr) {
    return 0;
  }

  size_t read_index = 0;
  size_t write_index = 1;
  size_t code_index = 0;
  uint8_t code = 1;

  while (read_index < input_length) {
    if (input[read_index] == 0) {
      if (code_index >= output_capacity) {
        return 0;
      }
      output[code_index] = code;
      code_index = write_index;
      if (write_index >= output_capacity) {
        return 0;
      }
      ++write_index;
      code = 1;
      ++read_index;
      continue;
    }

    if (write_index >= output_capacity) {
      return 0;
    }
    output[write_index++] = input[read_index++];
    ++code;
    if (code == 0xFF) {
      if (code_index >= output_capacity) {
        return 0;
      }
      output[code_index] = code;
      code_index = write_index;
      if (write_index >= output_capacity) {
        return 0;
      }
      ++write_index;
      code = 1;
    }
  }

  if (code_index >= output_capacity) {
    return 0;
  }
  output[code_index] = code;
  return write_index;
}

size_t encodeFrame(MessageType message_type, uint32_t sequence,
                   uint32_t device_uptime_ms, const uint8_t* payload,
                   uint16_t payload_length, uint8_t* output,
                   size_t output_capacity) {
  if (payload_length > kMaxPayloadBytes || output == nullptr) {
    return 0;
  }
  if (payload_length > 0 && payload == nullptr) {
    return 0;
  }

  uint8_t decoded[kMaxDecodedFrameBytes];
  decoded[0] = 'P';
  decoded[1] = 'S';
  decoded[2] = 'S';
  decoded[3] = 'A';
  decoded[4] = kProtocolVersion;
  decoded[5] = static_cast<uint8_t>(message_type);
  writeLe32(decoded + 6, sequence);
  writeLe32(decoded + 10, device_uptime_ms);
  writeLe16(decoded + 14, payload_length);
  if (payload_length > 0) {
    memcpy(decoded + kHeaderBytes, payload, payload_length);
  }
  const size_t without_crc = kHeaderBytes + payload_length;
  writeLe32(decoded + without_crc, crc32(decoded, without_crc));
  const size_t decoded_length = without_crc + kCrcBytes;

  if (output_capacity < 2) {
    return 0;
  }
  const size_t encoded_length = cobsEncode(
      decoded, decoded_length, output, output_capacity - 1);
  if (encoded_length == 0 || encoded_length >= output_capacity) {
    return 0;
  }
  output[encoded_length] = 0;
  return encoded_length + 1;
}

}  // namespace pssa
