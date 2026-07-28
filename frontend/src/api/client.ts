import { buildDashboardData, buildMockRecommendation, mockLiveSensorSnapshot, mockRooms } from "../mocks/mockData";
import type {
  AuthCredentials,
  AuthSessionResponse,
  AuthenticatedRecommendationRequest,
  DashboardData,
  DeleteResult,
  LiveSensorSnapshotResponse,
  MePreferenceResponse,
  MePreferenceUpdate,
  RecommendationRequest,
  RoomSelectionAccepted,
  RoomSelectionHistoryResponse,
  RoomSelectionRequest,
  RoomStatus,
  StudyAdvisorRequest,
  StudyAdvisorResponse,
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
const MOCK_ADMIN_SESSION_KEY = "pssa-local-admin-session";
const MOCK_ACCOUNTS_KEY = "pssa-mock-accounts";
const MOCK_PREFERENCES_KEY = "pssa-mock-preferences";
const WEATHER_CACHE_KEY = "pssa-weather-cache-v1";
const WEATHER_CACHE_MAX_AGE_MS = 6 * 60 * 60 * 1000;

type MockAccount = UserResponse & { passwordHash: string };
type ApiUserResponse = Omit<UserResponse, "role"> & { role?: UserResponse["role"] };
type ApiAuthSessionResponse = Omit<AuthSessionResponse, "user"> & { user: ApiUserResponse };

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
  const localAdminId = window.localStorage.getItem(MOCK_ADMIN_SESSION_KEY);
  if (localAdminId) {
    return mockAccounts().find((account) => account.user_id === localAdminId && account.role === "admin") ?? null;
  }
  if (!isRealApi) {
    const userId = window.localStorage.getItem(MOCK_SESSION_KEY);
    return mockAccounts().find((account) => account.user_id === userId) ?? null;
  }
  try {
    return normalizeUser(await getJson<ApiUserResponse>("/api/v1/me"));
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
    if (credentials.password.length < 10) throw new Error("密码至少需要 10 个字符。");
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
  const payload = await postJson<AuthCredentials, ApiAuthSessionResponse>(
    "/api/v1/auth/register",
    { schema_version: "1.0", ...credentials },
    { csrf: false },
  );
  const result = normalizeSession(payload);
  rememberCsrf(result.csrf_token);
  return result;
}

export async function loginAdministratorDemo(
  credentials: Omit<AuthCredentials, "schema_version">,
): Promise<AuthSessionResponse> {
  const account = mockAccounts().find(
    (item) => item.role === "admin" && item.username === credentials.username.trim().toLowerCase(),
  );
  if (!account || account.passwordHash !== (await mockPasswordHash(credentials.password))) {
    throw new Error("用户名或密码不正确。");
  }
  window.localStorage.setItem(MOCK_ADMIN_SESSION_KEY, account.user_id);
  return mockSession(account);
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
  const payload = await postJson<AuthCredentials, ApiAuthSessionResponse>(
    "/api/v1/auth/login",
    { schema_version: "1.0", ...credentials },
    { csrf: false },
  );
  const result = normalizeSession(payload);
  rememberCsrf(result.csrf_token);
  return result;
}

export async function logout() {
  const localAdmin = window.localStorage.getItem(MOCK_ADMIN_SESSION_KEY);
  window.localStorage.removeItem(MOCK_ADMIN_SESSION_KEY);
  if (localAdmin) return;
  if (!isRealApi) {
    window.localStorage.removeItem(MOCK_SESSION_KEY);
    return;
  }
  await postJson<Record<string, never>, unknown>("/api/v1/auth/logout", {});
  rememberCsrf(null);
}

export async function deleteMe() {
  if (window.localStorage.getItem(MOCK_ADMIN_SESSION_KEY)) {
    window.localStorage.removeItem(MOCK_ADMIN_SESSION_KEY);
    return null;
  }
  if (!isRealApi) {
    window.localStorage.removeItem(MOCK_SESSION_KEY);
    return null;
  }
  const response = await deleteJson<DeleteResult>("/api/v1/me");
  rememberCsrf(null);
  return response;
}

export async function loadMyPreferences(user: UserResponse): Promise<MePreferenceResponse> {
  if (user.role === "admin") return defaultPreferenceResponse();
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

export async function resetLearnedPreferences() {
  if (!isRealApi) return null;
  return postJson<Record<string, never>, MePreferenceResponse>(
    "/api/v1/me/preferences/reset-learned",
    {},
  );
}

export async function recordRoomSelection(
  roomId: string,
  recommendationRequestId: string | null,
  source: RoomSelectionRequest["source"],
  selectionIdValue = createSelectionId(),
) {
  if (!isRealApi) return null;
  const body: RoomSelectionRequest = {
    schema_version: "1.0",
    selection_id: selectionIdValue,
    room_id: roomId,
    recommendation_request_id: recommendationRequestId,
    source,
  };
  return postJson<RoomSelectionRequest, RoomSelectionAccepted>(
    "/api/v1/me/room-selections",
    body,
  );
}

export async function listRoomSelections(limit = 6) {
  if (!isRealApi) return null;
  return getJson<RoomSelectionHistoryResponse>(`/api/v1/me/room-selections?limit=${limit}`);
}

export async function deleteRoomSelections() {
  if (!isRealApi) return null;
  return deleteJson<DeleteResult>("/api/v1/me/room-selections");
}

export async function loadDashboardData(user: UserResponse, request: RecommendationRequest): Promise<DashboardData> {
  if (user.role === "admin" && isRealApi) {
    const roomsResponse = await getJson<{ rooms: RoomStatus[] }>("/api/v1/rooms/status");
    const candidateRoomIds = roomsResponse.rooms.map((room) => room.room_id);
    const adminRequest = {
      ...request,
      profile_id: "local-admin-demo",
      candidate_room_ids: candidateRoomIds,
    };
    let recommendations: DashboardData["recommendations"];
    try {
      recommendations = await postJson<RecommendationRequest, DashboardData["recommendations"]>(
        "/api/v1/recommendations",
        adminRequest,
        { csrf: false },
      );
    } catch {
      recommendations = buildMockRecommendation(adminRequest, roomsResponse.rooms);
    }
    return {
      rooms: roomsResponse.rooms,
      recommendations,
      histories: {},
      thermalPreviews: {},
      backendStatus: "ok",
      lastUpdated: new Date().toISOString(),
      user,
      preferences: defaultPreferenceResponse(adminRequest),
      authenticated: true,
    };
  }
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
  const [recommendations, preferences, selectionHistory] = await Promise.all([
    postJson<AuthenticatedRecommendationRequest, DashboardData["recommendations"]>("/api/v1/me/recommendations", body),
    loadMyPreferences(user),
    listRoomSelections(6),
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
    selectionHistory,
    authenticated: true,
  };
}

export async function requestStudyAdvice(
  user: UserResponse,
  studyGoal: string,
  candidateRoomIds: string[],
): Promise<StudyAdvisorResponse> {
  if (!isRealApi) {
    await delay(220);
    const preferences = mockPreference(user.user_id);
    const interpreted = interpretMockStudyGoal(studyGoal, preferences.effective.study_mode);
    const request = requestFromPreferences(
      preferences,
      candidateRoomIds,
      user.user_id,
    );
    request.study_mode = interpreted.mode;
    const recommendations = buildMockRecommendation(request);
    const focus = recommendations.recommendations[0] ?? null;
    return {
      schema_version: "1.0",
      request_id: "mock-advisor-request",
      generated_at: new Date().toISOString(),
      interpreted_study_mode: interpreted.mode,
      interpreted_needs: interpreted.needs,
      applied_preferences: request.preferences,
      focus_room_id: focus?.room_id ?? null,
      advisor_message: focus?.explanation ?? "No room has enough current evidence for a recommendation.",
      advice_source: "template",
      recommendations: recommendations.recommendations,
      warnings: ["LLM_DISABLED", "STUDY_GOAL_NOT_STORED"],
    };
  }
  const body: StudyAdvisorRequest = {
    schema_version: "1.0",
    study_goal: studyGoal,
    candidate_room_ids: candidateRoomIds,
  };
  return postJson<StudyAdvisorRequest, StudyAdvisorResponse>(
    "/api/v1/me/study-advisor",
    body,
  );
}

export async function loadRoomStatuses(): Promise<RoomStatus[]> {
  if (!isRealApi) {
    await delay(80);
    return mockRooms;
  }
  const response = await getJson<{ rooms: RoomStatus[] }>("/api/v1/rooms/status");
  return response.rooms;
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

function interpretMockStudyGoal(
  studyGoal: string,
  savedMode: RecommendationRequest["study_mode"],
): {
  mode: RecommendationRequest["study_mode"];
  needs: StudyAdvisorResponse["interpreted_needs"];
} {
  const normalized = studyGoal.toLowerCase();
  const discussion = ["discuss", "discussion", "group", "meeting", "presentation", "讨论", "小组", "汇报", "合作"].some((term) => normalized.includes(term));
  const quiet = ["quiet", "focus", "exam", "revision", "read", "coding", "安静", "专注", "复习", "考试", "阅读", "编程"].some((term) => normalized.includes(term));
  const needs: StudyAdvisorResponse["interpreted_needs"] = [];
  if (quiet) needs.push("quiet");
  if (discussion) needs.push("discussion");
  if (["empty", "seat", "less crowded", "人少", "空位", "不拥挤"].some((term) => normalized.includes(term))) needs.push("low_occupancy");
  if (["bright", "lighting", "明亮", "光线"].some((term) => normalized.includes(term))) needs.push("bright");
  if (["comfortable", "temperature", "humidity", "舒适", "温度", "湿度"].some((term) => normalized.includes(term))) needs.push("comfortable");
  if (!needs.length) needs.push("saved_preferences");
  return {
    mode: discussion && !quiet ? "discussion" : quiet && !discussion ? "quiet" : savedMode,
    needs,
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

async function deleteJson<Result>(path: string) {
  const token = csrfToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    credentials: "include",
    headers: token ? { "X-CSRF-Token": token } : {},
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

function normalizeUser(user: ApiUserResponse): UserResponse {
  return { ...user, role: user.role ?? "student" };
}

function normalizeSession(session: ApiAuthSessionResponse): AuthSessionResponse {
  return { ...session, user: normalizeUser(session.user) };
}

function cookieValue(name: string) {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

export function createSelectionId() {
  if ("randomUUID" in crypto) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (char) =>
    (Number(char) ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(char) / 4)))).toString(16),
  );
}

function mockAccounts(): MockAccount[] {
  const builtIn: MockAccount[] = [
    {
      schema_version: "1.0",
      user_id: "demo-student",
      username: "student",
      role: "student",
      created_at: "2026-07-01T00:00:00Z",
      passwordHash: "demo:study12345",
    },
    {
      schema_version: "1.0",
      user_id: "demo-admin",
      username: "admin",
      role: "admin",
      created_at: "2026-07-01T00:00:00Z",
      passwordHash: "demo:admin12345",
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
  if (password === "study12345" || password === "admin12345") return `demo:${password}`;
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
