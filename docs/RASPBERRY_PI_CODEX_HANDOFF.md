# Raspberry Pi 接管与完成操作手册

- 更新时间：2026-07-23，Asia/Singapore
- 目标读者：接手本项目实机工作的新版 Codex
- 工作分支：`module1/hardware-foundation`

## 给新 Codex 的执行指令

你是本项目唯一的主执行 Agent。先完整阅读：

1. `AGENTS.md`
2. `docs/module-specs/00_SHARED_CONTRACT.md`
3. `docs/module-specs/01_SENSOR_EDGE_HARDWARE.md`
4. `edge/hardware/README.md`
5. 本文档

按本文档顺序串行执行。每个阶段先检查现状，再运行命令。不要删除来源不明的文件，不要用模拟数据冒充真实传感器，不要在用户确认实时页面前开始正式采集。

> [!WARNING]
> Pi 上的 `/home/pi/privacy-study-space-advisor` 是部署副本，没有 `.git`。不要在 Pi 上运行 `git pull`、`git reset` 或创建分支。代码只在 Mac 仓库管理，再用不带 `--delete` 的 `rsync` 同步到 Pi。

## 最终目标

完成以下结果后，Raspberry Pi 交接才算结束：

- Mac 后端监听 `0.0.0.0:8000`，Mac 和 Pi 都能访问 `/health`。
- Pi 的 `pssa-dashboard-bridge.service` 为 `enabled/active`，日志持续出现成功窗口，不再连续出现 `dashboard_publish_failed`。
- 页面 `http://127.0.0.1:5173/?mode=api` 显示新时间戳、真实温湿度、相对光照、四位小数实时声音 RMS 和 32×24 热图。
- 用户先检查页面并明确同意开始采集。
- 采集命令同时保持实时页面更新，结束后产生通过验收的会话目录、`.tar.gz` 和 `.tar.gz.sha256`。
- 归档不含 WAV、PCM、MP3、RGB 图片、视频、姓名、学号或原始声音。
- 采集结束后恢复常驻桥接服务。

## 当前生产基线

| 项目 | 当前事实 |
|---|---|
| 控制板 | WeMos D1 R32 / ESP32-D0WD-V3 |
| Pi 串口 | `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`，当前解析为 `/dev/ttyUSB0` |
| 热阵列 | MLX90640，GPIO21 SDA、GPIO22 SCL，3V3，32×24，生产约 2 FPS |
| 声音 | HW-485，3V3 供电，`A0` 直连 GPIO34，`D0` 不接 |
| 光照 | HW-486，3V3，`S` 接 GPIO35，只输出未标定相对值 |
| 温湿度 | HW-507/DHT11，3V3，`S` 接 GPIO27 |
| 雷达 | 已从最终实物移除；契约保留 `radar.health=not_configured` |
| ESP32 到 Pi | USB CH340 串口，460800 baud |
| 热成像档位 | 只使用稳定的 `analytics`/约 2 FPS，不烧录 `smooth` 或 `live_max` |
| 数据隐私 | 不保存原始音频，不使用 RGB 摄像头，不记录个人身份 |

HW-485 当前采用 `3V3 + A0直连GPIO34`。2026-07-22 的现场复测已经读取到非零 RMS，页面显示过 `0.0037%`。如果日后改回 5V 供电，A0 不能直连 ESP32，必须恢复限压方案并先测量电压。

## 2026-07-23 现场快照

这部分是带日期的现场信息，不是永久配置：

| 项目 | 核验结果 |
|---|---|
| Pi mDNS | `raspberrypi.local` |
| Pi 当前 IP | `198.51.100.76` |
| Mac 当前 IP | `198.51.100.106` |
| Pi ED25519 指纹 | `SHA256:<your-privately-verified-host-fingerprint>` |
| SSH 密钥 | `/Users/<user>/.ssh/id_ed25519` |
| Pi 部署目录 | `/home/pi/privacy-study-space-advisor` |
| Pi 用户服务 | 已启用，`Linger=yes` |
| Mac 后端 | `screen` 会话 `pssa-backend`，端口 8000 正在监听 |
| 前端 | 端口 5173 当时未监听，需要重新启动 |
| 当前故障 | Pi 服务仍指向旧后端 `192.0.2.106:8000`，所以持续发布失败 |

