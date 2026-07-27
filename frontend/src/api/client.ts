import { buildDashboardData, buildMockRecommendation, mockLiveSensorSnapshot, mockRooms } from "../mocks/mockData";
import type {
  AuthCredentials,
  AuthSessionResponse,
  AuthenticatedRecommendationRequest,
  DashboardData,
  LiveSensorSnapshotResponse,
  MePreferenceResponse,
  MePreferenceUpdate,
  RecommendationRequest,
  RoomStatus,
  UserResponse,
  WeatherInfo,
} from "../types/contracts";

const QUERY_MODE = new URLSearchParams(window.location.search).get("mode");
const API_MODE = QUERY_MODE === "api" ? "real" : QUERY_MODE === "mock" ? "mock" : (import.meta.env.VITE_API_MODE ?? "mock");
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? "" : "http://127.0.0.1:8000";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, "");
const CSRF_STORAGE_KEY = "pssa-csrf-token";
const CSRF_COOKIE = "pssa_csrf";
const MOCK_SESSION_KEY = "pssa-mock-session";
const MOCK_ACCOUNTS_KEY = "pssa-mock-accounts";
const MOCK_PREFERENCES_KEY = "pssa-mock-preferences";
const WEATHER_CACHE_KEY = "pssa-weather-cache-v1";
const WEATHER_CACHE_MAX_AGE_MS = 6 * 60 * 60 * 1000;

type MockAccount = UserResponse & { passwordHash: string };

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
  candidate_room_ids: ["room_a", "room_b", "room_c", "room_d", "room_e", "room_f", "room_g", "room_h", "room_i"],
};

const defaultPreferenceResponse = (request = defaultRequest): MePreferenceResponse => ({
  schema_version: "1.0",
  manual: { ...request.preferences, study_mode: request.study_mode, preferred_temperature_c: null },
  learned: {
    quiet_priority: null,
    low_occupancy_priority: null,
    brightness_priority: null,
    comfort_priority: null,
    distance_priority: null,
  },
  effective: { ...request.preferences, study_mode: request.study_mode, preferred_temperature_c: null },
  evidence_counts: {
    quiet_priority: 0,
    low_occupancy_priority: 0,
    brightness_priority: 0,
    comfort_priority: 0,
    distance_priority: 0,
  },
  learning_enabled: true,
  updated_at: new Date().toISOString(),
});

export async function restoreSession(): Promise<UserResponse | null> {
  if (!isRealApi) {
    const userId = window.localStorage.getItem(MOCK_SESSION_KEY);
    return mockAccounts().find((account) => account.user_id === userId) ?? null;
  }
  try {
    return await getJson<UserResponse>("/api/v1/me");
  } catch {
    rememberCsrf(null);
    return null;
  }
}

export async function register(credentials: Omit<AuthCredentials, "schema_version">): Promise<AuthSessionResponse> {
  if (!isRealApi) {
    const username = credentials.username.trim().toLowerCase();
    const accounts = mockAccounts();
    if (username === "admin") throw new Error("该用户名为管理员保留。");
    if (accounts.some((account) => account.username === username)) throw new Error("用户名已存在。");
    if (credentials.password.length < 8) throw new Error("密码至少需要 8 个字符。");
    const account: MockAccount = {
      schema_version: "1.0",
      user_id: `mock-${Date.now()}`,
      username,
      role: "student",
      created_at: new Date().toISOString(),
      passwordHash: await mockPasswordHash(credentials.password),
    };
    saveMockAccounts([...accounts, account]);
    window.localStorage.setItem(MOCK_SESSION_KEY, account.user_id);
    saveMockPreference(account.user_id, defaultPreferenceResponse());
    return mockSession(account);
  }
  const result = await postJson<AuthCredentials, AuthSessionResponse>(
    "/api/v1/auth/register",
    { schema_version: "1.0", ...credentials },
    { csrf: false },
  );
  rememberCsrf(result.csrf_token);
  return result;
}

export async function login(credentials: Omit<AuthCredentials, "schema_version">): Promise<AuthSessionResponse> {
  if (!isRealApi) {
    const username = credentials.username.trim().toLowerCase();
    const account = mockAccounts().find((item) => item.username === username);
    if (!account || account.passwordHash !== (await mockPasswordHash(credentials.password))) {
      throw new Error("用户名或密码不正确。");
    }
    window.localStorage.setItem(MOCK_SESSION_KEY, account.user_id);
    return mockSession(account);
  }
  const result = await postJson<AuthCredentials, AuthSessionResponse>(
    "/api/v1/auth/login",
    { schema_version: "1.0", ...credentials },
    { csrf: false },
  );
  rememberCsrf(result.csrf_token);
  return result;
}

