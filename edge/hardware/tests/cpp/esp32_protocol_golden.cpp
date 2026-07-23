#include <stdint.h>

#include <array>
#include <cstdio>

#include "protocol.h"

int main() {
  constexpr std::array<uint8_t, 8> payload = {
      0x1F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
  constexpr std::array<uint8_t, 30> expected = {
      0x08, 0x50, 0x53, 0x53, 0x41, 0x02, 0x01, 0x01, 0x01, 0x01,
      0x03, 0xE8, 0x03, 0x01, 0x02, 0x08, 0x02, 0x1F, 0x01, 0x01,
      0x01, 0x01, 0x01, 0x01, 0x05, 0x35, 0xD2, 0xDE, 0x7C, 0x00};
  std::array<uint8_t, pssa::kMaxEncodedFrameBytes> encoded{};

  const size_t encoded_length = pssa::encodeFrame(
      pssa::MessageType::kHeartbeat, 1, 1000, payload.data(), payload.size(),
      encoded.data(), encoded.size());
  if (encoded_length != expected.size()) {
    std::fprintf(stderr, "length mismatch: %lu\n",
                 static_cast<unsigned long>(encoded_length));
    return 1;
  }
  for (size_t index = 0; index < expected.size(); ++index) {
    if (encoded[index] != expected[index]) {
      std::fprintf(stderr, "byte mismatch at %lu: %02x != %02x\n",
                   static_cast<unsigned long>(index),
                   encoded[index], expected[index]);
      return 2;
    }
  }

  std::array<uint8_t, 8> too_small{};
  if (pssa::encodeFrame(pssa::MessageType::kHeartbeat, 1, 1000,
                        payload.data(), payload.size(), too_small.data(),
                        too_small.size()) != 0) {
    std::fprintf(stderr, "undersized output buffer was accepted\n");
    return 3;
  }
  return 0;
}