IP 会随网络变化。先发现地址，不能直接复制旧 IP。

## 阶段 1：检查 Mac 仓库

在 Mac 执行：

```bash
cd "/Users/<user>/Documents/project aiot/privacy-study-space-advisor"
git status -sb
git fetch origin --prune
git switch module1/hardware-foundation
git pull --ff-only
```

允许保留的已知未跟踪内容：

```text
frontend/tests/e2e.cjs
references/
```

不要删除、移动或整批提交这两项。传感器会话、数据库、虚拟环境和构建目录也不能提交。

## 阶段 2：发现 Pi 并核验主机身份

设置本次操作变量：

```bash
PROJECT_ROOT="/Users/<user>/Documents/project aiot/privacy-study-space-advisor"
PI_KEY="/Users/<user>/.ssh/id_ed25519"
PI_IP="$(dscacheutil -q host -a name raspberrypi.local | awk '/ip_address:/ {print $2; exit}')"
MAC_IF="$(route -n get default | awk '/interface:/ {print $2; exit}')"
MAC_IP="$(ipconfig getifaddr "$MAC_IF")"

printf 'PI_IP=%s\nMAC_IP=%s\n' "$PI_IP" "$MAC_IP"
```

如果 `PI_IP` 为空，先确认 Mac 和 Pi 连接同一网络，再检查：

```bash
arp -a
ping -c 1 raspberrypi.local
```

新 DHCP 地址第一次连接前，比较主机密钥：

```bash
ssh-keyscan -T 5 -t ed25519 "$PI_IP" 2>/dev/null | ssh-keygen -lf -
```

结果必须匹配本机已记录的 Pi 指纹：

```text
SHA256:<your-privately-verified-host-fingerprint>
```

指纹不匹配时停止，不得使用 `StrictHostKeyChecking=no`。指纹匹配后可借用旧地址的已验证记录连接：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  'hostname; hostname -I; uname -m'
```

## 阶段 3：恢复 Mac 后端

先检查已有后端：

```bash
curl -fsS http://127.0.0.1:8000/health | python3 -m json.tool
lsof -nP -iTCP:8000 -sTCP:LISTEN
screen -ls
```

端口没有监听时再启动，不要重复创建多个后端：

```bash
cd "$PROJECT_ROOT/backend"

if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -e '.[dev]'
fi

.venv/bin/alembic upgrade head

screen -dmS pssa-backend zsh -lc \
  "cd '$PROJECT_ROOT/backend' && exec .venv/bin/uvicorn study_space_api.main:app --host 0.0.0.0 --port 8000"

curl -fsS http://127.0.0.1:8000/health | python3 -m json.tool
```

如果 `/api/v1/rooms/room_a` 返回 `ROOM_NOT_FOUND`，运行一次不带 `--reset` 的种子命令：

```bash
cd "$PROJECT_ROOT/backend"
.venv/bin/study-space-api seed-demo
```

禁止默认执行 `seed-demo --reset`，它会删除已有的合成观察和预测记录。

从 Pi 验证 Mac 的局域网地址：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  "curl -fsS http://$MAC_IP:8000/health"
```

失败时先确认后端使用 `--host 0.0.0.0`，再检查 Mac 防火墙和两台设备是否在同一网段。

## 阶段 4：从 Mac 同步部署副本

服务运行时不能覆盖其正在加载的代码。先停止：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  'systemctl --user stop pssa-dashboard-bridge.service'
```

先预览同步范围：

```bash
rsync --dry-run -az \
  --exclude '.venv/' \
  --exclude 'data/' \
  --exclude '.pytest_cache/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'build/' \
  --exclude 'dist/' \
  --exclude '*.egg-info/' \
  -e "ssh -o IdentitiesOnly=yes -o HostKeyAlias=192.0.2.76 -i $PI_KEY" \
  "$PROJECT_ROOT/edge/hardware/" \
  "pi@$PI_IP:/home/pi/privacy-study-space-advisor/edge/hardware/"