export async function logout() {
  if (!isRealApi) {
    window.localStorage.removeItem(MOCK_SESSION_KEY);
    return;
  }
  await postJson<Record<string, never>, unknown>("/api/v1/auth/logout", {});
  rememberCsrf(null);
}

export async function loadMyPreferences(user: UserResponse): Promise<MePreferenceResponse> {
  if (!isRealApi) return mockPreference(user.user_id);
  return getJson<MePreferenceResponse>("/api/v1/me/preferences");
}

export async function saveMyPreferences(
  user: UserResponse,
  request: RecommendationRequest,
  learningEnabled = true,
): Promise<MePreferenceResponse> {
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
  if (!isRealApi) {
    const response: MePreferenceResponse = {
      ...defaultPreferenceResponse(request),
      learning_enabled: learningEnabled,
      updated_at: new Date().toISOString(),
    };
    saveMockPreference(user.user_id, response);
    return response;
  }
  return putJson<MePreferenceUpdate, MePreferenceResponse>("/api/v1/me/preferences", body);
}

export async function loadDashboardData(user: UserResponse, request: RecommendationRequest): Promise<DashboardData> {
  if (!isRealApi) {
    await delay(120);
    const preferences = mockPreference(user.user_id);
    const effectiveRequest = requestFromPreferences(preferences, request.candidate_room_ids, user.user_id);
    return {
      ...buildDashboardData(effectiveRequest),
      recommendations: buildMockRecommendation(effectiveRequest),
      user,
      preferences,
      authenticated: true,
      backendStatus: "ok",
    };
  }
  const roomsResponse = await getJson<{ rooms: RoomStatus[] }>("/api/v1/rooms/status");
  const candidateRoomIds = roomsResponse.rooms.map((room) => room.room_id);
  const body: AuthenticatedRecommendationRequest = {
    schema_version: "1.0",
    study_mode: request.study_mode,
    candidate_room_ids: candidateRoomIds,
  };
  const [recommendations, preferences] = await Promise.all([
    postJson<AuthenticatedRecommendationRequest, DashboardData["recommendations"]>("/api/v1/me/recommendations", body, { csrf: false }),
    loadMyPreferences(user),
  ]);
  return {
    rooms: roomsResponse.rooms,
    recommendations,
    histories: {},
    thermalPreviews: {},
    backendStatus: "ok",
    lastUpdated: new Date().toISOString(),
    user,
    preferences,
    authenticated: true,
  };
}

export async function loadLiveSensorSnapshot(roomId: string): Promise<LiveSensorSnapshotResponse> {
  if (!isRealApi) {
    await delay(90);
    return mockLiveSensorSnapshot(roomId);
  }
  return getJson<LiveSensorSnapshotResponse>(`/api/v1/rooms/${encodeURIComponent(roomId)}/live`);
}

