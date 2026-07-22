import {
  createMockSnapshot,
  isFreshLiveSensorSnapshot,
  isLiveSensorSnapshot
} from "./sensor-data.mjs";

const configured = window.AIOT_CONFIG ?? {};
const queryMode = new URLSearchParams(location.search).get("mode");
const useMocks = queryMode ? queryMode !== "api" : configured.useMocks !== false;
const apiBaseUrl = String(configured.apiBaseUrl ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const roomId = configured.roomId ?? "room_a";
const pollInterval = Math.max(500, Number(configured.pollIntervalMs) || 2500);
const history = { temperature: [], humidity: [], light: [], sound: [] };
let sequence = 0;
let smoothing = true;
let timer;
let renderedThermal = [];
let thermalAnimation;

const stateLabels = {
  empty_or_low_activity: "低活动",
  quiet_study_recommended: "安静舒适",
  discussion_allowed: "适合讨论",
  not_recommended_noisy_or_crowded: "声音偏高",
  unknown: "状态未知"
};

document.querySelector("#root").innerHTML = `
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <div class="background-grid" aria-hidden="true"></div>
    <header class="topbar">
      <div class="brand" aria-label="AIoT 环境感知台">
        <span class="brand__mark" aria-hidden="true">≋</span>
        <span class="brand__copy"><strong>SENSE / LOCAL</strong><small>AIoT 环境感知台</small></span>
      </div>
      <div class="topbar__actions">
        <div id="connection" class="connection-pill" aria-live="polite"><span class="connection-pill__pulse"></span>${useMocks ? "模拟数据" : "连接中"}</div>
        <button id="refresh" class="icon-button" type="button" aria-label="立即刷新数据" title="立即刷新数据">↻</button>
      </div>
    </header>
    <main id="main-content" class="dashboard">
      <section class="dashboard-heading" aria-labelledby="dashboard-title">
        <div><p class="eyebrow">ROOM_A / LIVE SENSOR OVERVIEW</p><h1 id="dashboard-title">环境实时概览</h1><p class="dashboard-heading__intro">汇总温湿度、光照、声音与匿名低分辨率热分布，所有数据仅在本机处理。</p></div>
        <dl class="update-meta">
          <div><dt>空间状态</dt><dd><span class="status-dot"></span><span id="room-state">等待数据</span></dd></div>
          <div><dt>最近更新</dt><dd id="updated-at" class="numeric">--:--:--</dd></div>
        </dl>
      </section>
      <div id="error-banner" class="error-banner" role="alert" hidden><span>!</span><span id="error-text"></span><button id="retry" type="button">重试</button></div>
      <section class="metric-grid" aria-label="当前传感器读数">
        ${metricCard("temperature", "空气温度", "°C", "DHT11 · 当前环境温度", "♨")}
        ${metricCard("humidity", "相对湿度", "%", "DHT11 · 相对湿度", "◌")}
        ${metricCard("light", "光照强度", "%", "HW-486 · ADC 相对强度", "☼")}
        ${metricCard("sound", "声音强度", "%", "HW-485 · 最近 10 秒相对峰值", "⌁")}
      </section>
      <section class="monitor-grid" aria-label="热成像和数据链路">
        <article class="thermal-panel panel">
          <header class="panel-heading">
            <div><p class="panel-kicker">▦ MLX90640 / THERMAL</p><h2>热分布画面</h2></div>
            <div class="thermal-actions"><span class="resolution-tag">32 × 24</span><button id="smoothing" class="smoothing-toggle is-active" type="button" aria-pressed="true">☷ <span>关闭平滑显示</span></button></div>
          </header>
          <div class="thermal-layout">
            <div class="thermal-visual">
              <div id="thermal-stage" class="thermal-stage">
                <canvas id="thermal-canvas" class="thermal-canvas" data-smoothing="on" width="768" height="576" role="img" aria-label="32 乘 24 低分辨率热分布图，亮色区域温度相对较高"></canvas>
                <div class="thermal-reticle" aria-hidden="true"><span class="thermal-reticle__x"></span><span class="thermal-reticle__y"></span></div>
                <span class="thermal-coordinate thermal-coordinate--tl">00 / 00</span><span class="thermal-coordinate thermal-coordinate--br">31 / 23</span><div class="thermal-scan" aria-hidden="true"></div>
              </div>
            </div>
            <div class="thermal-legend"><span>相对低温</span><span class="thermal-legend__bar"></span><span>相对高温</span></div>
          </div>
          <footer class="thermal-footer"><span>◉ 非摄像头图像，无身份识别</span><span id="smooth-mode">◫ 时间插值 + 空间平滑</span><span>◎ 热区 <b id="hot-regions">--</b></span></footer>
        </article>
        <aside class="system-panel panel" aria-labelledby="system-title">
          <div class="system-panel__header"><p class="panel-kicker">☁ PIPELINE STATUS</p><h2 id="system-title">数据链路</h2><p>当前读数沿用模块 01 → 02 的共享字段，真实数据接入时无需重做界面。</p></div>
          <ol class="pipeline-list">
            <li><span class="pipeline-list__index">01</span><div><strong>传感器窗口</strong><small>${useMocks ? "浏览器模拟源" : "Raspberry Pi 采集"}</small></div><span class="pipeline-list__state">READY</span></li>
            <li><span class="pipeline-list__index">02</span><div><strong>特征摘要</strong><small>共享契约 v1.0</small></div><span class="pipeline-list__state">READY</span></li>
            <li><span class="pipeline-list__index">UI</span><div><strong>平滑呈现</strong><small>60 FPS 时间插值</small></div><span class="pipeline-list__state">ACTIVE</span></li>
          </ol>
          <div class="health-summary"><h3>传感器健康</h3><dl><div><dt>热阵列</dt><dd id="health-thermal">等待</dd></div><div><dt>声音</dt><dd id="health-sound">等待</dd></div><div><dt>环境</dt><dd id="health-environment">等待</dd></div><div><dt>雷达</dt><dd>不在最终硬件中</dd></div></dl></div>
          <div class="privacy-note"><span aria-hidden="true">✓</span><p><strong>本地隐私保护</strong><span>无 RGB 摄像头，不保存原始语音，热图仅保留最新匿名预览。</span></p></div>
        </aside>
      </section>
    </main>
    <footer class="site-footer"><span>AIoT STUDY SPACE / LOCAL OBSERVABILITY</span><span>SCHEMA 1.0 · ${useMocks ? "DEMO MODE" : "LIVE MODE"}</span></footer>
  </div>`;

function metricCard(id, label, unit, detail, icon) {
  return `<article class="metric-card metric-card--${id}">
    <div class="metric-card__header"><span class="metric-card__icon" aria-hidden="true">${icon}</span><span class="health-label health-label--ok"><span class="health-label__dot"></span>在线</span></div>
    <p class="metric-card__label">${label}</p><p class="metric-card__value" id="${id}-value">--<span>${unit}</span></p>
    <div class="metric-card__chart"><svg class="sparkline" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label="${label}最近趋势"><path id="${id}-area" opacity=".16"></path><path id="${id}-line" fill="none" stroke="currentColor" stroke-width="1.8" vector-effect="non-scaling-stroke"></path></svg></div>
    <p class="metric-card__detail">${detail}</p></article>`;
}

function push(series, value) {
  if (Number.isFinite(value)) series.push(value);
  if (series.length > 24) series.shift();
}

function updateSparkline(id, values) {
  if (!values.length) return;
  const safe = values.length > 1 ? values : [values[0], values[0]];
  const min = Math.min(...safe);
  const range = Math.max(Math.max(...safe) - min, 0.0001);
  const points = safe.map((value, index) => `${(index / (safe.length - 1) * 100).toFixed(2)},${(27 - (value - min) / range * 20).toFixed(2)}`);
  const line = `M ${points.join(" L ")}`;
  document.querySelector(`#${id}-line`).setAttribute("d", line);
  document.querySelector(`#${id}-area`).setAttribute("d", `${line} L 100,32 L 0,32 Z`);
}

function clearSparkline(id) {
  document.querySelector(`#${id}-line`).removeAttribute("d");
  document.querySelector(`#${id}-area`).removeAttribute("d");
}

const healthText = (value) => ({ ok: "运行正常", degraded: "降级运行", offline: "设备离线", not_configured: "未配置" })[value] ?? "未知";

function acceptSnapshot(snapshot) {
  const features = snapshot.room.features;
  const lightRelativePct = features.light_relative_mean == null ? null : features.light_relative_mean * 100;
  const soundRelative = features.sound_peak_max ?? features.sound_rms_mean;
  const soundRelativePct = soundRelative == null ? null : soundRelative * 100;
  push(history.temperature, features.temperature_c);
  push(history.humidity, features.humidity_pct);
  push(history.light, lightRelativePct);
  push(history.sound, soundRelativePct);
  updateMetric("temperature", features.temperature_c, 1, history.temperature);
  updateMetric("humidity", features.humidity_pct, 1, history.humidity);
  updateMetric("light", lightRelativePct, 1, history.light);
  updateMetric("sound", soundRelativePct, 1, history.sound);
  document.querySelector("#room-state").textContent = stateLabels[snapshot.room.room_state] ?? "状态未知";
  document.querySelector("#updated-at").textContent = new Date(snapshot.generated_at).toLocaleTimeString("zh-CN", { hour12: false });
  document.querySelector("#hot-regions").textContent = features.thermal_hot_region_count ?? "--";
  document.querySelector("#health-thermal").textContent = healthText(snapshot.room.sensor_health.thermal);
  document.querySelector("#health-sound").textContent = healthText(snapshot.room.sensor_health.sound);
  document.querySelector("#health-environment").textContent = healthText(snapshot.room.sensor_health.environment);
  document.querySelector("#connection").classList.remove("connection-pill--error");
  document.querySelector("#connection").lastChild.textContent = useMocks ? "模拟数据" : "后端已连接";
  document.querySelector("#error-banner").hidden = true;
  if (snapshot.thermal_preview.available && snapshot.thermal_preview.values) renderThermal(snapshot.thermal_preview.values);
}

function clearLiveReadings(connectionText, message) {
  for (const id of Object.keys(history)) {
    history[id].length = 0;
    updateMetric(id, null, 1, history[id]);
    clearSparkline(id);
  }
  if (thermalAnimation) cancelAnimationFrame(thermalAnimation);
  thermalAnimation = undefined;
  renderedThermal = [];
  const canvas = document.querySelector("#thermal-canvas");
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  document.querySelector("#room-state").textContent = "等待新数据";
  document.querySelector("#updated-at").textContent = "--:--:--";
  document.querySelector("#hot-regions").textContent = "--";
  document.querySelector("#health-thermal").textContent = "等待新数据";
  document.querySelector("#health-sound").textContent = "等待新数据";
  document.querySelector("#health-environment").textContent = "等待新数据";
  document.querySelector("#connection").classList.add("connection-pill--error");
  document.querySelector("#connection").lastChild.textContent = connectionText;
  document.querySelector("#error-text").textContent = message;
  document.querySelector("#error-banner").hidden = false;
}

function updateMetric(id, value, decimals, values) {
  const element = document.querySelector(`#${id}-value`);
  const unit = element.querySelector("span").outerHTML;
  element.innerHTML = `${value == null ? "--" : Number(value).toFixed(decimals)}${unit}`;
  updateSparkline(id, values);
}

const colorStops = [[0,[8,10,22]],[.18,[45,25,86]],[.4,[152,41,81]],[.62,[238,91,54]],[.82,[255,189,70]],[1,[255,248,203]]];
function colorFor(value) {
  let upper = colorStops.findIndex(([point]) => value <= point);
  upper = Math.max(1, upper < 0 ? colorStops.length - 1 : upper);
  const [lowPoint, low] = colorStops[upper - 1];
  const [highPoint, high] = colorStops[upper];
  const amount = (value - lowPoint) / Math.max(highPoint - lowPoint, .0001);
  return low.map((channel, index) => Math.round(channel + (high[index] - channel) * amount));
}

function drawThermal(values) {
  const canvas = document.querySelector("#thermal-canvas");
  const context = canvas.getContext("2d");
  const source = document.createElement("canvas");
  source.width = 32; source.height = 24;
  const sourceContext = source.getContext("2d");
  const image = sourceContext.createImageData(32, 24);
  values.forEach((value, index) => {
    const [red, green, blue] = colorFor(value);
    image.data.set([red, green, blue, 255], index * 4);
  });
  sourceContext.putImageData(image, 0, 0);
  context.imageSmoothingEnabled = smoothing;
  context.imageSmoothingQuality = "high";
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
}

function renderThermal(target) {
  cancelAnimationFrame(thermalAnimation);
  const start = renderedThermal.length === target.length ? [...renderedThermal] : [...target];
  const startedAt = performance.now();
  const animate = (now) => {
    const progress = smoothing ? Math.min(1, (now - startedAt) / 680) : 1;
    const eased = progress * progress * (3 - 2 * progress);
    renderedThermal = target.map((value, index) => start[index] + (value - start[index]) * eased);
    drawThermal(renderedThermal);
    if (progress < 1) thermalAnimation = requestAnimationFrame(animate);
  };
  thermalAnimation = requestAnimationFrame(animate);
}

async function poll() {
  clearTimeout(timer);
  try {
    let snapshot;
    if (useMocks) {
      snapshot = createMockSnapshot(sequence++);
    } else {
      const response = await fetch(`${apiBaseUrl}/api/v1/rooms/${encodeURIComponent(roomId)}/live`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`传感器接口返回 ${response.status}`);
      snapshot = await response.json();
      if (!isLiveSensorSnapshot(snapshot)) throw new Error("传感器接口响应格式不兼容");
      if (!isFreshLiveSensorSnapshot(snapshot)) {
        clearLiveReadings(
          "数据已中断",
          "传感器数据已经过期，已隐藏重启前的缓存值，正在等待树莓派重新上报。"
        );
        return;
      }
    }
    acceptSnapshot(snapshot);
  } catch (error) {
    clearLiveReadings(
      "连接异常",
      `${error.message}。已隐藏旧数据，请检查后端和树莓派后重试。`
    );
  } finally {
    timer = setTimeout(poll, document.hidden ? (useMocks ? 3600 : pollInterval * 4) : (useMocks ? 900 : pollInterval));
  }
}

document.querySelector("#refresh").addEventListener("click", poll);
document.querySelector("#retry").addEventListener("click", poll);
document.querySelector("#smoothing").addEventListener("click", (event) => {
  smoothing = !smoothing;
  event.currentTarget.classList.toggle("is-active", smoothing);
  event.currentTarget.setAttribute("aria-pressed", String(smoothing));
  event.currentTarget.querySelector("span").textContent = smoothing ? "关闭平滑显示" : "开启平滑显示";
  document.querySelector("#thermal-canvas").dataset.smoothing = smoothing ? "on" : "off";
  document.querySelector("#smooth-mode").textContent = smoothing ? "◫ 时间插值 + 空间平滑" : "▦ 原始像素显示";
  if (renderedThermal.length) drawThermal(renderedThermal);
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
poll();
