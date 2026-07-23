import type {
  DashboardData,
  HistoryPoint,
  OccupancyLevel,
  RecommendationItem,
  RecommendationRequest,
  RecommendationResponse,
  RoomHistoryResponse,
  RoomState,
  RoomStatus,
  StudyMode,
  ThermalPreviewResponse,
} from "../types/contracts";

const now = () => new Date();
const iso = (offsetMinutes = 0) => new Date(now().getTime() + offsetMinutes * 60_000).toISOString();

const occupancyScore: Record<OccupancyLevel, number> = {
  empty: 100,
  low: 86,
  medium: 48,
  high: 10,
  unknown: 28,
};

const modeScore = (state: RoomState, mode: StudyMode) => {
  if (mode === "quiet") {
    if (state === "quiet_study_recommended") return 100;
    if (state === "empty_or_low_activity") return 90;
    if (state === "discussion_allowed") return 54;
    if (state === "not_recommended_noisy_or_crowded") return 8;
    return 24;
  }
  if (mode === "discussion") {
    if (state === "discussion_allowed") return 100;
    if (state === "empty_or_low_activity") return 74;
    if (state === "quiet_study_recommended") return 62;
    if (state === "not_recommended_noisy_or_crowded") return 36;
    return 30;
  }
  return state === "unknown" ? 40 : 78;
};

export const mockRooms: RoomStatus[] = [
  {
    schema_version: "1.0",
    room_id: "room_a",
    name: "Quiet Commons",
    location: "Library Level 2",
    observed_at: iso(-1),
    received_at: iso(-1),
    room_state: "quiet_study_recommended",
    occupancy_level: "low",
    suitability_score: 88,
    confidence: 0.91,
    features: {
      thermal_hot_region_count: 2,
      radar_active_target_count: null,
      sound_rms_mean: 0.16,
      sound_peak_max: 0.22,
      light_relative_mean: 0.56,
      light_lux: null,
      temperature_c: 24,
      humidity_pct: 52,
    },
    sensor_health: { thermal: "ok", radar: "not_configured", sound: "ok", environment: "ok" },
    warnings: [],
    data_age_seconds: 18,
    is_stale: false,
    forecasts: [forecast("room_a", 15, "low"), forecast("room_a", 30, "low")],
  },
  {
    schema_version: "1.0",
    room_id: "room_b",
    name: "Discussion Hub",
    location: "Learning Centre",
    observed_at: iso(-2),
    received_at: iso(-2),
    room_state: "discussion_allowed",
    occupancy_level: "medium",
    suitability_score: 72,
    confidence: 0.82,
    features: { thermal_hot_region_count: 5, radar_active_target_count: 4, sound_rms_mean: 0.43, light_lux: 510, temperature_c: 25.5, humidity_pct: 57 },
    sensor_health: { thermal: "ok", radar: "ok", sound: "ok", environment: "ok" },
    warnings: [],
    data_age_seconds: 28,
    is_stale: false,
    forecasts: [forecast("room_b", 15, "medium"), forecast("room_b", 30, "medium")],
  },
  {
    schema_version: "1.0",
    room_id: "room_c",
    name: "Atrium Tables",
    location: "Main Atrium",
    observed_at: iso(-12),
    received_at: iso(-12),
    room_state: "not_recommended_noisy_or_crowded",
    occupancy_level: "high",
    suitability_score: 38,
    confidence: 0.49,
    features: { thermal_hot_region_count: 9, radar_active_target_count: 8, sound_rms_mean: 0.72, light_lux: 760, temperature_c: 27.2, humidity_pct: 68 },
    sensor_health: { thermal: "ok", radar: "degraded", sound: "ok", environment: "ok" },
    warnings: ["RADAR_DEGRADED"],
    data_age_seconds: 720,
    is_stale: true,
    forecasts: [forecast("room_c", 15, "high"), forecast("room_c", 30, "high")],
  },
  {
    schema_version: "1.0",
    room_id: "room_d",
    name: "North Nook",
    location: "Library Level 3",
    observed_at: null,
    received_at: null,
    room_state: "unknown",
    occupancy_level: "unknown",
    suitability_score: null,
    confidence: 0.2,
    features: {},
    sensor_health: { thermal: "offline", radar: "offline", sound: "not_configured", environment: "not_configured" },
    warnings: ["NO_OBSERVATION"],
    data_age_seconds: null,
    is_stale: true,
    forecasts: [forecast("room_d", 15, "unknown"), forecast("room_d", 30, "unknown")],
  },
];