export async function loadWeather(): Promise<WeatherInfo> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/weather`, {
      credentials: "include",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("天气暂时不可用");
    const payload = (await response.json()) as {
      source: "nea" | "nea_cache";
      is_cached: boolean;
      station_name: string;
      location_label: string;
      observed_at: string;
      temperature_c: number;
      apparent_temperature_c: number;
      humidity_percent: number;
      wind_kph: number;
      weather_code: number;
      condition: string;
    };
    const weather: WeatherInfo = {
      temperatureC: payload.temperature_c,
      apparentTemperatureC: payload.apparent_temperature_c,
      humidityPercent: payload.humidity_percent,
      windKph: payload.wind_kph,
      weatherCode: payload.weather_code,
      observedAt: payload.observed_at,
      locationLabel: payload.location_label,
      stationName: payload.station_name,
      condition: payload.condition,
      source: payload.source,
      isCached: payload.is_cached,
    };
    window.localStorage.setItem(WEATHER_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), weather }));
    return weather;
  } catch {
    const cached = readWeatherCache();
    if (cached) return { ...cached, source: "nea_cache", isCached: true };
    throw new Error("天气暂时不可用");
  } finally {
    window.clearTimeout(timeout);
  }
}

function readWeatherCache(): WeatherInfo | null {
  try {
    const cached = JSON.parse(window.localStorage.getItem(WEATHER_CACHE_KEY) ?? "null") as {
      savedAt?: number;
      weather?: WeatherInfo;
    } | null;
    if (!cached?.savedAt || !cached.weather || Date.now() - cached.savedAt > WEATHER_CACHE_MAX_AGE_MS) return null;
    return cached.weather;
  } catch {
    return null;
  }
}

function requestFromPreferences(preferences: MePreferenceResponse, candidateRoomIds: string[], profileId: string): RecommendationRequest {
  return {
    schema_version: "1.0",
    profile_id: profileId,
    study_mode: preferences.effective.study_mode,
    preferences: {
      quiet_priority: preferences.effective.quiet_priority,
      low_occupancy_priority: preferences.effective.low_occupancy_priority,
      brightness_priority: preferences.effective.brightness_priority,
      comfort_priority: preferences.effective.comfort_priority,
      distance_priority: preferences.effective.distance_priority,
    },
    candidate_room_ids: candidateRoomIds,
  };
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  return parseResponse<T>(response);
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
  return parseResponse<Result>(response);
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
  return parseResponse<Result>(response);
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = `请求失败 (${response.status})`;
  try {
    const payload = (await response.json()) as { error?: { message?: string } };
    if (payload.error?.message) message = payload.error.message;
  } catch {
    // Keep the status-based fallback when an intermediary returns non-JSON.
  }
  throw new Error(message);
}

function csrfToken() {
  return window.sessionStorage.getItem(CSRF_STORAGE_KEY) ?? cookieValue(CSRF_COOKIE);
}

function rememberCsrf(token: string | null) {
  if (token) window.sessionStorage.setItem(CSRF_STORAGE_KEY, token);
  else window.sessionStorage.removeItem(CSRF_STORAGE_KEY);
}

function cookieValue(name: string) {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function mockAccounts(): MockAccount[] {
  const builtIn: MockAccount[] = [
    {
      schema_version: "1.0",
      user_id: "demo-student",
      username: "student",
      role: "student",
      created_at: "2026-07-01T00:00:00Z",
      passwordHash: "demo:study1234",
    },
    {
      schema_version: "1.0",
      user_id: "demo-admin",
      username: "admin",
      role: "admin",
      created_at: "2026-07-01T00:00:00Z",
      passwordHash: "demo:admin1234",
    },
  ];
  try {
    const saved = JSON.parse(window.localStorage.getItem(MOCK_ACCOUNTS_KEY) ?? "[]") as MockAccount[];
    return [...builtIn, ...saved];
  } catch {
    return builtIn;
  }
}

function saveMockAccounts(accounts: MockAccount[]) {
  const custom = accounts.filter((account) => !account.user_id.startsWith("demo-"));
  window.localStorage.setItem(MOCK_ACCOUNTS_KEY, JSON.stringify(custom));
}

function mockPreference(userId: string): MePreferenceResponse {
  try {
    const saved = JSON.parse(window.localStorage.getItem(MOCK_PREFERENCES_KEY) ?? "{}") as Record<string, MePreferenceResponse>;
    return saved[userId] ?? defaultPreferenceResponse();
  } catch {
    return defaultPreferenceResponse();
  }
}

function saveMockPreference(userId: string, preference: MePreferenceResponse) {
  let saved: Record<string, MePreferenceResponse> = {};
  try {
    saved = JSON.parse(window.localStorage.getItem(MOCK_PREFERENCES_KEY) ?? "{}") as Record<string, MePreferenceResponse>;
  } catch {
    saved = {};
  }
  saved[userId] = preference;
  window.localStorage.setItem(MOCK_PREFERENCES_KEY, JSON.stringify(saved));
}

async function mockPasswordHash(password: string) {
  if (password === "study1234" || password === "admin1234") return `demo:${password}`;
  if (window.crypto?.subtle) {
    const bytes = new TextEncoder().encode(`study-space-mock:${password}`);
    const digest = await window.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
  }
  return `mock:${password.length}:${Array.from(password).reduce((sum, char) => sum + char.charCodeAt(0), 0)}`;
}

function mockSession(account: MockAccount): AuthSessionResponse {
  const { passwordHash: _passwordHash, ...user } = account;
  return {
    schema_version: "1.0",
    user,
    csrf_token: "mock-csrf",
    expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
  };
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export { mockRooms };
