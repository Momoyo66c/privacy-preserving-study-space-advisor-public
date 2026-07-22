import test from "node:test";
import assert from "node:assert/strict";
import {
  createMockSnapshot,
  createThermalFrame,
  isFreshLiveSensorSnapshot,
  isLiveSensorSnapshot
} from "../src/sensor-data.mjs";

test("mock snapshot matches the module-facing live contract", () => {
  const snapshot = createMockSnapshot(3, new Date("2026-07-22T08:00:00Z"));
  assert.equal(isLiveSensorSnapshot(snapshot), true);
  assert.equal(snapshot.room.sensor_health.radar, "not_configured");
  assert.equal(snapshot.thermal_preview.values.length, 32 * 24);
  for (const field of ["temperature_c", "humidity_pct", "light_relative_mean", "light_lux", "sound_rms_mean", "sound_peak_max"]) {
    assert.equal(typeof snapshot.room.features[field], "number");
  }
});

test("stale snapshots remain contract-valid but cannot be displayed as live data", () => {
  const snapshot = createMockSnapshot(1, new Date("2026-07-22T08:00:00Z"));
  snapshot.room.is_stale = true;
  snapshot.room.data_age_seconds = 300;

  assert.equal(isLiveSensorSnapshot(snapshot), true);
  assert.equal(isFreshLiveSensorSnapshot(snapshot), false);
});

test("thermal frame is normalized and visually non-flat", () => {
  const values = createThermalFrame(27);
  assert.ok(Math.min(...values) >= 0);
  assert.ok(Math.max(...values) <= 1);
  assert.ok(new Set(values).size > 100);
});
