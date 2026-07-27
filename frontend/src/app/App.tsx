import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowLeft,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Clock3,
  CloudSun,
  Cpu,
  Database,
  DoorOpen,
  Droplets,
  ExternalLink,
  Gauge,
  Home,
  Languages,
  Lightbulb,
  LogIn,
  LogOut,
  MapPin,
  Menu,
  Radio,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  ScanLine,
  SlidersHorizontal,
  Thermometer,
  UserCircle,
  Users,
  Volume2,
  Wifi,
  X,
} from "lucide-react";
import {
  createSelectionId,
  deleteMe,
  deleteRoomSelections,
  defaultRequest,
  isRealApi,
  loadDashboardData,
  loadLiveSensorSnapshot,
  loadMyPreferences,
  loadWeather,
  login,
  logout,
  recordRoomSelection,
  register,
  resetLearnedPreferences,
  restoreSession,
  saveMyPreferences,
} from "../api/client";
import { catalogFor } from "../data/roomCatalog";
import { LanguageProvider, localizeKnownMessage, selectText, useLanguage, type Language } from "../i18n";
import type {
  DashboardData,
  LiveSensorSnapshotResponse,
  MePreferenceResponse,
  OccupancyLevel,
  RecommendationItem,
  RecommendationRequest,
  RoomState,
  RoomStatus,
  StudyMode,
  UserResponse,
  WeatherInfo,
} from "../types/contracts";

type StudentPage = "home" | "rooms" | "preferences" | "account";
type AdminPage = "overview" | "monitor" | "rooms" | "system";
type AuthRole = "student" | "admin";
type FailedSelection = {
  selectionId: string;
  roomId: string;
  roomName: string;
  recommendationRequestId: string | null;
  source: "recommendation" | "room_detail";
};

const roomStateText: Record<RoomState, Record<Language, string>> = {
  empty_or_low_activity: { zh: "安静空闲", en: "Quiet and available" },
  quiet_study_recommended: { zh: "适合专注学习", en: "Recommended for quiet study" },
  discussion_allowed: { zh: "适合小组讨论", en: "Suitable for group discussion" },
  not_recommended_noisy_or_crowded: { zh: "当前较拥挤", en: "Currently crowded" },
  unknown: { zh: "状态待确认", en: "Status pending" },
};

const occupancyText: Record<OccupancyLevel, Record<Language, string>> = {
  empty: { zh: "空间很宽松", en: "Plenty of space" },
  low: { zh: "空位较充足", en: "Good seat availability" },
  medium: { zh: "使用人数适中", en: "Moderately occupied" },
  high: { zh: "目前较拥挤", en: "Currently crowded" },
  unknown: { zh: "占用情况待确认", en: "Occupancy pending" },
};

const quotes = [
  { zh: "把注意力留给此刻，进度会在安静中发生。", en: "Give this moment your attention; progress often begins in quiet." },
  { zh: "先找到适合自己的空间，再开始今天的专注。", en: "Find the space that suits you, then settle into focused work." },
  { zh: "慢一点没关系，稳定前进就很好。", en: "There is no harm in moving slowly when you are moving steadily." },
  { zh: "一次只做好一件事，也是一种很强的节奏。", en: "Doing one thing well at a time is a powerful rhythm." },
  { zh: "给今天留一点安静，也给自己留一点余地。", en: "Leave a little quiet in your day and a little room for yourself." },
  { zh: "清晰的环境，会让思路更容易抵达。", en: "A clear environment makes clear thinking easier to reach." },
  { zh: "今天的每一小步，都在靠近更完整的答案。", en: "Every small step today brings the answer closer." },
];

export function App() {
  return (
    <LanguageProvider>
      <AppContent />
    </LanguageProvider>
  );
}

function AppContent() {
  const { language, choose } = useLanguage();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [request, setRequest] = useState<RecommendationRequest>(defaultRequest);
  const [data, setData] = useState<DashboardData | null>(null);
  const [weather, setWeather] = useState<WeatherInfo | null>(null);
  const [weatherError, setWeatherError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);
  const [outbox, setOutbox] = useState<FailedSelection[]>([]);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        const restored = await restoreSession();
        if (!active || !restored) return;
        const preferences = await loadMyPreferences(restored);
        const nextRequest = requestFromPreferences(preferences, restored.user_id);
        const dashboard = await loadDashboardData(restored, nextRequest);
        if (!active) return;
        setUser(restored);
        setRequest(nextRequest);
        setData(dashboard);
      } catch (err) {
        if (active) setError(messageFrom(err, choose("应用暂时无法加载。", "The application is temporarily unavailable."), language));
      } finally {
        if (active) setLoading(false);
      }
    }
    void bootstrap();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!user || user.role !== "student") return;
    let active = true;
    loadWeather()
      .then((result) => {
        if (active) {
          setWeather(result);
          setWeatherError(false);
        }
      })
      .catch(() => {
        if (active) setWeatherError(true);
      });
    return () => {
      active = false;
    };
  }, [user]);

  async function authenticate(role: AuthRole, mode: "login" | "register", username: string, password: string) {
    setError(null);
    const result = mode === "register" ? await register({ username, password }) : await login({ username, password });
    if (result.user.role !== role) {
      await logout();
      throw new Error(
        role === "admin"
          ? choose("该账户不是管理员账户。", "This account does not have administrator access.")
          : choose("请从管理员入口登录该账户。", "Please sign in to this account through the administrator portal."),
      );
    }
    const preferences = await loadMyPreferences(result.user);
    const nextRequest = requestFromPreferences(preferences, result.user.user_id);
    const dashboard = await loadDashboardData(result.user, nextRequest);
    setUser(result.user);
    setRequest(nextRequest);
    setData(dashboard);
  }

  async function signOut() {
    await logout();
    setUser(null);
    setData(null);
    setWeather(null);
    setRequest(defaultRequest);
    setSelectionMessage(null);
    setOutbox([]);
  }

  async function refresh(nextRequest = request) {
    if (!user) return;
    setRefreshing(true);
    setError(null);
    try {
      setData(await loadDashboardData(user, nextRequest));
    } catch (err) {
      setError(messageFrom(err, choose("最新状态暂时无法获取。", "The latest room status is temporarily unavailable."), language));
    } finally {
      setRefreshing(false);
    }
  }

  async function updatePreferences(nextRequest: RecommendationRequest) {
    if (!user) return;
    setRefreshing(true);
    setError(null);
    try {
      await saveMyPreferences(user, nextRequest, data?.preferences?.learning_enabled ?? true);
      const dashboard = await loadDashboardData(user, nextRequest);
      setRequest(nextRequest);
      setData(dashboard);
    } catch (err) {
      setError(messageFrom(err, choose("偏好设置保存失败。", "Your preferences could not be saved."), language));
      throw err;
    } finally {
      setRefreshing(false);
    }
  }

  async function toggleLearning(enabled: boolean) {
    if (!user) return;
    setRefreshing(true);
    setError(null);
    try {
      await saveMyPreferences(user, request, enabled);
      setData(await loadDashboardData(user, request));
    } catch (err) {
      setError(messageFrom(err, choose("偏好学习设置保存失败。", "The learning setting could not be saved."), language));
    } finally {
      setRefreshing(false);
    }
  }

  async function resetLearned() {
    if (!user) return;
    setRefreshing(true);
    setError(null);
    try {
      await resetLearnedPreferences();
      setData(await loadDashboardData(user, request));
    } catch (err) {
      setError(messageFrom(err, choose("学习偏好重置失败。", "Learned preferences could not be reset."), language));
    } finally {
      setRefreshing(false);
    }
  }

  async function clearSelections() {
    if (!user) return;
    setRefreshing(true);
    setError(null);
    try {
      await deleteRoomSelections();
      setData(await loadDashboardData(user, request));
    } catch (err) {
      setError(messageFrom(err, choose("选择历史删除失败。", "Room selection history could not be deleted."), language));
    } finally {
      setRefreshing(false);
    }
  }

  async function deleteAccount() {
    if (!window.confirm(choose("删除本地账户和全部学习记录？", "Delete this local account and all learning data?"))) return;
    try {
      await deleteMe();
      setUser(null);
      setData(null);
      setWeather(null);
      setOutbox([]);
    } catch (err) {
      setError(messageFrom(err, choose("账户删除失败。", "The account could not be deleted."), language));
    }
  }

  async function chooseRoom(
    roomId: string,
    roomName: string,
    recommendationRequestId: string | null,
    source: FailedSelection["source"],
    selectionId = createSelectionId(),
  ) {
    if (!user) return;
    setSelectionMessage(null);
    try {
      await recordRoomSelection(roomId, recommendationRequestId, source, selectionId);
      setOutbox((items) => items.filter((item) => item.selectionId !== selectionId));
      setSelectionMessage(choose("选择已记录，将用于改善推荐。", "Choice recorded and available for preference learning."));
      setData(await loadDashboardData(user, request));
    } catch (err) {
      setOutbox((items) => [
        ...items.filter((item) => item.selectionId !== selectionId),
        { selectionId, roomId, roomName, recommendationRequestId, source },
      ]);
      setSelectionMessage(messageFrom(err, choose("记录失败，已加入本地重试队列。", "Recording failed and was added to the local retry queue."), language));
    }
  }

  if (loading) return <AppLoading />;
  if (!user) return <AuthPortal onAuthenticate={authenticate} />;
  if (!data) {
    return (
      <main className="fatal-state">
        <AlertTriangle aria-hidden="true" />
        <h1>{choose("暂时无法进入系统", "Unable to open the application")}</h1>
        <p>{error ?? choose("请重新登录后再试。", "Please sign in again and retry.")}</p>
        <button type="button" className="primary-button" onClick={() => void signOut()}>
          {choose("返回登录", "Return to sign in")}
        </button>
      </main>
    );
  }

  return user.role === "admin" ? (
    <AdminApp user={user} data={data} error={error} refreshing={refreshing} onRefresh={() => void refresh()} onSignOut={() => void signOut()} />
  ) : (
    <StudentApp
      user={user}
      data={data}
      request={request}
      weather={weather}
      weatherError={weatherError}
      error={error}
      refreshing={refreshing}
      onRefresh={() => void refresh()}
      onSavePreferences={updatePreferences}
      onChooseRoom={chooseRoom}
      selectionMessage={selectionMessage}
      outbox={outbox}
      onRetrySelection={(item) => chooseRoom(item.roomId, item.roomName, item.recommendationRequestId, item.source, item.selectionId)}
      onLearningToggle={toggleLearning}
      onResetLearned={resetLearned}
      onDeleteSelections={clearSelections}
      onDeleteAccount={deleteAccount}
      onSignOut={() => void signOut()}
    />
  );
}