```

确认预览不会覆盖 `.venv`、`data/sessions` 或其他未知目录后，去掉 `--dry-run` 再执行一次。不要加入 `--delete`。

同步后更新 Python 安装：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  "cd /home/pi/privacy-study-space-advisor/edge/hardware &&
   .venv/bin/python -m pip install -e '.[hardware,dev]'"
```

如果同步或安装中途失败，先用下面的命令恢复旧服务，再排查失败原因：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  'systemctl --user start pssa-dashboard-bridge.service'
```

## 阶段 5：安装不写死 IP 的 systemd 服务

新单元从 `~/.config/pssa/dashboard-bridge.env` 读取后端地址。第一次安装：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  "install -d -m 700 /home/pi/.config/pssa /home/pi/.config/systemd/user
   test -f /home/pi/.config/pssa/dashboard-bridge.env ||
     install -m 600 \
       /home/pi/privacy-study-space-advisor/edge/hardware/deploy/systemd/dashboard-bridge.env.example \
       /home/pi/.config/pssa/dashboard-bridge.env
   sed -i \
     's#^PSSA_BACKEND_URL=.*#PSSA_BACKEND_URL=http://$MAC_IP:8000#' \
     /home/pi/.config/pssa/dashboard-bridge.env
   install -m 644 \
     /home/pi/privacy-study-space-advisor/edge/hardware/deploy/systemd/pssa-dashboard-bridge.service \
     /home/pi/.config/systemd/user/pssa-dashboard-bridge.service
   systemctl --user daemon-reload
   systemd-analyze --user verify /home/pi/.config/systemd/user/pssa-dashboard-bridge.service
   systemctl --user enable --now pssa-dashboard-bridge.service"
```

后端启用 `EDGE_API_TOKEN` 时，把同名变量加入 Pi 的私有环境文件并保持权限 `600`。不要把真实令牌写入仓库、命令输出或日志。

检查服务和开机恢复：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  "systemctl --user is-enabled pssa-dashboard-bridge.service
   systemctl --user is-active pssa-dashboard-bridge.service
   loginctl show-user pi -p Linger
   journalctl --user -u pssa-dashboard-bridge.service -n 30 --no-pager"
```

成功日志应持续出现 `dashboard_window_complete`，其中 `previews` 和 `observations` 会增长。短暂网络切换可以出现少量失败，但 `dashboard_publish_failed` 不能持续增加。

以后 Mac IP 变化时，只需：

```bash
MAC_IF="$(route -n get default | awk '/interface:/ {print $2; exit}')"
MAC_IP="$(ipconfig getifaddr "$MAC_IF")"

ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP" \
  "sed -i \
     's#^PSSA_BACKEND_URL=.*#PSSA_BACKEND_URL=http://$MAC_IP:8000#' \
     /home/pi/.config/pssa/dashboard-bridge.env
   systemctl --user restart pssa-dashboard-bridge.service"
```

## 阶段 6：运行标准传感器检查

串口只能有一个消费者。探测前停止常驻桥接，结束后一定恢复：

```bash
ssh \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP"
```

进入 Pi 后执行：

```bash
set -e
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0

systemctl --user stop pssa-dashboard-bridge.service
restore_bridge() {
  systemctl --user start pssa-dashboard-bridge.service
}
trap restore_bridge EXIT INT TERM

PYTHONPATH=src .venv/bin/python scripts/probe_sensors.py \
  --config config/esp32-hub.example.yaml

restore_bridge
trap - EXIT INT TERM
```

标准结果：

- `thermal`、`sound`、`light`、`climate` 均为 `connected=true`，健康状态为 `ok`。
- 不应构建第五个真实雷达传感器。共享输出中的 radar 为 `not_configured`。
- MLX90640 返回 768 个有限温度值，但探测日志不打印完整矩阵。
- HW-486 返回 ADC 相对值，`light_lux` 保持 `null`。
- HW-485 安静时可以是精确 0。对模块说话或拍手后必须至少出现一次非零窗口。
- DHT11 温湿度必须是有限值。

如果命令失败，退出 shell 前确认 trap 已恢复服务：

```bash
systemctl --user is-active pssa-dashboard-bridge.service
```

## 阶段 7：启动并检查实时页面

在 Mac 启动 React/Vite 前端：

```bash
cd "$PROJECT_ROOT/frontend"

