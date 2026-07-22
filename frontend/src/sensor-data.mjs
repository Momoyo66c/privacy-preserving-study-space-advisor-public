const WIDTH = 32;
const HEIGHT = 24;

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));

function gaussian(x, y, centerX, centerY, spread) {
  const distance = (x - centerX) ** 2 + (y - centerY) ** 2;
  return Math.exp(-distance / (2 * spread ** 2));
}

export function createThermalFrame(sequence) {
  const phase = sequence * 0.12;
  const firstX = 10.5 + Math.sin(phase) * 2.4;
  const firstY = 11.5 + Math.cos(phase * 0.8) * 1.5;
  const secondX = 22 + Math.cos(phase * 0.7) * 2.1;
  const secondY = 8.8 + Math.sin(phase * 0.9) * 1.6;
  const raw = Array.from({ length: WIDTH * HEIGHT }, (_, index) => {
    const x = index % WIDTH;
    const y = Math.floor(index / WIDTH);
    return 0.055
      + (x / WIDTH) * 0.035
      + Math.sin((x + y + phase) * 0.35) * 0.012
      + gaussian(x, y, firstX, firstY, 2.8) * 0.93
      + gaussian(x, y, secondX, secondY, 2.25) * 0.76
      + gaussian(x, y, 17, 20.5, 5.8) * 0.22;
  });
  const max = Math.max(...raw);
  const min = Math.min(...raw);
  return raw.map((value) => Number(clamp((value - min) / (max - min)).toFixed(4)));
}

export function createMockSnapshot(sequence = 0, now = new Date()) {
  const phase = sequence * 0.18;
  const timestamp = now.toISOString();
  const sound = clamp(0.18 + Math.sin(phase * 1.15) * 0.035 + Math.cos(phase * 0.38) * 0.012);
  return {
    schema_version: "1.0",
    generated_at: timestamp,
    room: {
      schema_version: "1.0",
      room_id: "room_a",
      name: "学习空间 A",
      location: "本机演示节点",
      observed_at: timestamp,
      received_at: timestamp,
      room_state: "quiet_study_recommended",
      occupancy_level: "low",
      suitability_score: 88,
      confidence: 0.92,
      features: {
        thermal_hot_region_count: 2,
        radar_active_target_count: null,
        sound_rms_mean: Number(sound.toFixed(4)),
        sound_peak_max: Number(clamp(sound * 1.8).toFixed(4)),
        light_relative_mean: Number(clamp(0.56 + Math.sin(phase * 0.75) * 0.08).toFixed(4)),
        light_lux: Number((438 + Math.sin(phase * 0.75) * 32 + Math.cos(phase * 0.22) * 9).toFixed(1)),
        temperature_c: Number((24.6 + Math.sin(phase * 0.55) * 0.55).toFixed(2)),
        humidity_pct: Number((57.8 + Math.cos(phase * 0.42) * 2.4).toFixed(2))
      },
      sensor_health: { thermal: "ok", radar: "not_configured", sound: "ok", environment: "ok" },
      warnings: ["MOCK_DATA"],
      data_age_seconds: 0,
      is_stale: false,
      forecasts: []
    },
    sound_preview: {
      schema_version: "1.0",
      room_id: "room_a",
      available: true,
      captured_at: timestamp,
      rms: Number(sound.toFixed(4)),
      expires_at: new Date(now.getTime() + 3000).toISOString(),
      unavailable_reason: null
    },
    thermal_preview: {
      schema_version: "1.0",
      room_id: "room_a",
      available: true,
      captured_at: timestamp,
      width: WIDTH,
      height: HEIGHT,
      values: createThermalFrame(sequence),
      normalization: "window_min_max_clipped",
      expires_at: new Date(now.getTime() + 30000).toISOString(),
      unavailable_reason: null
    }
  };
}

export function isLiveSensorSnapshot(value) {
  if (!value || typeof value !== "object") return false;
  const preview = value.thermal_preview;
  const sound = value.sound_preview;
  return value.schema_version === "1.0"
    && typeof value.generated_at === "string"
    && Boolean(value.room && typeof value.room.room_id === "string" && value.room.features)
    && Boolean(sound && typeof sound.available === "boolean")
    && (!sound.available || (typeof sound.rms === "number" && typeof sound.captured_at === "string"))
    && Boolean(preview && typeof preview.available === "boolean")
    && (!preview.available || (preview.width === 32 && preview.height === 24 && preview.values?.length === 768));
}

export function isFreshLiveSensorSnapshot(value) {
  return isLiveSensorSnapshot(value) && value.room.is_stale === false;
}
