// Minimal ESP32 serial smoke test for Raspberry Pi-hosted Arduino CLI.
// No sensor data is collected and no network connection is created.

constexpr unsigned long kReportIntervalMs = 1000;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("PSSA_ESP32_SMOKE_READY");
}

void loop() {
  static unsigned long sequence = 0;
  Serial.print("PSSA_ESP32_HEARTBEAT seq=");
  Serial.println(sequence++);
  delay(kReportIntervalMs);
}