function AuthPortal({
  onAuthenticate,
}: {
  onAuthenticate: (role: AuthRole, mode: "login" | "register", username: string, password: string) => Promise<void>;
}) {
  const { language, choose } = useLanguage();
  const [role, setRole] = useState<AuthRole>("student");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function switchRole(nextRole: AuthRole) {
    setRole(nextRole);
    setMode("login");
    setMessage(null);
    setUsername("");
    setPassword("");
  }

  function fillDemo() {
    setUsername(role === "admin" ? "admin" : "student");
    setPassword(role === "admin" ? "admin1234" : "study1234");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await onAuthenticate(role, mode, username.trim(), password);
    } catch (err) {
      setMessage(messageFrom(err, choose("登录失败，请重试。", "Sign-in failed. Please try again."), language));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-topbar">
        <Brand />
        <div className="auth-top-actions">
          <span className="privacy-mini">
            <ShieldCheck size={16} aria-hidden="true" />
            {choose("隐私保护学习空间", "Privacy-preserving study spaces")}
          </span>
          <LanguageToggle />
        </div>
      </header>
      <section className="auth-stage">
        <div className="auth-intro">
          <p className="overline">STUDY SPACE ADVISOR</p>
          <h1>{choose("找到更适合你的学习空间", "Find a study space that works for you")}</h1>
          <p>{choose(
            "根据房间状态和你的偏好提供简单、清晰的建议。无需摄像头，也不记录原始语音。",
            "Get clear recommendations based on room conditions and your preferences, without cameras or stored audio.",
          )}</p>
          <div className="auth-trust">
            <span><ShieldCheck size={18} />{choose("无身份识别", "No identity recognition")}</span>
            <span><Wifi size={18} />{choose("实时空间状态", "Live room status")}</span>
          </div>
        </div>
        <section className="auth-panel" aria-label={choose("账户登录", "Account sign in")}>
          <div className="auth-role-switch" aria-label={choose("账户类型", "Account type")}>
            <button type="button" className={role === "student" ? "active" : ""} onClick={() => switchRole("student")}>
              {choose("普通用户", "Student")}
            </button>
            {!isRealApi ? (
              <button type="button" className={role === "admin" ? "active" : ""} onClick={() => switchRole("admin")}>
                {choose("管理员", "Administrator")}
              </button>
            ) : null}
          </div>
          <div className="auth-heading">
            <div className="auth-icon">{role === "admin" ? <Settings /> : <UserCircle />}</div>
            <div>
              <h2>{mode === "register"
                ? choose("创建账户", "Create an account")
                : role === "admin"
                  ? choose("管理员登录", "Administrator sign in")
                  : choose("欢迎回来", "Welcome back")}</h2>
              <p>{mode === "register"
                ? choose("创建你的个人偏好档案", "Create your personal study preference profile")
                : choose("登录后继续查看推荐", "Sign in to view your recommendations")}</p>
            </div>
          </div>
          <form onSubmit={(event) => void submit(event)}>
            <label>
              {choose("用户名", "Username")}
              <input
                value={username}
                onChange={(event) => setUsername(event.currentTarget.value)}
                autoComplete="username"
                minLength={3}
                placeholder={choose("请输入用户名", "Enter your username")}
                required
              />
            </label>
            <label>
              {choose("密码", "Password")}
              <input
                value={password}
                onChange={(event) => setPassword(event.currentTarget.value)}
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                minLength={10}
                placeholder={choose("至少 10 个字符", "At least 10 characters")}
                type="password"
                required
              />
            </label>
            {message ? <p className="form-message error" role="alert">{message}</p> : null}
            <button type="submit" className="primary-button auth-submit" disabled={busy}>
              {busy ? <RefreshCw className="spin" size={18} /> : <LogIn size={18} />}
              {mode === "register" ? choose("创建并登录", "Create account and sign in") : choose("登录", "Sign in")}
            </button>
          </form>
          {role === "student" ? (
            <button type="button" className="text-button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login"
                ? choose("还没有账户？创建用户", "New here? Create an account")
                : choose("已有账户？返回登录", "Already have an account? Sign in")}
            </button>
          ) : null}
          {!isRealApi ? (
            <button type="button" className="demo-fill" onClick={fillDemo}>
              {role === "admin"
                ? choose("填入管理员演示账户", "Use administrator demo account")
                : choose("填入学生演示账户", "Use student demo account")}
            </button>
          ) : null}
        </section>
      </section>
    </main>
  );
}

