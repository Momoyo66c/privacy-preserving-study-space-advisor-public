export type RoomState =
  | "empty_or_low_activity"
  | "quiet_study_recommended"
  | "discussion_allowed"
  | "not_recommended_noisy_or_crowded"
  | "unknown";

export type OccupancyLevel = "empty" | "low" | "medium" | "high" | "unknown";
export type SensorHealth = "ok" | "degraded" | "offline" | "not_configured";
export type StudyMode = "quiet" | "discussion" | "any";

export interface FeatureSummary {
  thermal_hot_region_count?: number | null;
  radar_active_target_count?: number | null;
  sound_rms_mean?: number | null;
  sound_peak_max?: number | null;
  light_relative_mean?: number | null;
  light_lux?: number | null;
  temperature_c?: number | null;
  humidity_pct?: number | null;
}

export interface ForecastResult {
  schema_version: "1.0";
  room_id: string;
  generated_at: string;
  target_at: string;
  horizon_minutes: 15 | 30;
  predicted_occupancy_level: OccupancyLevel;
  confidence: number;
  method: string;
  model_version: string;
  input_start_at: string | null;
  input_end_at: string | null;
  fallback_reason: string | null;
}

export interface RoomStatus {
  schema_version: "1.0";
  room_id: string;
  name: string;
  location: string | null;
  observed_at: string | null;
  received_at: string | null;
  room_state: RoomState;
  occupancy_level: OccupancyLevel;
  suitability_score: number | null;
  confidence: number | null;
  features: FeatureSummary;
  sensor_health: Record<string, SensorHealth>;
  warnings: string[];
  data_age_seconds: number | null;
  is_stale: boolean;
  forecasts: ForecastResult[];
}

export interface HistoryPoint {
  bucket_start: string;
  bucket_end: string;
  observation_count: number;
  coverage: number;
  dominant_room_state: RoomState;
  last_room_state: RoomState;
  occupancy_level: OccupancyLevel;
  occupancy_mean: number | null;
  suitability_mean: number | null;
  confidence_mean: number | null;
  sound_rms_mean: number | null;
  light_lux_mean: number | null;
  temperature_c_mean: number | null;
  humidity_pct_mean: number | null;
}

export interface RoomHistoryResponse {
  schema_version: "1.0";
  room_id: string;
  start_at: string;
  end_at: string;
  bucket_minutes: 1 | 5 | 15 | 30 | 60;
  points: HistoryPoint[];
}

export interface ThermalPreviewResponse {
  schema_version: "1.0";
  room_id: string;
  available: boolean;
  captured_at: string | null;
  width: number | null;
  height: number | null;
  values: number[] | null;
  normalization: string | null;
  expires_at: string | null;
  unavailable_reason: string | null;
}

export interface SoundPreviewResponse {
  schema_version: "1.0";
  room_id: string;
  available: boolean;
  captured_at: string | null;
  rms: number | null;
  expires_at: string | null;
  unavailable_reason: string | null;
}

export interface PeopleCountPreviewResponse {
  schema_version: "people_count_prediction.v1";
  room_id: string;
  available: boolean;
  observed_at: string | null;
  predicted_people_count: number | null;
  predicted_people_count_rounded: number | null;
  occupancy_level: OccupancyLevel | null;
  confidence: number | null;
  model: {
    name: string;
    version: string;
    feature_schema_version: string;
  } | null;
  warnings: string[];
  expires_at: string | null;
  unavailable_reason: string | null;
}

export interface ThermalDetectionBox {
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  peak_intensity: number;
}

export interface ThermalAnalysisResponse {
  schema_version: "1.0";
  available: boolean;
  method: "thermal_connected_regions";
  threshold: number | null;
  detected_region_count: number;
  estimated_people_count: number | null;
  count_source: "people_count_model" | "thermal_regions" | "room_observation" | "unavailable";
  boxes: ThermalDetectionBox[];
}

export interface LiveSensorSnapshotResponse {
  schema_version: "1.0";
  generated_at: string;
  room: RoomStatus;
  thermal_preview: ThermalPreviewResponse;
  sound_preview: SoundPreviewResponse;
  people_count: PeopleCountPreviewResponse;
  thermal_analysis: ThermalAnalysisResponse;
}

