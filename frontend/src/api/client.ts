import { buildDashboardData, mockRooms } from "../mocks/mockData";
import type {
  AuthCredentials,
  AuthSessionResponse,
  AuthenticatedRecommendationRequest,
  DashboardData,
  LiveSensorSnapshotResponse,
  MePreferenceResponse,
  MePreferenceUpdate,
  RecommendationRequest,
  RoomHistoryResponse,
  RoomSelectionAccepted,
  RoomSelectionRequest,
  RoomStatus,
  SoundPreviewResponse,
  ThermalPreviewResponse,
  UserResponse,
} from "../types/contracts";

const QUERY_MODE = new URLSearchParams(window.location.search).get("mode");
const API_MODE = QUERY_MODE === "api" ? "real" : QUERY_MODE === "mock" ? "mock" : (import.meta.env.VITE_API_MODE ?? "mock");
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? "" : "http://127.0.0.1:8000";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, "");
const CSRF_STORAGE_KEY = "pssa-csrf-token";

export const isRealApi = API_MODE === "real";

export const defaultRequest: RecommendationRequest = {
  schema_version: "1.0",
  profile_id: "demo-user",
  study_mode: "quiet",
  preferences: {
    quiet_priority: 0.8,
    low_occupancy_priority: 0.7,
    brightness_priority: 0.3,
    comfort_priority: 0.4,
    distance_priority: 0.2,
  },
  candidate_room_ids: ["room_a", "room_b", "room_c", "room_d"],
};

export async function loadDashboardData(request: RecommendationRequest): Promise<DashboardData> {
  if (API_MODE === "mock") {
    await delay(150);
    return buildDashboardData(request);
  }
  const rooms = await getJson<{ rooms: RoomStatus[] }>("/api/v1/rooms/status");
  const candidates = rooms.rooms.map((room) => room.room_id);
  const requestWithCandidates = { ...request, candidate_room_ids: candidates.length ? candidates : request.candidate_room_ids };
  const session = await optionalSessionState();
  const recommendations = session.user
    ? await postJson<AuthenticatedRecommendationRequest, DashboardData["recommendations"]>("/api/v1/me/recommendations", {
        schema_version: "1.0",
        study_mode: request.study_mode,
        candidate_room_ids: requestWithCandidates.candidate_room_ids,
      })
    : await postJson<RecommendationRequest, DashboardData["recommendations"]>("/api/v1/recommendations", requestWithCandidates, { csrf: false });
  const histories = Object.fromEntries(await Promise.all(candidates.map(async (roomId) => [roomId, await getJson<RoomHistoryResponse>(`/api/v1/rooms/${roomId}/history?hours=1&bucket_minutes=5`)])));
  const thermalPreviews = Object.fromEntries(await Promise.all(candidates.map(async (roomId) => [roomId, await getJson<ThermalPreviewResponse>(`/api/v1/rooms/${roomId}/thermal-preview`)])));
  return {
    rooms: rooms.rooms,
    recommendations,
    histories,
    thermalPreviews,
    backendStatus: "ok",
    lastUpdated: new Date().toISOString(),
    user: session.user,
    preferences: session.preferences,
    authenticated: Boolean(session.user),
  };
}

export function allCandidateIds() {
  return mockRooms.map((room) => room.room_id);
}

export async function loadLiveSensorSnapshot(roomId: string) {
  return getJson<LiveSensorSnapshotResponse>(`/api/v1/rooms/${encodeURIComponent(roomId)}/live`);
}

export async function loadSoundPreview(roomId: string) {
  return getJson<SoundPreviewResponse>(`/api/v1/rooms/${encodeURIComponent(roomId)}/sound-preview`);
}

export async function register(credentials: Omit<AuthCredentials, "schema_version">) {
  const response = await postJson<AuthCredentials, AuthSessionResponse>(
    "/api/v1/auth/register",
    { schema_version: "1.0", ...credentials },
    { csrf: false },
  );
  rememberCsrf(response.csrf_token);
  return response;
}

export async function login(credentials: Omit<AuthCredentials, "schema_version">) {
  const response = await postJson<AuthCredentials, AuthSessionResponse>(
    "/api/v1/auth/login",
    { schema_version: "1.0", ...credentials },
    { csrf: false },
  );
  rememberCsrf(response.csrf_token);
  return response;
}

export async function logout() {
  if (!isRealApi) return;
  await postJson<Record<string, never>, unknown>("/api/v1/auth/logout", {});
  rememberCsrf(null);
}

export async function saveMyPreferences(request: RecommendationRequest, learningEnabled: boolean) {
  if (!isRealApi) return null;
  const body: MePreferenceUpdate = {
    schema_version: "1.0",
    study_mode: request.study_mode,
    quiet_priority: request.preferences.quiet_priority,
    low_occupancy_priority: request.preferences.low_occupancy_priority,
    brightness_priority: request.preferences.brightness_priority,
    comfort_priority: request.preferences.comfort_priority,
    distance_priority: request.preferences.distance_priority,
    preferred_temperature_c: null,
    learning_enabled: learningEnabled,
  };
  return putJson<MePreferenceUpdate, MePreferenceResponse>("/api/v1/me/preferences", body);
}

export async function recordRoomSelection(roomId: string, recommendationRequestId: string | null, source: RoomSelectionRequest["source"]) {
  if (!isRealApi) return null;
  const body: RoomSelectionRequest = {
    schema_version: "1.0",
    selection_id: selectionId(),
    room_id: roomId,
    recommendation_request_id: recommendationRequestId,
    source,
  };
  return postJson<RoomSelectionRequest, RoomSelectionAccepted>("/api/v1/me/room-selections", body);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  if (!response.ok) throw new Error(`GET ${path} failed with ${response.status}`);
  return response.json() as Promise<T>;
}

async function postJson<Body, Result>(path: string, body: Body, options: { csrf?: boolean } = {}) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.csrf !== false) {
    const token = csrfToken();
    if (token) headers["X-CSRF-Token"] = token;
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`POST ${path} failed with ${response.status}`);
  return response.json() as Promise<Result>;
}

async function putJson<Body, Result>(path: string, body: Body) {
  const token = csrfToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-CSRF-Token": token } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`PUT ${path} failed with ${response.status}`);
  return response.json() as Promise<Result>;
}

async function optionalSessionState(): Promise<{ user: UserResponse | null; preferences: MePreferenceResponse | null }> {
  try {
    const user = await getJson<UserResponse>("/api/v1/me");
    const preferences = await getJson<MePreferenceResponse>("/api/v1/me/preferences");
    return { user, preferences };
  } catch {
    rememberCsrf(null);
    return { user: null, preferences: null };
  }
}

function csrfToken() {
  return window.sessionStorage.getItem(CSRF_STORAGE_KEY) ?? cookieValue("pssa_csrf");
}

function rememberCsrf(token: string | null) {
  if (token) {
    window.sessionStorage.setItem(CSRF_STORAGE_KEY, token);
  } else {
    window.sessionStorage.removeItem(CSRF_STORAGE_KEY);
  }
}

function cookieValue(name: string) {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function selectionId() {
  if ("randomUUID" in crypto) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (char) =>
    (Number(char) ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(char) / 4)))).toString(16),
  );
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