if [ ! -d node_modules ]; then
  TASK_NPM_CACHE="$(mktemp -d)"
  npm_config_cache="$TASK_NPM_CACHE" npm ci
fi

if ! lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null; then
  screen -dmS pssa-frontend zsh -lc \
    "cd '$PROJECT_ROOT/frontend' && exec npm run dev"
fi
```

打开：

```text
http://127.0.0.1:5173/?mode=api
```

同时检查 API：

```bash
curl -fsS http://127.0.0.1:8000/api/v1/rooms/room_a/live |
  jq '{
    generated_at,
    observed_at: .room.observed_at,
    is_stale: .room.is_stale,
    features: .room.features,
    sensor_health: .room.sensor_health,
    warnings: .room.warnings,
    thermal_available: .thermal_preview.available,
    sound_preview: .sound_preview
  }'

curl -fsS http://127.0.0.1:8000/api/v1/rooms/room_a/sound-preview |
  jq .
```

验收页面时确认：

- 连接状态是“后端已连接”。
- `observed_at` 持续前进，`is_stale=false`。
- 热阵列、声音、环境显示正常。
- 声音卡片标记“当前窗口 RMS（实时）”，显示四位小数，不显示 8 秒释放峰值。
- 光照使用相对百分比，不冒充 lux。
- 热图持续更新；页面插值可以是 60 FPS，但真实热采样仍约 2 FPS。

> [!IMPORTANT]
> 到这里暂停并让用户检查页面。只有用户明确说“开始采集”后，才能进入下一阶段。

## 阶段 8：边展示边采集并自动打包

`stream_dashboard.py --duration` 会占用同一 ESP32 串口，所以先停止常驻服务。该命令在采集期间继续向网页后端发送数据，结束后自动执行会话验收并生成归档。

在 Pi 执行：

```bash
set -e
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
MAC_BACKEND_URL="$(
  sed -n 's/^PSSA_BACKEND_URL=//p' \
    /home/pi/.config/pssa/dashboard-bridge.env
)"
test -n "$MAC_BACKEND_URL"

systemctl --user stop pssa-dashboard-bridge.service
restore_bridge() {
  systemctl --user start pssa-dashboard-bridge.service
}
trap restore_bridge EXIT INT TERM

PYTHONPATH=src .venv/bin/python scripts/stream_dashboard.py \
  --config config/esp32-hub.example.yaml \
  --backend-url "$MAC_BACKEND_URL" \
  --duration 300 \
  --scenario unlabeled_relative_training \
  --participant-range 1-4 \
  --notes "HW-485 and HW-486 collected as uncalibrated relative values"

restore_bridge
trap - EXIT INT TERM
```

该命令直接复用常驻服务已经验证过的后端地址。不要在备注中写姓名、学号或其他身份信息。

成功输出必须同时满足：

```text
window_count > 0
validation.valid = true
validation.errors = []
archive_path 不是 null
archive_sha256 不是 null
raw_audio_persisted = false
light_lux_calibrated = false
sound_db_calibrated = false
```

会话目录包含：

```text
data/sessions/<session_id>/
├── session.json
├── windows.jsonl
├── relative_features.jsonl
├── thermal/
│   └── <window_id>.npz
└── checksums.json
```

同级还会生成：

```text
<session_id>.tar.gz
<session_id>.tar.gz.sha256
```

采集结束后再次检查：

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_session.py \
  "data/sessions/<session_id>"

(cd data/sessions && sha256sum -c "<session_id>.tar.gz.sha256")
systemctl --user is-active pssa-dashboard-bridge.service
```

## 阶段 9：把数据包复制到 Mac

在 Mac 建立 Git 仓库外的导出目录：

```bash
EXPORT_DIR="/Users/<user>/Documents/project aiot/sensor-session-exports"
mkdir -p "$EXPORT_DIR"
```

复制归档和校验文件：