function StudentApp({
  user,
  data,
  request,
  weather,
  weatherError,
  error,
  refreshing,
  onRefresh,
  onSavePreferences,
  onChooseRoom,
  selectionMessage,
  outbox,
  onRetrySelection,
  onLearningToggle,
  onResetLearned,
  onDeleteSelections,
  onDeleteAccount,
  onSignOut,
}: {
  user: UserResponse;
  data: DashboardData;
  request: RecommendationRequest;
  weather: WeatherInfo | null;
  weatherError: boolean;
  error: string | null;
  refreshing: boolean;
  onRefresh: () => void;
  onSavePreferences: (request: RecommendationRequest) => Promise<void>;
  onChooseRoom: (
    roomId: string,
    roomName: string,
    recommendationRequestId: string | null,
    source: FailedSelection["source"],
  ) => Promise<void>;
  selectionMessage: string | null;
  outbox: FailedSelection[];
  onRetrySelection: (item: FailedSelection) => Promise<void>;
  onLearningToggle: (enabled: boolean) => Promise<void>;
  onResetLearned: () => Promise<void>;
  onDeleteSelections: () => Promise<void>;
  onDeleteAccount: () => Promise<void>;
  onSignOut: () => void;
}) {
  const { choose } = useLanguage();
  const [page, setPage] = useState<StudentPage>("home");
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [mobileMenu, setMobileMenu] = useState(false);

  function navigate(nextPage: StudentPage) {
    setPage(nextPage);
    setMobileMenu(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openRoom(roomId: string) {
    setSelectedRoomId(roomId);
    navigate("rooms");
  }

  function selectRoom(roomId: string) {
    setSelectedRoomId(roomId);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  return (
    <div className="product-shell">
      <header className="product-header">
        <Brand />
        <nav className="desktop-nav" aria-label={choose("主要菜单", "Primary navigation")}>
          <StudentNav page={page} onNavigate={navigate} />
        </nav>
        <div className="header-actions">
          <LanguageToggle />
          <button
            type="button"
            className="icon-button"
            aria-label={choose("刷新数据", "Refresh data")}
            title={choose("刷新数据", "Refresh data")}
            onClick={onRefresh}
            disabled={refreshing}
          >
            <RefreshCw className={refreshing ? "spin" : ""} size={18} />
          </button>
          <button type="button" className="account-chip" onClick={() => navigate("account")}>
            <UserCircle size={18} />
            {user.username}
          </button>
          <button type="button" className="icon-button mobile-menu-button" aria-label={choose("打开菜单", "Open menu")} onClick={() => setMobileMenu((value) => !value)}>
            {mobileMenu ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </header>
      {mobileMenu ? (
        <nav className="mobile-menu" aria-label={choose("移动端菜单", "Mobile navigation")}>
          <StudentNav page={page} onNavigate={navigate} />
        </nav>
      ) : null}
      {error ? <StatusBanner text={error} /> : null}
      <main className="page-content">
        {selectionMessage ? <StatusBanner text={selectionMessage} /> : null}
        {page === "home" ? (
          <HomeView
            user={user}
            data={data}
            weather={weather}
            weatherError={weatherError}
            onOpenRoom={openRoom}
            onChooseRoom={onChooseRoom}
          />
        ) : null}
        {page === "rooms" ? (
          <RoomsView
            data={data}
            selectedRoomId={selectedRoomId}
            onSelectRoom={selectRoom}
            onChooseRoom={onChooseRoom}
          />
        ) : null}
        {page === "preferences" ? <PreferencesView request={request} busy={refreshing} onSave={onSavePreferences} /> : null}
        {page === "account" ? (
          <AccountView
            user={user}
            preferences={data.preferences ?? null}
            history={data.selectionHistory ?? null}
            outbox={outbox}
            busy={refreshing}
            onRetrySelection={onRetrySelection}
            onLearningToggle={onLearningToggle}
            onResetLearned={onResetLearned}
            onDeleteSelections={onDeleteSelections}
            onDeleteAccount={onDeleteAccount}
            onSignOut={onSignOut}
          />
        ) : null}
      </main>
      <nav className="mobile-bottom-nav" aria-label={choose("底部导航", "Bottom navigation")}>
        <StudentNav page={page} onNavigate={navigate} compact />
      </nav>
    </div>
  );
}

function StudentNav({
  page,
  onNavigate,
  compact = false,
}: {
  page: StudentPage;
  onNavigate: (page: StudentPage) => void;
  compact?: boolean;
}) {
  const { choose } = useLanguage();
  const items: Array<{ id: StudentPage; label: string; icon: ReactNode }> = [
    { id: "home", label: choose("首页", "Home"), icon: <Home size={18} /> },
    { id: "rooms", label: choose("教室", "Rooms"), icon: <DoorOpen size={18} /> },
    { id: "preferences", label: choose("偏好", "Preferences"), icon: <SlidersHorizontal size={18} /> },
    { id: "account", label: choose("账户", "Account"), icon: <UserCircle size={18} /> },
  ];
  return (
    <>
      {items.map((item) => (
        <button key={item.id} type="button" className={page === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}>
          {item.icon}
          <span>{item.label}</span>
          {!compact && page === item.id ? <span className="nav-dot" aria-hidden="true" /> : null}
        </button>
      ))}
    </>
  );
}

function HomeView({
  user,
  data,
  weather,
  weatherError,
  onOpenRoom,
  onChooseRoom,
}: {
  user: UserResponse;
  data: DashboardData;
  weather: WeatherInfo | null;
  weatherError: boolean;
  onOpenRoom: (roomId: string) => void;
  onChooseRoom: (
    roomId: string,
    roomName: string,
    recommendationRequestId: string | null,
    source: FailedSelection["source"],
  ) => Promise<void>;
}) {
  const { language, locale, choose } = useLanguage();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const dateText = new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric" }).format(now);
  const weekdayText = new Intl.DateTimeFormat(locale, { weekday: "long" }).format(now);
  const recommendations = data.recommendations.recommendations.slice(0, 3);

  return (
    <>
      <section className="welcome-hero" aria-labelledby="welcome-title">
        <div className="welcome-copy">
          <p className="hero-kicker">TODAY ON CAMPUS</p>
          <h1 id="welcome-title">{greeting(now, language)}{language === "zh" ? "，" : ", "}{user.username}</h1>
          <p className="welcome-lead">{choose("先找到合适的空间，再开始今天的专注。", "Find the right space, then give your work your full attention.")}</p>
          <blockquote>{dailyQuote(now, language)}</blockquote>
        </div>
        <div className="clock-block" aria-label={choose("当前时间", "Current time")}>
          <strong>{new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(now)}</strong>
          <span>{choose("本地时间", "Local time")}</span>
        </div>
      </section>

      <section className="today-facts" aria-label={choose("今日信息", "Today's information")}>
        <InfoTile icon={<CalendarDays />} label={choose("日期", "Date")} value={dateText} detail={weekdayText} />
        <InfoTile
          icon={<CloudSun />}
          label={choose("天气", "Weather")}
          value={weather
            ? `${Math.round(weather.temperatureC)}°C · ${weatherDescription(weather.weatherCode, language)}`
            : weatherError
              ? choose("暂时无法获取", "Temporarily unavailable")
              : choose("正在获取", "Loading")}
          detail={weather
            ? `${weather.locationLabel} · ${choose("体感", "Feels like")} ${Math.round(weather.apparentTemperatureC)}°C · ${choose("湿度", "Humidity")} ${weather.humidityPercent}%${weather.isCached ? choose(" · 最近更新", " · Last available") : ""}`
            : choose("实时天气由新加坡国家环境局提供", "Live weather data from Singapore's NEA")}
        />
        <InfoTile
          icon={<ShieldCheck />}
          label={choose("隐私", "Privacy")}
          value={choose("只分析空间，不识别个人", "Room-level analysis only; no identity recognition")}
          detail={choose("无 RGB 摄像头，不保存原始语音", "No RGB cameras and no stored raw audio")}
        />
      </section>

      <section className="home-recommendations" aria-labelledby="recommendation-heading">
        <div className="section-heading">
          <div>
            <p className="overline">BASED ON YOUR PREFERENCES</p>
            <h2 id="recommendation-heading">{choose("为你推荐", "Recommended for you")}</h2>
          </div>
          <span className="section-note">{choose("已结合你的学习偏好", "Personalised using your study preferences")}</span>
        </div>
        {recommendations.length ? (
          <div className="recommendation-list">
            {recommendations.map((item, index) => {
              const room = data.rooms.find((entry) => entry.room_id === item.room_id);
              return room ? (
                <RecommendationCard
                  key={item.room_id}
                  room={room}
                  item={item}
                  featured={index === 0}
                  onOpen={() => onOpenRoom(room.room_id)}
                  onChoose={() => onChooseRoom(room.room_id, room.name, data.recommendations.request_id, "recommendation")}
                />
              ) : null;
            })}
          </div>
        ) : (
          <EmptyPanel
            title={choose("暂时没有可推荐的教室", "No room recommendations yet")}
            detail={choose("新的空间状态到达后，推荐会自动更新。", "Recommendations will update when new room data arrives.")}
          />
        )}
      </section>
    </>
  );
}

function InfoTile({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return (
    <article className="info-tile">
      <div className="tile-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

function RecommendationCard({
  room,
  item,
  featured,
  onOpen,
  onChoose,
}: {
  room: RoomStatus;
  item: RecommendationItem;
  featured: boolean;
  onOpen: () => void;
  onChoose: () => Promise<void>;
}) {
  const { language, choose } = useLanguage();
  const catalog = catalogFor(room, language);
  return (
    <article className={`recommendation-card ${featured ? "featured" : ""}`}>
      <div className="recommendation-rank">
        {featured ? choose("首选", "Top choice") : `${choose("备选", "Alternative")} ${item.rank}`}
      </div>
      <div className="recommendation-main">
        <div>
          <span className={`state-dot ${stateTone(room.room_state)}`}>{roomStateText[room.room_state][language]}</span>
          <h3>{catalog.displayName}</h3>
          <p>{catalog.shortLocation}</p>
        </div>
        <span className={`fit-label ${fitTone(item.score)}`}>{qualitativeFit(item.score, language)}</span>
      </div>
      <div className="reason-row">
        <span>{occupancyText[room.occupancy_level][language]}</span>
        <span>{forecastText(item.forecast_30m, language)}</span>
        {item.is_stale
          ? <span>{choose("建议到场确认", "Verify on arrival")}</span>
          : <span>{choose("状态刚刚更新", "Updated just now")}</span>}
      </div>
      <div className="recommendation-actions">
        <button type="button" className="secondary-button" onClick={() => void onChoose()}>
          <CheckCircle2 size={17} />
          {choose("选择此教室", "Choose this room")}
        </button>
        <button type="button" className="card-link" onClick={onOpen}>
          {choose("查看教室", "View room")}
          <ArrowRight size={17} />
        </button>
      </div>
    </article>
  );
}

function RoomsView({
  data,
  selectedRoomId,
  onSelectRoom,
  onChooseRoom,
}: {
  data: DashboardData;
  selectedRoomId: string;
  onSelectRoom: (roomId: string) => void;
  onChooseRoom: (
    roomId: string,
    roomName: string,
    recommendationRequestId: string | null,
    source: FailedSelection["source"],
  ) => Promise<void>;
}) {
  const { language, choose } = useLanguage();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "quiet" | "discussion" | "available">("all");
  const selectedRoom = data.rooms.find((room) => room.room_id === selectedRoomId) ?? null;
  const selectedRecommendation = data.recommendations.recommendations.find((item) => item.room_id === selectedRoom?.room_id);
  const filtered = data.rooms.filter((room) => {
    const catalog = catalogFor(room, language);
    const matchesQuery = `${catalog.displayName} ${catalog.shortLocation} ${catalog.address}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter =
      filter === "all" ||
      (filter === "quiet" && ["quiet_study_recommended", "empty_or_low_activity"].includes(room.room_state)) ||
      (filter === "discussion" && room.room_state === "discussion_allowed") ||
      (filter === "available" && ["empty", "low"].includes(room.occupancy_level) && !room.is_stale);
    return matchesQuery && matchesFilter;
  });

  if (selectedRoom) {
    return (
      <StudentRoomDetail
        room={selectedRoom}
        recommendation={selectedRecommendation ?? null}
        onBack={() => onSelectRoom("")}
        onChoose={() =>
          onChooseRoom(
            selectedRoom.room_id,
            selectedRoom.name,
            selectedRecommendation ? data.recommendations.request_id : null,
            selectedRecommendation ? "recommendation" : "room_detail",
          )
        }
      />
    );
  }

  return (
    <section className="rooms-page">
      <PageTitle
        eyebrow="CAMPUS SPACES"
        title={choose("发现教室", "Explore study rooms")}
        detail={choose("先浏览空间与位置，点开后再查看与你偏好的匹配情况。", "Browse spaces and locations first, then open a room to see how well it matches your preferences.")}
      />
      <div className="room-tools">
        <label className="search-field">
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder={choose("搜索教室、楼层或地址", "Search by room, level or address")}
            aria-label={choose("搜索教室", "Search rooms")}
          />
        </label>
        <div className="filter-tabs" aria-label={choose("教室筛选", "Room filters")}>
          {(["all", "available", "quiet", "discussion"] as const).map((value) => (
            <button key={value} type="button" className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>
              {value === "all"
                ? choose("全部", "All")
                : value === "available"
                  ? choose("空位充足", "Seats available")
                  : value === "quiet"
                    ? choose("安静学习", "Quiet study")
                    : choose("小组讨论", "Group discussion")}
            </button>
          ))}
        </div>
      </div>
      <div className="room-card-grid">
        {filtered.map((room) => {
          const catalog = catalogFor(room, language);
          const recommendation = data.recommendations.recommendations.find((item) => item.room_id === room.room_id) ?? null;
          return (
            <button key={room.room_id} type="button" className="room-card" onClick={() => onSelectRoom(room.room_id)}>
              <span className="room-card-media">
                <img src={catalog.image} alt={`${catalog.displayName} ${choose("教室", "room")}`} />
                <span className={`room-card-state ${stateTone(room.room_state)}`}>{roomStateText[room.room_state][language]}</span>
              </span>
              <span className="room-card-body">
                <span className="room-card-heading">
                  <strong>{catalog.displayName}</strong>
                  <ArrowRight size={18} />
                </span>
                <span className="room-card-location"><MapPin size={14} />{catalog.shortLocation}</span>
                <span className="room-card-meta">
                  <span><Clock3 size={14} />{catalog.openingHours}</span>
                  <em className={fitTone(recommendation?.score ?? 0)}>
                    {recommendation
                      ? qualitativeFit(recommendation.score, language)
                      : choose("等待匹配", "Match pending")}
                  </em>
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {!filtered.length ? (
        <EmptyPanel
          title={choose("没有找到匹配的教室", "No matching rooms found")}
          detail={choose("可以换一个关键词或筛选条件。", "Try a different search term or filter.")}
        />
      ) : null}
    </section>
  );
}

function StudentRoomDetail({
  room,
  recommendation,
  onBack,
  onChoose,
}: {
  room: RoomStatus;
  recommendation: RecommendationItem | null;
  onBack: () => void;
  onChoose: () => Promise<void>;
}) {
  const { language, choose } = useLanguage();
  const catalog = catalogFor(room, language);
  const fit = recommendation ? qualitativeFit(recommendation.score, language) : choose("可以作为备选", "Suitable as an alternative");
  return (
    <section className="student-room-detail" aria-label={`${catalog.displayName} ${choose("详情", "details")}`}>
      <button type="button" className="detail-back" onClick={onBack}>
        <ArrowLeft size={18} />
        {choose("返回全部教室", "Back to all rooms")}
      </button>
      <div className="room-detail-hero">
        <img src={catalog.image} alt={`${catalog.displayName} ${choose("教室内部", "interior")}`} />
        <div className="room-detail-overlay">
          <span className={`state-dot ${stateTone(room.room_state)}`}>{roomStateText[room.room_state][language]}</span>
          <h1>{catalog.displayName}</h1>
          <p>{catalog.shortLocation}</p>
        </div>
      </div>
      <div className="room-detail-grid">
        <div className="room-detail-main">
          <section className="room-match-panel">
            <div className="room-match-heading">
              <div><span>{choose("与你的偏好匹配度", "Match with your preferences")}</span><strong>{fit}</strong></div>
              <span className={`fit-orbit ${fitTone(recommendation?.score ?? 0)}`}><CheckCircle2 size={22} /></span>
            </div>
            <div className="match-meter" role="progressbar" aria-label={choose("个人偏好匹配度", "Preference match")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={recommendation?.score ?? 0}>
              <span style={{ width: `${recommendation?.score ?? 0}%` }} />
            </div>
            <p>{qualitativeSummary(room, recommendation, language)}</p>
          </section>
          <section className="room-current-panel">
            <SectionBar
              title={choose("当前教室状态", "Current room status")}
              detail={choose("只展示适合学生决策的定性结果", "Qualitative guidance for student decisions")}
            />
            <dl className="student-status-list">
              <div><dt>{choose("当前空间", "Current occupancy")}</dt><dd>{occupancyText[room.occupancy_level][language]}</dd></div>
              <div><dt>{choose("综合判断", "Overall assessment")}</dt><dd>{roomStateText[room.room_state][language]}</dd></div>
              <div><dt>{choose("未来半小时", "Next 30 minutes")}</dt><dd>{forecastText(recommendation?.forecast_30m ?? "unknown", language)}</dd></div>
              <div><dt>{choose("数据状态", "Data status")}</dt><dd>{room.is_stale ? choose("建议到场确认", "Verify on arrival") : choose("刚刚更新", "Updated just now")}</dd></div>
            </dl>
          </section>
          <section className="room-amenities">
            <h2>{choose("空间设施", "Amenities")}</h2>
            <div>{catalog.amenities.map((amenity) => <span key={amenity}>{amenity}</span>)}</div>
          </section>
        </div>
        <aside className="room-facts">
          <div><MapPin /><span><small>{choose("具体位置", "Location")}</small><strong>{catalog.address}</strong></span></div>
          <div><Clock3 /><span><small>{choose("开放时间", "Opening hours")}</small><strong>{catalog.openingHours}</strong></span></div>
          <div><Users /><span><small>{choose("空间类型", "Space type")}</small><strong>{catalog.capacity}</strong></span></div>
          <div><DoorOpen /><span><small>{choose("访问方式", "Access")}</small><strong>{catalog.accessNote}</strong></span></div>
          <a href={catalog.mapUrl} target="_blank" rel="noreferrer">{choose("在地图中查看", "View on map")}<ExternalLink size={16} /></a>
          <button type="button" className="primary-button" onClick={() => void onChoose()}>
            <CheckCircle2 size={18} />
            {choose("选择此教室", "Choose this room")}
          </button>
          <p>{choose(
            "开放时间与预约状态可能因课表、假期和活动调整，请以 uNivUS 或现场信息为准。",
            "Opening hours and booking availability may change with timetables, holidays and events. Check uNivUS or on-site notices before visiting.",
          )}</p>
        </aside>
      </div>
      <div className="privacy-note">
        <ShieldCheck size={20} />
        <p>{choose(
          "这里只展示整体空间判断。系统不使用 RGB 摄像头，也不会识别或跟踪个人。",
          "Only room-level assessments are shown. The system does not use RGB cameras or identify or track individuals.",
        )}</p>
      </div>
    </section>
  );
}

function PreferencesView({
  request,
  busy,
  onSave,
}: {
  request: RecommendationRequest;
  busy: boolean;
  onSave: (request: RecommendationRequest) => Promise<void>;
}) {
  const { language, choose } = useLanguage();
  const [draft, setDraft] = useState(request);
  const [saved, setSaved] = useState(false);
  useEffect(() => setDraft(request), [request]);

  function setPriority(key: keyof RecommendationRequest["preferences"], value: number) {
    setDraft((current) => ({ ...current, preferences: { ...current.preferences, [key]: value } }));
  }

  async function save() {
    await onSave(draft);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  return (
    <section className="preferences-page">
      <PageTitle
        eyebrow="PERSONAL PREFERENCES"
        title={choose("个人偏好设置", "Personal preferences")}
        detail={choose("这些数值会保存在你的账户中，并用于重新排列首页推荐。", "These settings are saved to your account and used to rank your home-page recommendations.")}
      />
      <div className="preference-form">
        <section className="preference-section">
          <h2>{choose("你今天想怎么学习？", "How would you like to study today?")}</h2>
          <div className="mode-options">
            {([
              ["quiet", choose("安静学习", "Quiet study"), choose("更看重安静、低占用的空间", "Prioritise quiet, less occupied spaces"), BookOpen],
              ["discussion", choose("小组讨论", "Group discussion"), choose("优先寻找允许交流的空间", "Prioritise spaces where conversation is appropriate"), UserCircle],
              ["any", choose("都可以", "No preference"), choose("根据当前状态综合推荐", "Recommend based on current overall conditions"), DoorOpen],
            ] as const).map(([value, title, detail, Icon]) => (
              <button
                key={value}
                type="button"
                className={draft.study_mode === value ? "selected" : ""}
                onClick={() => setDraft((current) => ({ ...current, study_mode: value as StudyMode }))}
              >
                <Icon size={22} />
                <span><strong>{title}</strong><small>{detail}</small></span>
                {draft.study_mode === value ? <CheckCircle2 size={19} /> : null}
              </button>
            ))}
          </div>
        </section>
        <section className="preference-section">
          <h2>{choose("你更在意什么？", "What matters most to you?")}</h2>
          <p>{choose("拖动滑块即可，推荐会在保存后更新。", "Adjust the sliders; recommendations update after you save.")}</p>
          <PreferenceSlider label={choose("安静程度", "Quietness")} detail={choose("更少交谈与环境噪声", "Less conversation and ambient noise")} value={draft.preferences.quiet_priority} onChange={(value) => setPriority("quiet_priority", value)} />
          <PreferenceSlider label={choose("空闲程度", "Seat availability")} detail={choose("更偏好人少、容易找到座位", "Prefer spaces with fewer people and easier seating")} value={draft.preferences.low_occupancy_priority} onChange={(value) => setPriority("low_occupancy_priority", value)} />
          <PreferenceSlider label={choose("光线明亮", "Brightness")} detail={choose("更偏好明亮的学习环境", "Prefer a well-lit study environment")} value={draft.preferences.brightness_priority} onChange={(value) => setPriority("brightness_priority", value)} />
          <PreferenceSlider label={choose("温湿度舒适", "Thermal comfort")} detail={choose("更看重环境体感", "Prioritise comfortable temperature and humidity")} value={draft.preferences.comfort_priority} onChange={(value) => setPriority("comfort_priority", value)} />
          <PreferenceSlider label={choose("距离更近", "Proximity")} detail={choose("位置数据可用时参与推荐", "Used when location data is available")} value={draft.preferences.distance_priority} onChange={(value) => setPriority("distance_priority", value)} />
        </section>
        <div className="preference-actions">
          <span>{saved
            ? choose("已保存，首页推荐已更新", "Saved. Your home-page recommendations have been updated.")
            : choose("偏好仅与你的账户关联", "Preferences are linked only to your account")}</span>
          <button type="button" className="primary-button" onClick={() => void save()} disabled={busy}>
            {busy ? <RefreshCw className="spin" size={18} /> : <CheckCircle2 size={18} />}
            {choose("保存偏好", "Save preferences")}
          </button>
        </div>
      </div>
    </section>
  );
}

function PreferenceSlider({
  label,
  detail,
  value,
  onChange,
}: {
  label: string;
  detail: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const { language } = useLanguage();
  return (
    <label className="preference-slider">
      <span><strong>{label}</strong><small>{detail}</small></span>
      <input type="range" min="0" max="1" step="0.1" value={value} onChange={(event) => onChange(Number(event.currentTarget.value))} />
      <em>{priorityWord(value, language)}</em>
    </label>
  );
}

function AccountView({
  user,
  preferences,
  history,
  outbox,
  busy,
  onRetrySelection,
  onLearningToggle,
  onResetLearned,
  onDeleteSelections,
  onDeleteAccount,
  onSignOut,
}: {
  user: UserResponse;
  preferences: MePreferenceResponse | null;
  history: DashboardData["selectionHistory"];
  outbox: FailedSelection[];
  busy: boolean;
  onRetrySelection: (item: FailedSelection) => Promise<void>;
  onLearningToggle: (enabled: boolean) => Promise<void>;
  onResetLearned: () => Promise<void>;
  onDeleteSelections: () => Promise<void>;
  onDeleteAccount: () => Promise<void>;
  onSignOut: () => void;
}) {
  const { locale, choose } = useLanguage();
  return (
    <section className="account-page">
      <PageTitle eyebrow="YOUR ACCOUNT" title={choose("账户", "Account")} detail={choose("管理你的登录状态与隐私信息。", "Manage your session and privacy information.")} />
      <div className="account-profile">
        <div className="profile-avatar"><UserCircle size={34} /></div>
        <div>
          <span>{choose("普通用户", "Student account")}</span>
          <h2>{user.username}</h2>
          <p>{choose("账户创建于", "Account created")} {formatDate(user.created_at, locale)}</p>
        </div>
      </div>
      <section className="account-section">
        <div><h2>{choose("个人偏好记录", "Preference record")}</h2><p>{choose("你的学习模式与五项优先级已保存在数据库中。", "Your study mode and five preference priorities are stored in the database.")}</p></div>
        <span className="status-confirm"><CheckCircle2 size={18} />{choose("已同步", "Synced")}</span>
      </section>
      <section className="account-section privacy-account">
        <div><h2>{choose("隐私承诺", "Privacy commitment")}</h2><p>{choose(
          "系统不收集学号、真实姓名、摄像画面或原始录音。推荐只使用房间整体状态和你主动设置的偏好。",
          "The system does not collect student IDs, real names, camera footage or raw audio. Recommendations use only room-level conditions and the preferences you choose to provide.",
        )}</p></div>
        <ShieldCheck size={26} />
      </section>
      <section className="account-section">
        <div>
          <h2>{choose("选择历史与偏好学习", "Choice history and preference learning")}</h2>
          <p>
            {choose("只记录你明确点击“选择此教室”的操作。", "Only explicit “Choose this room” actions are recorded.")}
          </p>
          <label className="learning-toggle">
            <input
              type="checkbox"
              checked={preferences?.learning_enabled ?? true}
              disabled={busy}
              onChange={(event) => void onLearningToggle(event.currentTarget.checked)}
            />
            <span>{choose("允许选择历史影响推荐", "Allow choice history to influence recommendations")}</span>
          </label>
        </div>
        <div className="account-actions">
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void onResetLearned()}>
            {choose("重置学习偏好", "Reset learned preferences")}
          </button>
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void onDeleteSelections()}>
            {choose("删除选择历史", "Delete choice history")}
          </button>
        </div>
      </section>
      {history?.selections.length ? (
        <section className="account-section selection-history">
          <div>
            <h2>{choose("最近选择", "Recent choices")}</h2>
            <ul>
              {history.selections.slice(0, 6).map((selection) => (
                <li key={selection.selection_id}>
                  <strong>{selection.room_name}</strong>
                  <span>{selection.selected_rank ? `#${selection.selected_rank}` : selection.source}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
      {outbox.length ? (
        <section className="account-section selection-outbox">
          <div>
            <h2>{choose("等待重试", "Waiting to retry")}</h2>
            <p>{choose("网络恢复后可使用同一幂等 ID 重试。", "Retry with the same idempotency ID after connectivity returns.")}</p>
          </div>
          <div className="account-actions">
            {outbox.map((item) => (
              <button
                key={item.selectionId}
                type="button"
                className="secondary-button"
                disabled={busy}
                onClick={() => void onRetrySelection(item)}
              >
                {choose("重试", "Retry")} {item.roomName}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      <section className="account-section">
        <div><h2>{choose("当前会话", "Current session")}</h2><p>{user.username}</p></div>
        <button type="button" className="secondary-button" onClick={onSignOut}><LogOut size={18} />{choose("退出登录", "Sign out")}</button>
      </section>
      <section className="account-section danger-zone">
        <div><h2>{choose("删除账户", "Delete account")}</h2><p>{choose("删除账户、会话、选择历史和派生偏好。", "Delete the account, sessions, choice history and learned preferences.")}</p></div>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => void onDeleteAccount()}>
          {choose("永久删除", "Delete permanently")}
        </button>
      </section>
    </section>
  );
}

function AdminApp({
  user,
  data,
  error,
  refreshing,
  onRefresh,
  onSignOut,
}: {
  user: UserResponse;
  data: DashboardData;
  error: string | null;
  refreshing: boolean;
  onRefresh: () => void;
  onSignOut: () => void;
}) {
  const { locale, choose } = useLanguage();
  const [page, setPage] = useState<AdminPage>("overview");
  const healthyRooms = data.rooms.filter((room) => !room.is_stale && !Object.values(room.sensor_health).some((health) => health === "offline")).length;
  const alerts = data.rooms.reduce((count, room) => count + Number(room.is_stale) + Object.values(room.sensor_health).filter((health) => health === "offline" || health === "degraded").length, 0);
  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <Brand />
        <div className="admin-identity"><Settings size={18} /><span><strong>{user.username}</strong><small>{choose("系统管理员", "System administrator")}</small></span></div>
        <nav aria-label={choose("管理员菜单", "Administrator navigation")}>
          <AdminNavButton active={page === "overview"} icon={<Activity />} label={choose("总览", "Overview")} onClick={() => setPage("overview")} />
          <AdminNavButton active={page === "monitor"} icon={<Radio />} label={choose("实时监测", "Live monitor")} onClick={() => setPage("monitor")} />
          <AdminNavButton active={page === "rooms"} icon={<DoorOpen />} label={choose("教室数据", "Room data")} onClick={() => setPage("rooms")} />
          <AdminNavButton active={page === "system"} icon={<Server />} label={choose("系统状态", "System status")} onClick={() => setPage("system")} />
        </nav>
        <button type="button" className="admin-logout" aria-label={choose("退出登录", "Sign out")} title={choose("退出登录", "Sign out")} onClick={onSignOut}><LogOut size={18} /><span>{choose("退出登录", "Sign out")}</span></button>
      </aside>
      <main className="admin-content">
        <header className="admin-topbar">
          <div><p className="overline">ADMIN CONSOLE</p><h1>{
            page === "overview"
              ? choose("运行总览", "Operational overview")
              : page === "monitor"
                ? choose("实时传感器监测", "Live sensor monitoring")
                : page === "rooms"
                  ? choose("教室量化数据", "Quantitative room data")
                  : choose("系统与模块状态", "System and module status")
          }</h1></div>
          <div className="admin-top-actions">
            <LanguageToggle />
            <button type="button" className="secondary-button" onClick={onRefresh} disabled={refreshing}>
              <RefreshCw className={refreshing ? "spin" : ""} size={18} />{choose("刷新", "Refresh")}
            </button>
          </div>
        </header>
        {error ? <StatusBanner text={error} /> : null}
        {page === "overview" ? (
          <>
            <section className="admin-kpi-grid">
              <AdminKpi label={choose("活跃教室", "Active rooms")} value={`${data.rooms.length}`} detail={choose("当前参与监测", "Currently monitored")} icon={<DoorOpen />} />
              <AdminKpi label={choose("状态正常", "Healthy")} value={`${healthyRooms}`} detail={choose("数据新鲜且传感器在线", "Fresh data and sensors online")} icon={<CheckCircle2 />} tone="ok" />
              <AdminKpi label={choose("待处理告警", "Open alerts")} value={`${alerts}`} detail={choose("过期、降级或离线", "Stale, degraded or offline")} icon={<AlertTriangle />} tone={alerts ? "warning" : "ok"} />
              <AdminKpi label={choose("推荐请求", "Recommendations")} value={`${data.recommendations.recommendations.length}`} detail={choose("本轮候选结果", "Candidates in this cycle")} icon={<Cpu />} />
            </section>
            <section className="admin-section">
              <SectionBar title={choose("教室运行状态", "Room operations")} detail={choose("量化数据仅在管理员端展示", "Quantitative data is restricted to administrators")} />
              <AdminRoomTable rooms={data.rooms} compact />
            </section>
          </>
        ) : null}
        {page === "monitor" ? <LiveMonitor rooms={data.rooms} /> : null}
        {page === "rooms" ? (
          <section className="admin-section">
            <SectionBar title={choose("实时量化遥测", "Live quantitative telemetry")} detail={`${choose("更新于", "Updated")} ${formatTime(data.lastUpdated, locale)}`} />
            <AdminRoomTable rooms={data.rooms} />
          </section>
        ) : null}
        {page === "system" ? <SystemView data={data} /> : null}
      </main>
    </div>
  );
}

function LiveMonitor({ rooms }: { rooms: RoomStatus[] }) {
  const { language, locale, choose } = useLanguage();
  const [roomId, setRoomId] = useState(rooms[0]?.room_id ?? "");
  const [snapshot, setSnapshot] = useState<LiveSensorSnapshotResponse | null>(null);
  const [monitorError, setMonitorError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const pollMs = Math.max(500, Number(import.meta.env.VITE_LIVE_SENSOR_POLL_MS ?? 1000));

  useEffect(() => {
    if (!roomId) return;
    let active = true;
    let running = false;
    async function poll() {
      if (running) return;
      running = true;
      setPolling(true);
      try {
        const next = await loadLiveSensorSnapshot(roomId);
        if (active) {
          setSnapshot(next);
          setMonitorError(null);
        }
      } catch (error) {
        if (active) setMonitorError(messageFrom(error, choose("实时传感器数据暂时不可用。", "Live sensor data is temporarily unavailable."), language));
      } finally {
        running = false;
        if (active) setPolling(false);
      }
    }
    setSnapshot(null);
    void poll();
    const timer = window.setInterval(() => void poll(), pollMs);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [roomId, pollMs]);

  const room = snapshot?.room ?? rooms.find((entry) => entry.room_id === roomId) ?? rooms[0];
  if (!room) {
    return <EmptyPanel title={choose("没有可监测的教室", "No rooms available to monitor")} detail={choose("教室注册后会出现在这里。", "Registered rooms will appear here.")} />;
  }
  const catalog = catalogFor(room, language);
  const peopleCount = snapshot?.people_count.available ? snapshot.people_count.predicted_people_count_rounded : snapshot?.thermal_analysis.estimated_people_count;
  const updatedAt = snapshot?.generated_at ? formatTime(snapshot.generated_at, locale) : "--";

  return (
    <div className="live-monitor">
      <section className="monitor-room-strip" aria-label={choose("选择监测教室", "Select a room to monitor")}>
        {rooms.map((entry) => {
          const entryCatalog = catalogFor(entry, language);
          return (
            <button key={entry.room_id} type="button" className={roomId === entry.room_id ? "active" : ""} onClick={() => setRoomId(entry.room_id)}>
              <span className={`monitor-room-dot ${stateTone(entry.room_state)}`} />
              <span><strong>{entryCatalog.displayName}</strong><small>{entryCatalog.shortLocation}</small></span>
            </button>
          );
        })}
      </section>

      <section className="monitor-heading">
        <div>
          <span className="live-indicator"><i />LIVE SENSOR FEED</span>
          <h2>{catalog.displayName}</h2>
          <p>{catalog.shortLocation} · {choose("更新于", "Updated")} {updatedAt}</p>
        </div>
        <span className={`monitor-connection ${monitorError ? "warning" : "ok"}`}>
          {polling ? <RefreshCw className="spin" size={15} /> : <Wifi size={15} />}
          {monitorError ? choose("连接降级", "Connection degraded") : choose("正在监测", "Monitoring")}
        </span>
      </section>
      {monitorError ? <StatusBanner text={monitorError} /> : null}

      <div className="monitor-primary-grid">
        <section className="thermal-monitor-panel">
          <div className="monitor-panel-heading">
            <div><span>MLX90640 · 32×24</span><h3>{choose("实时热成像与热区检测", "Live thermal view and heat-region detection")}</h3></div>
            <span>{snapshot?.thermal_analysis.detected_region_count ?? 0} {choose("个检测框", "detection boxes")}</span>
          </div>
          <ThermalCanvas snapshot={snapshot} />
          <div className="thermal-footer">
            <span><ScanLine size={16} />{choose("检测框来自热区连通分析，不进行身份识别", "Boxes are generated by connected heat-region analysis, without identity recognition")}</span>
            <span>{choose("阈值", "Threshold")} {formatNumber(snapshot?.thermal_analysis.threshold, "", 2)}</span>
          </div>
        </section>

        <aside className="monitor-side-stack">
          <section className="people-count-panel">
            <div className="sensor-card-icon"><Users /></div>
            <span>{choose("模型预测人数", "Model-estimated occupancy")}</span>
            <strong>{peopleCount ?? "--"}<small> {choose("人", "people")}</small></strong>
            <p>{snapshot?.people_count.model
              ? `${snapshot.people_count.model.name} · ${snapshot.people_count.model.version}`
              : choose("等待 Module 2 人数模型输出", "Waiting for the Module 2 occupancy model")}</p>
            <div><span>{choose("置信度", "Confidence")}</span><em>{formatPercent(snapshot?.people_count.confidence)}</em></div>
          </section>
          <section className="sound-monitor-panel">
            <div className="monitor-panel-heading compact">
              <div><span>WINDOWS MICROPHONE</span><h3>{choose("声音强度", "Sound intensity")}</h3></div>
              <Volume2 size={18} />
            </div>
            <SoundBars rms={snapshot?.sound_preview.rms ?? room.features.sound_rms_mean ?? 0} />
            <div className="sound-reading"><strong>{formatNumber(snapshot?.sound_preview.rms ?? room.features.sound_rms_mean, "", 3)}</strong><span>Relative RMS</span></div>
          </section>
        </aside>
      </div>

      <section className="sensor-metric-grid">
        <SensorMetric icon={<Thermometer />} label={choose("温度", "Temperature")} value={formatNumber(room.features.temperature_c, "°C", 1)} health={room.sensor_health.environment} />
        <SensorMetric icon={<Droplets />} label={choose("湿度", "Humidity")} value={formatNumber(room.features.humidity_pct, "%", 0)} health={room.sensor_health.environment} />
        <SensorMetric icon={<Lightbulb />} label={choose("相对光照", "Relative light level")} value={formatNumber(room.features.light_relative_mean ?? room.features.light_lux, room.features.light_relative_mean != null ? "" : " lx", room.features.light_relative_mean != null ? 2 : 0)} health={room.sensor_health.environment} />
        <SensorMetric icon={<Gauge />} label={choose("综合适合度", "Overall suitability")} value={formatNumber(room.suitability_score, "/100", 0)} health={room.is_stale ? "degraded" : "ok"} />
      </section>

      <section className="state-classifier-panel">
        <div className="monitor-panel-heading">
          <div><span>MODULE 2 · FOUR-STATE CLASSIFIER</span><h3>{choose("当前教室综合状态", "Current combined room state")}</h3></div>
          <span className={`table-state ${stateTone(room.room_state)}`}>{roomStateText[room.room_state][language]}</span>
        </div>
        <div className="state-classifier-grid">
          {([
            ["empty_or_low_activity", choose("空教室 / 低活动", "Empty / low activity"), choose("低人数与低声音活动", "Low occupancy and low sound activity")],
            ["quiet_study_recommended", choose("安静学习", "Quiet study"), choose("适合个人专注学习", "Suitable for focused individual study")],
            ["discussion_allowed", choose("允许讨论", "Discussion allowed"), choose("适合正常小组交流", "Suitable for normal group conversation")],
            ["not_recommended_noisy_or_crowded", choose("不推荐", "Not recommended"), choose("持续嘈杂或拥挤", "Persistently noisy or crowded")],
          ] as const).map(([state, label, detail]) => (
            <div key={state} className={room.room_state === state ? `active ${stateTone(state)}` : ""}>
              <span>{room.room_state === state ? <CheckCircle2 /> : <span />}</span>
              <strong>{label}</strong>
              <small>{detail}</small>
            </div>
          ))}
        </div>
        <footer>
          <span>{choose("分类置信度", "Classification confidence")} <strong>{formatPercent(room.confidence)}</strong></span>
          <span>{choose("模型", "Model")} {room.warnings.length
            ? choose(`含 ${room.warnings.length} 条警告`, `${room.warnings.length} warning${room.warnings.length === 1 ? "" : "s"}`)
            : choose("输入完整", "Complete input")}</span>
          <span>{choose("数据年龄", "Data age")} <strong>{room.data_age_seconds == null ? "--" : `${Math.round(room.data_age_seconds)}s`}</strong></span>
        </footer>
      </section>
    </div>
  );
}

function ThermalCanvas({ snapshot }: { snapshot: LiveSensorSnapshotResponse | null }) {
  const { language, choose } = useLanguage();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const preview = snapshot?.thermal_preview;
  const boxes = snapshot?.thermal_analysis.boxes ?? [];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const width = 640;
    const height = 480;
    canvas.width = width;
    canvas.height = height;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#090c12";
    context.fillRect(0, 0, width, height);
    if (!preview?.available || !preview.values || !preview.width || !preview.height) return;
    const previewWidth = preview.width;
    const previewHeight = preview.height;
    const cellWidth = width / previewWidth;
    const cellHeight = height / previewHeight;
    preview.values.forEach((value, index) => {
      context.fillStyle = thermalColor(value);
      context.fillRect((index % previewWidth) * cellWidth, Math.floor(index / previewWidth) * cellHeight, Math.ceil(cellWidth), Math.ceil(cellHeight));
    });
    boxes.forEach((box, index) => {
      const x = box.x * width;
      const y = box.y * height;
      const boxWidth = box.width * width;
      const boxHeight = box.height * height;
      context.strokeStyle = "#7be7ff";
      context.lineWidth = 3;
      context.strokeRect(x, y, boxWidth, boxHeight);
      context.fillStyle = "rgba(3, 12, 20, 0.82)";
      context.fillRect(x, Math.max(0, y - 25), language === "zh" ? 96 : 142, 25);
      context.fillStyle = "#dffaff";
      context.font = "600 13px system-ui";
      context.fillText(
        `${choose("热区", "Region")} ${index + 1} · ${Math.round(box.confidence * 100)}%`,
        x + 7,
        Math.max(17, y - 8),
      );
    });
  }, [preview, boxes, choose, language]);

  return (
    <div className="thermal-canvas-wrap">
      <canvas ref={canvasRef} aria-label={choose("实时热成像检测画面", "Live thermal detection view")} />
      {!preview?.available ? (
        <div className="thermal-empty">
          <ScanLine size={28} />
          <strong>{choose("等待热成像数据", "Waiting for thermal data")}</strong>
          <span>{choose("连接 MLX90640 后将自动显示", "The feed will appear when the MLX90640 is connected")}</span>
        </div>
      ) : null}
      <div className="thermal-scale"><span>{choose("低", "Low")}</span><i /><span>{choose("高", "High")}</span></div>
    </div>
  );
}

function SoundBars({ rms }: { rms: number }) {
  const { choose } = useLanguage();
  const bars = Array.from({ length: 28 }, (_, index) => {
    const wave = 0.35 + Math.abs(Math.sin(index * 0.78 + rms * 9)) * 0.65;
    return Math.max(8, Math.min(100, wave * Math.max(0.16, rms) * 130));
  });
  return <div className="sound-bars" aria-label={`${choose("声音相对 RMS", "Relative sound RMS")} ${rms.toFixed(3)}`}>{bars.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>;
}

function SensorMetric({ icon, label, value, health }: { icon: ReactNode; label: string; value: string; health: string | undefined }) {
  const { language } = useLanguage();
  return (
    <article className="sensor-metric">
      <span className="sensor-card-icon">{icon}</span>
      <div><small>{label}</small><strong>{value}</strong></div>
      <em className={health ?? "offline"}>{sensorHealthText(health, language)}</em>
    </article>
  );
}

function AdminNavButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return <button type="button" className={active ? "active" : ""} aria-label={label} title={label} onClick={onClick}>{icon}<span>{label}</span></button>;
}

function AdminKpi({ label, value, detail, icon, tone = "" }: { label: string; value: string; detail: string; icon: ReactNode; tone?: string }) {
  return (
    <article className={`admin-kpi ${tone}`}>
      <div><span>{label}</span>{icon}</div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function AdminRoomTable({ rooms, compact = false }: { rooms: RoomStatus[]; compact?: boolean }) {
  const { language, choose } = useLanguage();
  return (
    <div className="admin-table-wrap">
      <table className="admin-room-table">
        <thead>
          <tr>
            <th>{choose("教室", "Room")}</th>
            <th>{choose("分类状态", "Classification")}</th>
            <th>{choose("占用", "Occupancy")}</th>
            <th>{choose("适合度", "Suitability")}</th>
            <th>{choose("置信度", "Confidence")}</th>
            {!compact ? <><th>{choose("温度", "Temperature")}</th><th>{choose("湿度", "Humidity")}</th><th>{choose("光照", "Light")}</th><th>{choose("声音 RMS", "Sound RMS")}</th></> : null}
            <th>{choose("数据年龄", "Data age")}</th>
          </tr>
        </thead>
        <tbody>
          {rooms.map((room) => {
            const catalog = catalogFor(room, language);
            return <tr key={room.room_id}>
              <td><strong>{catalog.displayName}</strong><small>{catalog.shortLocation}</small></td>
              <td><span className={`table-state ${stateTone(room.room_state)}`}>{roomStateText[room.room_state][language]}</span></td>
              <td>{occupancyAdminText(room.occupancy_level, language)}</td>
              <td>{formatNumber(room.suitability_score, "", 0)}</td>
              <td>{formatPercent(room.confidence)}</td>
              {!compact ? (
                <>
                  <td>{formatNumber(room.features.temperature_c, "°C", 1)}</td>
                  <td>{formatNumber(room.features.humidity_pct, "%", 0)}</td>
                  <td>{formatNumber(room.features.light_lux, " lx", 0)}</td>
                  <td>{formatNumber(room.features.sound_rms_mean, "", 3)}</td>
                </>
              ) : null}
              <td>{room.data_age_seconds == null ? "--" : `${Math.round(room.data_age_seconds)}s`}</td>
            </tr>
          })}
        </tbody>
      </table>
    </div>
  );
}

function SystemView({ data }: { data: DashboardData }) {
  const { language, choose } = useLanguage();
  const sensorRows = data.rooms.flatMap((room) => Object.entries(room.sensor_health).map(([sensor, health]) => ({ room, sensor, health })));
  return (
    <div className="system-grid">
      <section className="admin-section">
        <SectionBar title={choose("服务状态", "Service status")} detail={choose("前端、后端、数据库与推荐适配器", "Frontend, backend, database and recommendation adapter")} />
        <div className="service-list">
          <ServiceRow icon={<Wifi />} label={choose("前端连接", "Frontend connection")} value={choose("正常", "Operational")} tone="ok" />
          <ServiceRow icon={<Server />} label={choose("FastAPI 后端", "FastAPI backend")} value={data.backendStatus === "ok" ? choose("正常", "Operational") : choose("降级", "Degraded")} tone={data.backendStatus === "ok" ? "ok" : "warning"} />
          <ServiceRow icon={<Database />} label={choose("SQLite 数据库", "SQLite database")} value={choose("已连接", "Connected")} tone="ok" />
          <ServiceRow icon={<Cpu />} label={choose("推荐适配器", "Recommendation adapter")} value={data.recommendations.warnings.includes("RECOMMENDATION_ADAPTER_FALLBACK") ? choose("回退模式", "Fallback mode") : choose("规则模式", "Rule-based mode")} tone="ok" />
        </div>
      </section>
      <section className="admin-section">
        <SectionBar title={choose("传感器健康", "Sensor health")} detail={choose("按教室与传感器查看", "Status by room and sensor")} />
        <div className="sensor-health-grid">
          {sensorRows.map(({ room, sensor, health }) => (
            <div key={`${room.room_id}-${sensor}`} className="sensor-health-row">
              <span><strong>{catalogFor(room, language).displayName}</strong><small>{sensorName(sensor, language)}</small></span>
              <em className={health}>{sensorHealthText(health, language)}</em>
            </div>
          ))}
        </div>
      </section>
      <section className="admin-section system-privacy">
        <SectionBar title={choose("隐私边界", "Privacy boundaries")} detail={choose("系统内部实现约束", "System implementation constraints")} />
        <ul>
          <li>{choose("热阵列只保留 32 × 24 的短时归一化预览，不写入历史数据库。", "The thermal array retains only a short-lived normalised 32 × 24 preview; it is never written to historical storage.")}</li>
          <li>{choose("声音模块只处理强度摘要，不保存原始波形或录音。", "The sound module processes intensity summaries only; raw waveforms and recordings are not stored.")}</li>
          <li>{choose("推荐层只接收结构化房间状态与匿名偏好。", "The recommendation layer receives only structured room states and pseudonymous preferences.")}</li>
          <li>{choose("学生端只显示定性结果，量化遥测集中在本管理员界面。", "The student interface shows qualitative guidance only; quantitative telemetry is restricted to this administrator console.")}</li>
        </ul>
      </section>
    </div>
  );
}

function ServiceRow({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: string }) {
  return <div className="service-row"><span className="service-icon">{icon}</span><strong>{label}</strong><em className={tone}>{value}</em></div>;
}

function LanguageToggle() {
  const { language, choose, toggleLanguage } = useLanguage();
  const label = choose("切换为英文", "Switch to Chinese");
  return (
    <button type="button" className="icon-button language-toggle" aria-label={label} title={label} onClick={toggleLanguage}>
      <Languages size={19} />
      <span aria-hidden="true">{language === "zh" ? "EN" : "中"}</span>
    </button>
  );
}

function Brand() {
  const { choose } = useLanguage();
  return (
    <div className="brand">
      <span className="brand-mark"><BookOpen size={21} /></span>
      <span><strong>StudySpace</strong><small>{choose("隐私优先学习助手", "Privacy-first advisor")}</small></span>
    </div>
  );
}

function PageTitle({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return <header className="page-title"><p className="overline">{eyebrow}</p><h1>{title}</h1><p>{detail}</p></header>;
}

function SectionBar({ title, detail }: { title: string; detail: string }) {
  return <div className="section-bar"><div><h2>{title}</h2><p>{detail}</p></div></div>;
}

function StatusBanner({ text }: { text: string }) {
  return <div className="status-banner" role="status"><AlertTriangle size={18} /><span>{text}</span></div>;
}

function EmptyPanel({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-panel"><DoorOpen size={24} /><strong>{title}</strong><p>{detail}</p></div>;
}

function AppLoading() {
  const { choose } = useLanguage();
  return (
    <main className="app-loading">
      <Brand />
      <RefreshCw className="spin" size={24} />
      <p>{choose("正在准备你的学习空间", "Preparing your study spaces")}</p>
    </main>
  );
}

function requestFromPreferences(preferences: MePreferenceResponse, profileId: string): RecommendationRequest {
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
    candidate_room_ids: defaultRequest.candidate_room_ids,
  };
}

function greeting(date: Date, language: Language) {
  const hour = date.getHours();
  if (hour < 11) return selectText(language, "早上好", "Good morning");
  if (hour < 13) return selectText(language, "中午好", "Good afternoon");
  if (hour < 18) return selectText(language, "下午好", "Good afternoon");
  return selectText(language, "晚上好", "Good evening");
}

function dailyQuote(date: Date, language: Language) {
  const start = new Date(date.getFullYear(), 0, 0);
  const day = Math.floor((date.getTime() - start.getTime()) / 86_400_000);
  return quotes[day % quotes.length][language];
}

function qualitativeFit(score: number, language: Language) {
  if (score >= 80) return selectText(language, "非常适合你", "Excellent match");
  if (score >= 58) return selectText(language, "比较适合", "Good match");
  return selectText(language, "可以作为备选", "Suitable alternative");
}

function fitTone(score: number) {
  return score >= 80 ? "excellent" : score >= 58 ? "good" : "fair";
}

function stateTone(state: RoomState) {
  if (state === "quiet_study_recommended" || state === "empty_or_low_activity") return "ok";
  if (state === "discussion_allowed") return "info";
  if (state === "not_recommended_noisy_or_crowded") return "warning";
  return "muted";
}

function forecastText(level: OccupancyLevel, language: Language) {
  if (level === "empty" || level === "low") return selectText(language, "未来半小时预计宽松", "Good availability expected for the next 30 minutes");
  if (level === "medium") return selectText(language, "未来半小时人数适中", "Moderate occupancy expected for the next 30 minutes");
  if (level === "high") return selectText(language, "未来半小时可能拥挤", "Crowding is likely within the next 30 minutes");
  return selectText(language, "未来趋势待确认", "30-minute outlook pending");
}

function qualitativeSummary(room: RoomStatus, recommendation: RecommendationItem | null, language: Language) {
  if (room.room_state === "unknown") return selectText(language, "目前缺少足够的新数据，建议到现场确认后再决定。", "There is not enough fresh data yet. Verify the room on arrival before deciding.");
  if (room.is_stale) return selectText(language, "这个空间可能仍然可用，但最新状态有延迟，建议谨慎参考。", "This space may still be suitable, but its latest status is delayed. Treat the recommendation with caution.");
  if (!recommendation) return selectText(language, "当前状态可供参考，你也可以回到首页查看更符合个人偏好的选择。", "The current status is available for reference. Return to Home to compare rooms against your preferences.");
  if (recommendation.score >= 80) return selectText(language, "当前环境与你设置的学习偏好很匹配，适合作为首选。", "Current conditions align closely with your study preferences, making this a strong first choice.");
  if (recommendation.score >= 58) return selectText(language, "整体比较符合你的需求，在首选空间不可用时值得考虑。", "This room meets most of your needs and is worth considering when your first choice is unavailable.");
  return selectText(language, "当前环境与部分偏好不太匹配，建议同时查看其他教室。", "Current conditions do not align with some of your preferences. Consider comparing other rooms.");
}

function priorityWord(value: number, language: Language) {
  if (value >= 0.8) return selectText(language, "很重要", "High priority");
  if (value >= 0.5) return selectText(language, "比较重要", "Important");
  if (value >= 0.2) return selectText(language, "一般", "Moderate");
  return selectText(language, "不太在意", "Low priority");
}

function weatherDescription(code: number, language: Language) {
  if (code === 0) return selectText(language, "晴", "Clear");
  if (code <= 3) return selectText(language, "多云", "Partly cloudy");
  if (code <= 48) return selectText(language, "有雾", "Foggy");
  if (code <= 67) return selectText(language, "有雨", "Rain");
  if (code <= 77) return selectText(language, "有雪", "Snow");
  if (code <= 82) return selectText(language, "阵雨", "Showers");
  return selectText(language, "雷雨", "Thunderstorms");
}

function occupancyAdminText(level: OccupancyLevel, language: Language) {
  const labels: Record<OccupancyLevel, Record<Language, string>> = {
    empty: { zh: "空闲", en: "Empty" },
    low: { zh: "低", en: "Low" },
    medium: { zh: "中", en: "Medium" },
    high: { zh: "高", en: "High" },
    unknown: { zh: "未知", en: "Unknown" },
  };
  return labels[level][language];
}

function sensorHealthText(health: string | undefined, language: Language) {
  const labels: Record<string, Record<Language, string>> = {
    ok: { zh: "正常", en: "Healthy" },
    degraded: { zh: "降级", en: "Degraded" },
    offline: { zh: "离线", en: "Offline" },
    unknown: { zh: "未知", en: "Unknown" },
  };
  return (labels[health ?? "offline"] ?? labels.unknown)[language];
}

function sensorName(sensor: string, language: Language) {
  const labels: Record<string, Record<Language, string>> = {
    environment: { zh: "温湿度", en: "Temperature and humidity" },
    thermal: { zh: "热阵列", en: "Thermal array" },
    light: { zh: "光照", en: "Light" },
    sound: { zh: "声音", en: "Sound" },
    radar: { zh: "雷达", en: "Radar" },
  };
  return (labels[sensor] ?? { zh: sensor, en: sensor })[language];
}

function thermalColor(value: number) {
  const stops = [
    [8, 14, 35],
    [25, 48, 108],
    [30, 126, 164],
    [79, 196, 116],
    [243, 211, 72],
    [241, 98, 43],
    [255, 238, 218],
  ];
  const scaled = Math.max(0, Math.min(0.999, value)) * (stops.length - 1);
  const index = Math.floor(scaled);
  const mix = scaled - index;
  const current = stops[index];
  const next = stops[Math.min(stops.length - 1, index + 1)];
  const channel = (position: number) => Math.round(current[position] + (next[position] - current[position]) * mix);
  return `rgb(${channel(0)} ${channel(1)} ${channel(2)})`;
}

function formatNumber(value: number | null | undefined, unit: string, digits: number) {
  return value == null || !Number.isFinite(value) ? "--" : `${value.toFixed(digits)}${unit}`;
}

function formatPercent(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "--" : `${Math.round(value * 100)}%`;
}

function formatTime(value: string | undefined, locale: string) {
  return value ? new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value)) : "--";
}

function formatDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric" }).format(new Date(value));
}

function messageFrom(error: unknown, fallback: string, language: Language) {
  return error instanceof Error ? localizeKnownMessage(error.message, language) : fallback;
}