export function buildMockRecommendation(request: RecommendationRequest, rooms = mockRooms): RecommendationResponse {
  const recommendations: RecommendationItem[] = [...rooms]
    .filter((room) => request.candidate_room_ids.includes(room.room_id))
    .map((room) => {
      const forecast30 = room.forecasts.find((item) => item.horizon_minutes === 30)?.predicted_occupancy_level ?? "unknown";
      const weights = request.study_mode === "discussion" ? { mode: 0.72, occupancy: 0.16, forecast: 0.12 } : { mode: 0.45, occupancy: 0.3, forecast: 0.25 };
      const raw =
        modeScore(room.room_state, request.study_mode) * weights.mode +
        occupancyScore[room.occupancy_level] * weights.occupancy +
        occupancyScore[forecast30] * weights.forecast;
      const penalty = (room.is_stale ? 0.72 : 1) * ((room.confidence ?? 0) < 0.55 ? 0.82 : 1) * (Object.values(room.sensor_health).includes("degraded") ? 0.9 : 1);
      return {
        room_id: room.room_id,
        rank: 0,
        score: Math.max(0, Math.min(100, Math.round(raw * penalty))),
        current_state: room.room_state,
        occupancy_level: room.occupancy_level,
        forecast_30m: forecast30,
        confidence: room.confidence ?? 0,
        is_stale: room.is_stale,
        reasons: reasonsFor(room, request.study_mode, forecast30),
        explanation: "",
        explanation_source: "template" as const,
      };
    })
    .sort((a, b) => Number(a.is_stale) - Number(b.is_stale) || b.score - a.score || b.confidence - a.confidence || a.room_id.localeCompare(b.room_id))
    .map((item, index) => ({
      ...item,
      rank: index + 1,
      explanation: `${roomName(item.room_id)} is ranked #${index + 1}: ${item.reasons
        .slice(0, 2)
        .map((reason) => reason.replace(/\.$/, ""))
        .join("; ")}.`,
    }));
  return {
    schema_version: "1.0",
    request_id: "mock-request",
    generated_at: iso(),
    recommendations,
    warnings: recommendations.some((item) => item.is_stale) ? ["LLM_TEMPLATE_FALLBACK", "STALE_ROOMS_PRESENT"] : ["LLM_TEMPLATE_FALLBACK"],
  };
}

export function buildDashboardData(request: RecommendationRequest): DashboardData {
  return {
    rooms: mockRooms,
    recommendations: buildMockRecommendation(request),
    histories: Object.fromEntries(mockRooms.map((room) => [room.room_id, history(room.room_id)])),
    thermalPreviews: Object.fromEntries(mockRooms.map((room) => [room.room_id, thermal(room.room_id)])),
    backendStatus: "degraded",
    lastUpdated: iso(),
  };
}

function forecast(room_id: string, minutes: 15 | 30, level: OccupancyLevel) {
  return {
    schema_version: "1.0" as const,
    room_id,
    generated_at: iso(),
    target_at: iso(minutes),
    horizon_minutes: minutes,
    predicted_occupancy_level: level,
    confidence: level === "unknown" ? 0.2 : 0.78,
    method: "mock",
    model_version: "mock-1",
    input_start_at: iso(-60),
    input_end_at: iso(),
    fallback_reason: level === "unknown" ? "insufficient_data" : null,
  };
}