export interface RecommendationPreferences {
  quiet_priority: number;
  low_occupancy_priority: number;
  brightness_priority: number;
  comfort_priority: number;
  distance_priority: number;
}

export interface RecommendationRequest {
  schema_version: "1.0";
  profile_id: string;
  study_mode: StudyMode;
  preferences: RecommendationPreferences;
  candidate_room_ids: string[];
}

export interface AuthenticatedRecommendationRequest {
  schema_version: "1.0";
  study_mode: StudyMode;
  candidate_room_ids: string[];
}

export interface RecommendationItem {
  room_id: string;
  rank: number;
  score: number;
  current_state: RoomState;
  occupancy_level: OccupancyLevel;
  forecast_30m: OccupancyLevel;
  confidence: number;
  is_stale: boolean;
  reasons: string[];
  explanation: string;
  explanation_source: "stub" | "template" | "llm";
}

export interface RecommendationResponse {
  schema_version: "1.0";
  request_id: string;
  generated_at: string;
  recommendations: RecommendationItem[];
  warnings: string[];
}

export interface UserResponse {
  schema_version: "1.0";
  user_id: string;
  username: string;
  role: "student" | "admin";
  created_at: string;
}

export interface AuthCredentials {
  schema_version: "1.0";
  username: string;
  password: string;
}

export interface AuthSessionResponse {
  schema_version: "1.0";
  user: UserResponse;
  csrf_token: string;
  expires_at: string;
}

export interface PreferenceSnapshot {
  study_mode: StudyMode;
  quiet_priority: number;
  low_occupancy_priority: number;
  brightness_priority: number;
  comfort_priority: number;
  distance_priority: number;
  preferred_temperature_c: number | null;
}

export interface LearnedPreferenceValues {
  quiet_priority: number | null;
  low_occupancy_priority: number | null;
  brightness_priority: number | null;
  comfort_priority: number | null;
  distance_priority: null;
}

export interface PreferenceEvidenceCounts {
  quiet_priority: number;
  low_occupancy_priority: number;
  brightness_priority: number;
  comfort_priority: number;
  distance_priority: 0;
}

export interface MePreferenceResponse {
  schema_version: "1.0";
  manual: PreferenceSnapshot;
  learned: LearnedPreferenceValues;
  effective: PreferenceSnapshot;
  evidence_counts: PreferenceEvidenceCounts;
  learning_enabled: boolean;
  updated_at: string;
}

export interface MePreferenceUpdate extends PreferenceSnapshot {
  schema_version: "1.0";
  learning_enabled: boolean;
}

export interface RoomSelectionRequest {
  schema_version: "1.0";
  selection_id: string;
  room_id: string;
  recommendation_request_id: string | null;
  source: "recommendation" | "room_detail";
}

export interface RoomSelectionAccepted {
  schema_version: "1.0";
  accepted: true;
  selection_id: string;
  room_id: string;
  recorded_at: string;
  effective_preferences: PreferenceSnapshot;
}

export interface RoomSelectionHistoryItem {
  selection_id: string;
  room_id: string;
  room_name: string;
  source: "recommendation" | "room_detail";
  recommendation_request_id: string | null;
  recorded_at: string;
  selected_rank: number | null;
  selected_score: number | null;
  evidence: Record<string, number>;
}

export interface RoomSelectionHistoryResponse {
  schema_version: "1.0";
  selections: RoomSelectionHistoryItem[];
  next_cursor: string | null;
}

export interface DeleteResult {
  schema_version: "1.0";
  deleted: boolean;
  deleted_count: number;
}

export interface DashboardData {
  rooms: RoomStatus[];
  recommendations: RecommendationResponse;
  histories: Record<string, RoomHistoryResponse>;
  thermalPreviews: Record<string, ThermalPreviewResponse>;
  backendStatus: "ok" | "degraded" | "offline";
  lastUpdated: string;
  user?: UserResponse | null;
  preferences?: MePreferenceResponse | null;
  selectionHistory?: RoomSelectionHistoryResponse | null;
  authenticated?: boolean;
}

export interface WeatherInfo {
  temperatureC: number;
  apparentTemperatureC: number;
  humidityPercent: number;
  windKph: number;
  weatherCode: number;
  observedAt: string;
  locationLabel: string;
  stationName: string;
  condition: string;
  source: "nea" | "nea_cache";
  isCached: boolean;
}