```bash
scp \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP:/home/pi/privacy-study-space-advisor/edge/hardware/data/sessions/<session_id>.tar.gz" \
  "$EXPORT_DIR/"

scp \
  -o IdentitiesOnly=yes \
  -o HostKeyAlias=192.0.2.76 \
  -i "$PI_KEY" \
  "pi@$PI_IP:/home/pi/privacy-study-space-advisor/edge/hardware/data/sessions/<session_id>.tar.gz.sha256" \
  "$EXPORT_DIR/"
```

在导出目录验证：

```bash
cd "$EXPORT_DIR"
shasum -a 256 -c "<session_id>.tar.gz.sha256"
tar -tzf "<session_id>.tar.gz" | sed -n '1,40p'
```

数据归档不能加入 Git。只有匿名、足够小且经过人工审查的摘要 fixture 才能进入 `shared/fixtures/`。

## 常见故障

### Pi 能 SSH，但页面显示连接异常

按顺序检查：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS "http://$MAC_IP:8000/health"
ssh -o IdentitiesOnly=yes -o HostKeyAlias=192.0.2.76 -i "$PI_KEY" \
  "pi@$PI_IP" "curl -fsS http://$MAC_IP:8000/health"
```

Pi 能访问 Mac 后端后，再检查环境文件和服务日志。不要用旧数据库值填充页面。

### 服务 active，但 `dashboard_publish_failed` 持续增长

最常见原因是 Mac IP 已变化。检查：

```bash
ipconfig getifaddr en0
ssh -o IdentitiesOnly=yes -o HostKeyAlias=192.0.2.76 -i "$PI_KEY" \
  "pi@$PI_IP" "grep '^PSSA_BACKEND_URL=' /home/pi/.config/pssa/dashboard-bridge.env"
```

更新环境文件并重启服务，不需要改 Python 代码。

### 串口被占用

常驻桥接、`probe_sensors.py`、`live_thermal.py` 和采集命令不能并行读取 ESP32：

```bash
systemctl --user stop pssa-dashboard-bridge.service
lsof /dev/ttyUSB0
```

只停止已经确认属于本项目的进程。测试结束后恢复服务。

### 声音仍显示 0

先核对当前接线：

```text
HW-485 +   -> ESP32 3V3
HW-485 G   -> ESP32 GND
HW-485 A0  -> ESP32 GPIO34
HW-485 D0  -> 不接
```

安静窗口可以是 0。对麦克风持续说话或拍手，再直接查询 `sound-preview`。不要加固定噪声、伪造 dB 或恢复历史峰值缓存。

### 热图消失

先检查供电、I²C 接线、服务日志和 `thermal_preview.available`。不要先烧录高帧率档位。当前生产基线是已实测稳定的约 2 FPS。

## 禁止操作

- 不运行 `git reset --hard`、`git clean -fd` 或 `rsync --delete`。
- 不删除旧会话，除非用户明确指定准确目录并确认删除。
- 不提交 `references/`、`frontend/tests/e2e.cjs`、数据库、虚拟环境或采集归档。
- 不重新接入 LD2450。
- 不把相对光照写成 lux，不把相对声音写成 dB。
- 不保存原始声音或 RGB 图像。
- 不在没有重新完成实机稳定性测试时把热成像提高到 16/32 FPS。
- 不让两个进程同时读取 ESP32 串口。

## 最终交付记录

新 Codex 完成操作后，应向用户报告：

- Mac 与 Pi 的实际 IP。
- Pi 主机指纹是否匹配。
- 部署了哪些本地提交。
- 四个真实传感器的探测结果。
- 页面实际显示与最新时间戳。
- 会话 ID、窗口数、`validation.valid`、归档路径和 SHA-256。
- 常驻服务是否恢复为 `enabled/active`。
- 未解决问题，尤其是未标定的 HW-486 lux 和 HW-485 dB。

相关证据与边界见：

- `edge/hardware/HARDWARE_SMOKE_TEST.md`
- `edge/hardware/MODULE1_HANDOFF.md`
- `docs/CURRENT_STATUS.md`
- `docs/DECISIONS.md`