function history(room_id: string): RoomHistoryResponse {
  const levels: OccupancyLevel[] = room_id === "room_b" ? ["low", "medium", "medium", "high", "medium", "low"] : room_id === "room_c" ? ["medium", "high", "high", "high", "medium", "high"] : ["empty", "low", "low", "low", "empty", "low"];
  const points: HistoryPoint[] = Array.from({ length: 12 }, (_, index) => {
    const level = levels[index % levels.length];
    return {
      bucket_start: iso(-60 + index * 5),
      bucket_end: iso(-55 + index * 5),
      observation_count: room_id === "room_d" ? 0 : 5,
      coverage: room_id === "room_d" ? 0 : 0.92,
      dominant_room_state: room_id === "room_b" ? "discussion_allowed" : room_id === "room_c" ? "not_recommended_noisy_or_crowded" : "quiet_study_recommended",
      last_room_state: room_id === "room_d" ? "unknown" : room_id === "room_b" ? "discussion_allowed" : "quiet_study_recommended",
      occupancy_level: room_id === "room_d" ? "unknown" : level,
      occupancy_mean: room_id === "room_d" ? null : occupancyScore[level] / 33,
      suitability_mean: room_id === "room_d" ? null : 90 - index * 2,
      confidence_mean: room_id === "room_d" ? null : 0.84,
      sound_rms_mean: room_id === "room_c" ? 0.7 : room_id === "room_b" ? 0.44 : 0.18,
      light_lux_mean: room_id === "room_c" ? 760 : 440,
      temperature_c_mean: room_id === "room_c" ? 27 : 24,
      humidity_pct_mean: room_id === "room_c" ? 68 : 52,
    };
  });
  return { schema_version: "1.0", room_id, start_at: iso(-60), end_at: iso(), bucket_minutes: 5, points };
}

function thermal(room_id: string): ThermalPreviewResponse {
  if (room_id === "room_c" || room_id === "room_d") {
    return { schema_version: "1.0", room_id, available: false, captured_at: null, width: null, height: null, values: null, normalization: null, expires_at: null, unavailable_reason: room_id === "room_c" ? "expired" : "not_available" };
  }
  const values = Array.from({ length: 32 * 24 }, (_, index) => {
    const x = index % 32;
    const y = Math.floor(index / 32);
    const center = room_id === "room_a" ? Math.hypot(x - 10, y - 12) : Math.min(Math.hypot(x - 9, y - 8), Math.hypot(x - 22, y - 14));
    return Math.max(0, Math.min(1, 1 - center / 18));
  });
  return { schema_version: "1.0", room_id, available: true, captured_at: iso(), width: 32, height: 24, values, normalization: "window_min_max_clipped", expires_at: iso(0.5), unavailable_reason: null };
}

function reasonsFor(room: RoomStatus, mode: StudyMode, forecast30: OccupancyLevel) {
  const reasons: string[] = [];
  if (mode === "quiet" && room.room_state === "quiet_study_recommended") reasons.push("Current state matches quiet study.");
  if (mode === "discussion" && room.room_state === "discussion_allowed") reasons.push("Current state supports discussion.");
  if (["empty", "low"].includes(room.occupancy_level)) reasons.push("Current occupancy is low.");
  if (["empty", "low"].includes(forecast30)) reasons.push("Forecast stays lightly occupied for 30 minutes.");
  if (room.is_stale) reasons.push("Data is stale, so use caution.");
  if ((room.confidence ?? 0) < 0.55) reasons.push("Model confidence is low.");
  if (Object.values(room.sensor_health).includes("degraded")) reasons.push("One sensor is degraded.");
  if (room.room_state === "unknown") reasons.push("Current state is unknown.");
  return reasons.slice(0, 4);
}

function roomName(roomId: string) {
  return mockRooms.find((room) => room.room_id === roomId)?.name ?? roomId;
}
