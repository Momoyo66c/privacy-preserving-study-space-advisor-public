# 模块 1：传感器与边缘硬件

本模块在 Raspberry Pi 5 或普通开发电脑上采集并编排热阵列、声音强度、光照和温湿度数据。每个 5 至 10 秒窗口都会转换为共享 `sensor_window` 契约，供模块 2 直接读取。最终生产基线不安装 LD2450，契约中的 `radar` 保留为兼容字段并输出 `not_configured`。

模块遵守以下隐私边界：

- 不采集 RGB 图像。
- 声音只在内存中计算 RMS、标准差和峰值，不保存 WAV、PCM 或其他原始音频。
- 可选雷达兼容驱动的目标 ID 只在当前窗口内有效，不用于跨窗口追踪。
- 完整热阵列只允许写入本地离线训练会话，不进入普通后端负载或日志。
- 缺失数据使用 `health`、`warnings` 和 `null` 表达，不用正常数值伪装。

共享契约与实现规格分别见：

- `../../docs/module-specs/00_SHARED_CONTRACT.md`
- `../../docs/module-specs/01_SENSOR_EDGE_HARDWARE.md`

## 快速运行模拟器

需要 Python 3.11 或更高版本。

```bash
cd edge/hardware
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/run_simulator.py \
  --config config/example.yaml \
  --scenario quiet_study_recommended \
  --windows 2
```

命令会打印两个符合共享 JSON Schema 的窗口。默认使用确定性手动时钟，测试或演示不需要等待真实的 5 秒；加入 `--realtime` 可按真实时间采样。

## 已实现内容

| 部分 | 实现 |
|---|---|
| 驱动接口 | `SensorDriver` Protocol 与带重试、健康状态、幂等关闭的基类 |
| 热阵列 | MLX90640 32 × 24 帧读取、长度/NaN/温度范围校验 |
| 雷达兼容 | HLK-LD2450 解析器和模拟测试保留；生产配置禁用，不安装实物 |
| 声音 | 短时内存缓冲区的 RMS、标准差和峰值统计；支持带环境底噪余量的 HW-485 相对标定 |
| 环境 | 直连 BH1750/AHTx0；Sensor Hub 模式支持 HW-486 两点相对标定与 DHT11 |
| 窗口 | 非重叠 5–10 秒窗口、样本计数、完整度和降级警告 |
| 模拟器 | 7 种场景、固定随机种子、间歇故障 |
| 本地采集 | JSONL 窗口、压缩 NPZ 热帧、SHA-256 校验和 |
| 状态输出 | 日志、GPIO RGB LED 与 micro:bit 串口适配器 |

目录结构：

```text
edge/hardware/
├── config/
│   ├── example.yaml
│   └── real.example.yaml
├── scripts/
│   ├── collect_session.py
│   ├── live_thermal.py
│   ├── probe_sensors.py
│   └── run_simulator.py
├── src/study_space_hardware/
│   ├── actuation/
│   ├── drivers/
│   ├── simulators/
│   ├── bootstrap.py
│   ├── config.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── storage.py
│   └── windowing.py
└── tests/
```

## 配置

`config/example.yaml` 默认启用模拟器，适合开发和 CI。`config/real.example.yaml`
保留 Raspberry Pi 四传感器直连兼容模式；当前实物使用 `config/esp32-hub.example.yaml`，
由 ESP32 汇聚 MLX90640、HW-485、HW-486 和 DHT11。两份真实配置都明确设置 `radar.enabled=false`。

HW-485 无可靠响应时，使用 `config/esp32-hub-windows-mic.example.yaml`：
MLX90640、HW-486 和 DHT11 仍由 ESP32 采集，只有 `sound` 驱动改为接收
Windows 麦克风产生的隐私摘要。公共 `sensor_window` 契约不变。

所有采集类 CLI 都要求显式传入 `--config`。这样从 wheel 安装后不会依赖源码目录中的隐式路径，也能在日志和复现实验时明确记录所用配置。

主要字段：

| 字段 | 含义 |
|---|---|
| `room_id`、`device_id` | 房间与设备的非个人标识 |
| `window_seconds` | 非重叠窗口长度，只允许 5–10 秒 |
| `sensors.<name>.enabled` | 是否启用该传感器 |
| `sample_rate_hz` | 每秒期望样本数 |
| `max_retries` | 单次读取的额外重试次数 |
| `offline_threshold` | 连续失败达到该值后标记为 offline |
| `storage.data_dir` | 本地离线会话目录 |
| `simulator.scenario` | 模拟场景 |
| `simulator.random_seed` | 可复现随机种子 |
| `actuation.device` | `log`、`gpio_rgb` 或 `microbit` |

`${ENV_NAME}` 形式的配置值会从环境变量读取。示例配置不包含密钥或机器专用绝对路径。

支持的模拟场景：

- `empty_or_low_activity`
- `quiet_study_recommended`
- `discussion_allowed`
- `not_recommended_noisy_or_crowded`
- `degraded_thermal`
- `degraded_radar`
- `intermittent_failure`

## Raspberry Pi 5 直连兼容模式接线

以下表格仅用于保留的直连驱动，不是当前 ESP32 Sensor Hub 接线。当前实物的
传感器全部接 ESP32，Pi 只通过 USB 串口连接 ESP32；具体引脚与供电要求见
`firmware/esp32_sensor_hub/README.md`。接线前断电，并确认外设电压与模块版本。

| 设备 | Raspberry Pi 连接 | 说明 |
|---|---|---|
| MLX90640 | 3.3V、GND、SDA/BCM2、SCL/BCM3 | I2C，常见地址 `0x33`（YAML 十进制为 `51`） |
| BH1750 | 3.3V、GND、SDA/BCM2、SCL/BCM3 | 与 MLX90640 共用 I2C 总线 |
| AHT20/AHTx0 | 3.3V、GND、SDA/BCM2、SCL/BCM3 | 与其他 I2C 设备地址不得冲突 |
| USB 麦克风 | USB | 驱动只读取短缓冲区并立即统计 |
| 共阴 RGB LED | BCM17/27/22 经限流电阻连接 R/G/B，公共端接 GND | GPIO 编号可在 `actuation.options` 中修改 |

在 Raspberry Pi OS 中启用 I2C，并确认设备：

```bash
sudo raspi-config
i2cdetect -y 1
ls -l /dev/ttyUSB* /dev/ttyACM*
```

## 运行真实驱动

先安装 PortAudio、I²C 工具和 Pi 5 `lgpio` 的构建依赖，再安装 Python
硬件依赖。以下命令已在 64 位 Raspberry Pi OS（Debian Trixie）验证：

```bash
sudo apt install i2c-tools portaudio19-dev liblgpio-dev swig
cd edge/hardware
source .venv/bin/activate
python -m pip install -e '.[hardware,dev]'
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
python scripts/probe_sensors.py --config config/esp32-hub.example.yaml
```

上面是当前生产连接。保留的 Raspberry Pi 直连模式使用 `config/real.example.yaml`，同样不要设置 `RADAR_PORT`。

在 64 位 Raspberry Pi OS 上，`hardware` extra 会同时安装 Pi 5 所需的
`lgpio` 后端。安装后可先运行 `python -c "import board, lgpio"`，确认
Blinka 与 GPIO 后端均可导入，再探测真实传感器。

`probe_sensors.py` 对每个驱动输出连接状态、最近一次安全摘要和健康状态。它不会打印完整热矩阵或保存声音缓冲区。

如果使用 micro:bit，将 `actuation.device` 改为 `microbit`，并在 `actuation.options.port` 设置串口。GPIO 模式需要在选项中提供 `red_pin`、`green_pin` 和 `blue_pin`。

### HW-486 两点相对标定

没有参考照度计时，可以把当前 HW-486 做成设备专属的相对 0–1 标尺。暗点与
亮点均取 12 个 ADC 样本的中位数，程序自动识别 ADC 随光照增加还是降低，
并把区间线性映射、截断到 0–1。暗亮中位数必须至少相差 64 ADC count。

该过程只改善 `light_relative_mean`，**不会生成 lux**；共享负载中的
`light_lux` 继续为 `null`，并保留 `hw486_uncalibrated_light_proxy` 警告。
标定文件只保存汇总统计，不保存逐样本数据。

标定分两次执行，便于每一步先确认物理环境。树莓派串口只允许一个读取者，
所以每次采样前停止展示桥，采样完成后立即恢复：

```bash
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
mkdir -p ~/.config/pssa/calibration

# 第一步：完全遮住 HW-486 光敏元件后执行，约 12 秒
systemctl --user stop pssa-dashboard-bridge.service
PYTHONPATH=src .venv/bin/python scripts/calibrate_light.py capture-dark \
  --config config/esp32-hub.example.yaml \
  --output ~/.config/pssa/calibration/hw486-dark-staging.json
systemctl --user start pssa-dashboard-bridge.service

# 第二步：移除遮挡并打开预期使用的最亮室内照明后执行，约 12 秒
systemctl --user stop pssa-dashboard-bridge.service
PYTHONPATH=src .venv/bin/python scripts/calibrate_light.py capture-bright \
  --config config/esp32-hub.example.yaml \
  --staging ~/.config/pssa/calibration/hw486-dark-staging.json \
  --output ~/.config/pssa/calibration/hw486-relative.json
systemctl --user start pssa-dashboard-bridge.service

# 只读校验；输出必须明确 calibrated_lux=false
PYTHONPATH=src .venv/bin/python scripts/calibrate_light.py status \
  --profile ~/.config/pssa/calibration/hw486-relative.json \
  --device-id pi5-a
```

校验通过后，在权限为 600 的
`~/.config/pssa/dashboard-bridge.env` 中加入：

```bash
HW486_RELATIVE_CALIBRATION_PATH=/home/pi/.config/pssa/calibration/hw486-relative.json
```

然后执行 `systemctl --user restart pssa-dashboard-bridge.service`。配置也可使用
`sensors.light.options.relative_calibration_path` 指定同一路径。启动时会严格
校验 schema、传感器型号、设备 ID、暗亮间距和派生方向；文件缺失、被篡改或
属于其他设备时会拒绝启用，删除上述环境变量并重启即可回退到原始 ADC 比例。

### HW-485 带环境余量的相对标定

没有声级计时，HW-485 只能建立当前设备和安装位置专属的相对 0–1 标尺，
不能生成 dB。安静锚点不要求绝对静音：程序采集 32 个统计窗口，以当前环境
RMS/峰值的第 95 百分位作为底噪上界；参考锚点使用最高 10% 样本的中位数，
且至少取 5 个高位样本，避免单次尖峰决定上限。最终零点再向上移动“底噪至参考声跨度”的 10%，给
无法消除的环境声留出余量。

每次命令先丢弃 8 个有效预热样本，容忍偶发串口超时，只保存 RMS/峰值汇总，
不保存音频、ADC 序列或逐窗口值。先执行无需人员配合且不保存文件的预检：

```bash
systemctl --user stop pssa-dashboard-bridge.service
PYTHONPATH=src .venv/bin/python scripts/calibrate_sound.py preflight \
  --config config/esp32-hub.example.yaml
systemctl --user start pssa-dashboard-bridge.service
```

预检和完整测试通过后，分两阶段建立测试 profile：

```bash
# 阶段一：暂停说话和触碰桌面即可；环境不必绝对安静，实机约 40 秒
systemctl --user stop pssa-dashboard-bridge.service
PYTHONPATH=src .venv/bin/python scripts/calibrate_sound.py capture-quiet \
  --config config/esp32-hub.example.yaml \
  --output ~/.config/pssa/calibration/hw485-quiet-staging.json
systemctl --user start pssa-dashboard-bridge.service

# 阶段二：距麦克风约 30–50 cm，持续以正常交谈音量重复固定短句，实机约 40 秒
systemctl --user stop pssa-dashboard-bridge.service
PYTHONPATH=src .venv/bin/python scripts/calibrate_sound.py capture-reference \
  --config config/esp32-hub.example.yaml \
  --staging ~/.config/pssa/calibration/hw485-quiet-staging.json \
  --output ~/.config/pssa/calibration/hw485-relative-trial.json \
  --noise-margin-fraction 0.10
systemctl --user start pssa-dashboard-bridge.service

PYTHONPATH=src .venv/bin/python scripts/calibrate_sound.py status \
  --profile ~/.config/pssa/calibration/hw485-relative-trial.json \
  --device-id pi5-a
```

RMS 和峰值的参考高位都必须明显高于环境底噪，否则拒绝生成 profile，不能
用无响应或纯底噪数据伪造成功。测试 profile 通过以下环境变量启用：

```bash
HW485_RELATIVE_CALIBRATION_PATH=/home/pi/.config/pssa/calibration/hw485-relative-trial.json
```

启用后，展示桥的 `sound_rms_mean`、`sound_peak_max` 和内存态声音预览使用
标定后的相对值，同时驱动保留传感器归一化统计用于诊断，并明确输出
`calibrated_db=false`、`hw485_not_calibrated_db`。删除环境变量并重启服务
即可无损回退到原有对数相对曲线。

### HW-485 高频采样响应诊断

在标定失败或只观察到瞬时峰值时，先运行隔离诊断，不应立即放宽标定门槛。
生产固件已经在 ESP32 内对 GPIO34 执行约 4 kHz、每窗 400 点的短时 ADC
采样，并且只上传 RMS、中心化标准差和峰值。诊断命令复用这些高频窗口，
不刷写固件、不改变引脚、协议或其他传感器任务。

诊断分为安静环境与持续参考声两次采集。文件只包含各指标的最小值、中位数、
p95、最大值、非零窗口数、窗口数及固件采样点总数；不包含音频、ADC 序列或
逐窗口值。比较结果区分：

- `sustained_ac_response_detected`：中心化标准差和峰值都持续响应，可继续做
  相对教室噪声方案；
- `peak_or_impulse_only_response`：只能检测拍手等瞬态，不适合稳定 RMS 标定；
- `dc_or_envelope_response_without_ac_variation`：只看到直流或包络变化，需要
  检查采样语义；
- `no_reliable_sound_response`：没有可靠声音响应。

树莓派串口只允许一个读取者。以下命令用 shell trap 保证无论采集成功还是
失败都会恢复展示桥；开始前后还应分别检查 MLX90640、HW-486 和 DHT11：

```bash
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
mkdir -p ~/.config/pssa/diagnostics

# 第一步：保持正常环境安静；约 40 秒，只保存不可重建声音的汇总
systemctl --user stop pssa-dashboard-bridge.service
trap 'systemctl --user start pssa-dashboard-bridge.service' EXIT
PYTHONPATH=src .venv/bin/python scripts/diagnose_sound.py capture \
  --config config/esp32-hub.example.yaml \
  --label quiet \
  --output ~/.config/pssa/diagnostics/hw485-quiet.json
systemctl --user start pssa-dashboard-bridge.service
trap - EXIT

# 第二步：播放或制造持续、稳定的参考声；同样不保存逐窗口值
systemctl --user stop pssa-dashboard-bridge.service
trap 'systemctl --user start pssa-dashboard-bridge.service' EXIT
PYTHONPATH=src .venv/bin/python scripts/diagnose_sound.py capture \
  --config config/esp32-hub.example.yaml \
  --label reference \
  --output ~/.config/pssa/diagnostics/hw485-reference.json
systemctl --user start pssa-dashboard-bridge.service
trap - EXIT

PYTHONPATH=src .venv/bin/python scripts/diagnose_sound.py compare \
  --quiet ~/.config/pssa/diagnostics/hw485-quiet.json \
  --reference ~/.config/pssa/diagnostics/hw485-reference.json \
  --device-id pi5-a
```

诊断不会启用 `HW485_RELATIVE_CALIBRATION_PATH`。若任一其他传感器在诊断后
不再为预期健康状态，立即停止后续声音操作、重启展示桥并使用诊断前的配置；
由于本流程不刷写 ESP32 或修改服务环境文件，不需要更改其他传感器配置。

### Windows 麦克风替代 HW-485

该模式适合 HW-485 无可靠响应且暂时无法更换传感器的演示。Windows 程序每次
只在内存读取 1 秒、16 kHz、单声道缓冲区，立即计算 RMS、标准差和峰值，
随后释放缓冲区。发送负载没有 PCM、WAV、逐样本数组或可恢复语音；接收端也
只在内存保留最新摘要。输出是相对归一化振幅，固定声明
`calibrated_db=false`，不得解释为 dBA。

接收端集成在模块 1 的采样进程中，并强制只监听 Pi 的 `127.0.0.1:8766`。
Windows 必须使用 SSH 本地转发访问，禁止把监听地址改为 `0.0.0.0`。负载还
必须通过随机 Bearer token、房间/设备 ID、UUID 幂等键、0–1 有限值、最大
4 KiB 正文和时间新鲜度校验。超过 4 秒的摘要不进入窗口；8 秒没有新摘要时
声音健康状态变为 `offline`，其他三个传感器继续采集。

Pi 的 `~/.config/pssa/dashboard-bridge.env` 使用权限 600，并加入：

```bash
PSSA_SENSOR_CONFIG=config/esp32-hub-windows-mic.example.yaml
PSSA_REMOTE_SOUND_TOKEN=<32-byte-random-secret>
```

同一个 token 只放入当前 Windows 进程环境，不写入仓库。PowerShell 可生成：

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:PSSA_REMOTE_SOUND_TOKEN = [Convert]::ToBase64String($bytes)
```

更新 Pi 服务配置后重载并启动：

```bash
systemctl --user daemon-reload
systemctl --user restart pssa-dashboard-bridge.service
systemctl --user status pssa-dashboard-bridge.service --no-pager
```

在 Windows 第一个 PowerShell 窗口建立加密隧道：

```powershell
ssh -N -L 18766:127.0.0.1:8766 pi@PI_IP
```

第二个窗口安装最小依赖、只读列出输入设备，然后再启动采集：

```powershell
cd edge\hardware
python -m pip install -e ".[remote-sound]"
python scripts\stream_remote_sound.py --list-devices
python scripts\stream_remote_sound.py `
  --url http://127.0.0.1:18766/v1/sound-features `
  --room-id room_a `
  --device-id windows-laptop-mic
```

`--list-devices` 不打开麦克风。正式命令第一次运行时 Windows 可能要求允许
“桌面应用访问麦克风”；拒绝权限或关闭代理后，系统应在 8 秒内把声音标为
`offline`，不得复用旧摘要。后端 Observation 每 5 秒发布一次，因此页面最迟
约 13 秒显示 `offline` 和空声音值。笔记本必须与传感器留在同一教室且位置
固定；Windows 自动增益、降噪或移动设备会改变相对标尺。

首次部署可用有限窗口诊断确认麦克风确实响应。命令只在内存累计
RMS/标准差/峰值，并在结束时打印最小值、中位数、p95 和最大值，不写文件：

```powershell
python scripts\stream_remote_sound.py `
  --device 1 `
  --windows 10 `
  --diagnostic-summary
```

Pi 对收到的原始归一化 RMS/峰值应用固定的相对对数曲线，使普通声音变化在
0–1 显示上可见；原始归一化值只保留在当前内存样本中用于诊断。该曲线没有
参考声级计，仍然不是 dB，也不具备跨设备可比性。

### 连续刷新 MLX90640 热图

本地诊断工具持续读取热阵列，并通过只监听树莓派回环地址的网页显示
32 × 24 实时热图。进程只在内存中保留最新一帧，不写热图文件、不上传
后端，也不改变正式采样窗口。

在树莓派启动：

```bash
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
PYTHONPATH=src .venv/bin/python scripts/live_thermal.py \
  --config config/esp32-hub.example.yaml
```

默认地址为 `127.0.0.1:8765`。在 Mac 建立 SSH 隧道：

```bash
ssh -N -L 8765:127.0.0.1:8765 \
  -i /Users/<user>/.ssh/id_ed25519 \
  pi@192.0.2.76
```

然后在 Mac 浏览器打开 `http://127.0.0.1:8765`。网页以二进制长轮询读取
最新帧，默认按 60 FPS 在相邻真实帧之间做时间插值；“平滑显示”同时控制
画布缩放和平滑过渡。页面会显示真实采集 FPS 和当前帧龄，渲染 FPS 不代表
传感器采样率。兼容诊断用的 JSON `/frame` 端点仍保留，`/health` 不包含
温度矩阵。按 `Ctrl-C` 停止；不要在没有访问控制的网络上把 `--host` 改为
`0.0.0.0`。

### 接入现有数据展示前后端

树莓派桥接程序直接复用后端已有的 observation 和 thermal-preview 写接口。热预览按生产配置约 2 FPS 更新；温湿度、声音、热区数量和健康状态每 5 秒提交一次。桥接程序不做模块 02 推理，因此房间状态保持 `unknown`。

```bash
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
PYTHONPATH=src .venv/bin/python scripts/stream_dashboard.py \
  --config config/esp32-hub.example.yaml \
  --backend-url http://MAC_LAN_IP:8000
```

后端启用 `EDGE_API_TOKEN` 时，在 Pi 上设置同名环境变量。HW-486 无论是否完成
相对标定，桥接程序都坚持发送 `light_lux=null`；页面显示 `-- lx` 属于预期
行为。相对标定只改变 0–1 光照条或百分比。

长期运行使用 `deploy/systemd/pssa-dashboard-bridge.service`。单元从 Pi 的
`~/.config/pssa/dashboard-bridge.env` 读取 `PSSA_BACKEND_URL`，Mac DHCP 地址
变化时只更新该环境文件并重启服务，不修改 Python 源码。完整安装、恢复、
页面确认和边展示边采集流程见
[`../../docs/RASPBERRY_PI_CODEX_HANDOFF.md`](../../docs/RASPBERRY_PI_CODEX_HANDOFF.md)。

## ESP32 烧录与串口检查

仓库提供最小 ESP32 串口烟雾固件，用于确认树莓派能够识别、编译、烧录和读取开发板。固件不采集传感器数据，也不连接网络。操作命令和成功输出见 [`firmware/README.md`](firmware/README.md)。

烧录前必须读取芯片型号，并核对 `/dev/serial/by-id/`。`/dev/ttyUSB0` 只是动态设备名，不能代替芯片和稳定路径校验。

## 离线采集

模拟采集示例：

```bash
python scripts/collect_session.py \
  --config config/example.yaml \
  --room room_a \
  --scenario quiet_study_recommended \
  --duration 300 \
  --participant-range 1-4 \
  --known-anomaly "thermal sensor warm-up dropped one frame"
```

真实 ESP32 Hub 采集时改用 `config/esp32-hub.example.yaml` 并加入 `--realtime`。输出结构：

```text
data/sessions/<session_id>/
├── session.json
├── windows.jsonl
├── thermal/
│   └── <window_id>.npz
└── checksums.json
```

`windows.jsonl` 可直接交给模块 2。热帧通过 `thermal.frames_ref` 指向同一会话内的本地 NPZ 文件。`checksums.json` 保存每个文件的 SHA-256。会话元数据明确记录 `raw_audio_persisted=false`，且不包含姓名或学号。

`--known-anomaly` 用于记录不含个人身份的已知采集异常，可以重复传入。内容会按条目写入 `session.json` 的 `known_anomalies` 数组；没有已知异常时保存空数组。

### 验证离线会话

采集结束后运行只读验收工具：

```bash
python scripts/verify_session.py data/sessions/SESSION_ID
# 安装后的等价入口：
study-space-verify-session data/sessions/SESSION_ID
```

验收工具检查 `session.json` 隐私字段、`windows.jsonl` 共享 Schema、文件 SHA-256、热帧 NPZ 的 `(N, 768)` 形状和窗口帧数，同时拒绝符号链接、未登记文件以及音频、RGB 图像和视频扩展名。成功时输出 `"valid": true` 并返回 0；任何错误都会列在 `errors` 中并返回 1。工具不会修复或改写会话。

模块 2 不需要重复实现本地 URI、校验和和 NPZ 解析。读取前使用同一严格验收边界：

```python
from study_space_hardware.session_reader import SessionReader

for item in SessionReader("data/sessions/SESSION_ID"):
    sensor_window = item.payload
    thermal_frames = item.thermal_frames
```

读取器先验证完整会话，再按 `windows.jsonl` 顺序流式加载窗口。热阵列为只读
`float32`、形状 `(N, 768)`；没有热帧时为 `None`。元数据、窗口房间/设备、
UTC 时间范围、非重叠顺序、NPZ 有限值和温度范围不一致时会拒绝整个会话。

### 仓库内真实短时样本

`sample_data/real_classroom_v1/` 包含 2026-07-23 采集的四份去身份化真实
会话：空教室、一人安静学习、两人正常讨论和两人持续嘈杂活动，共36个五秒
窗口，覆盖全部四个训练标签。数据包含完整会话元数据、相对声音/光照摘要和
本地训练用 MLX90640 NPZ，不含原始音频、RGB 图像、姓名或学号。

数据位置、逐窗口标签、格式、校验命令、模块 2 特征流水线以及当前规则基线
重标定方法见 [`REAL_DATASET_GUIDE.md`](REAL_DATASET_GUIDE.md)。训练可行性、
信号效果、数据泄漏风险和虚拟数据建议见
[`MODEL_TRAINING_READINESS_REPORT.md`](MODEL_TRAINING_READINESS_REPORT.md)。
四个标签各只有一个独立会话，仍不能单独作为模型准确率声明。

## 窗口契约

JSON Schema 位于 `../../shared/contracts/sensor_window.schema.json`，示例位于 `../../shared/fixtures/`。

默认 5 秒窗口的期望样本数为：

- 热阵列：10 帧（2 Hz）
- 雷达：未配置，0 样本；共享字段固定输出 `not_configured`
- 声音：20 个统计样本（4 Hz）
- 光照：5 个样本（1 Hz）
- 温湿度：5 个样本（1 Hz）

`quality.completeness` 是所有已启用传感器有效样本数与期望样本数之比，范围为 0–1。未配置的雷达不计入分母。单个传感器故障不会中止窗口；热阵列在无雷达备援时离线，窗口会明确标记不可用于正常推理。兼容驱动产生的雷达目标仍使用窗口局部 ID。

## 状态输出

状态到颜色的固定映射如下：

| 状态 | 输出 |
|---|---|
| `empty_or_low_activity` | 蓝 |
| `quiet_study_recommended` | 绿 |
| `discussion_allowed` | 黄 |
| `not_recommended_noisy_or_crowded` | 红 |
| `unknown` 或严重降级 | 白色闪烁 |

默认 `actuation.device: log`，无硬件时只记录目标颜色。蜂鸣器默认关闭；提交的配置不允许启用蜂鸣器。

## 测试

```bash
cd edge/hardware
source .venv/bin/activate
python -m pytest
python -m compileall -q src scripts
```

也可以在仓库根目录直接运行：

```bash
edge/hardware/.venv/bin/python -m pytest -q edge/hardware/tests
edge/hardware/.venv/bin/python -m compileall -q \
  edge/hardware/src edge/hardware/scripts
```

测试覆盖驱动错误隔离、损坏帧、LD2450 的 100 组确定性随机分块/噪声/粘包压力、超时恢复、MLX90640 非有限值与越界温度、声音不落盘、窗口完整度、确定性模拟、共享 JSON Schema、离线会话和两分钟模拟集成运行。

`.github/workflows/module1-ci.yml` 使用单个顺序作业执行完整测试、80% 总覆盖率门禁、编译检查和 wheel 构建。

自动化测试不依赖物理传感器。最终四传感器固件已在
ESP32-D0WD-V3 上烧录，并在 Raspberry Pi 5 完成 120 个五秒窗口的
10 分钟真实会话。会话整包验收为 `valid=true`，雷达在全部窗口中为
`not_configured`。`smooth` 和 `live_max` 是保留的实验档，不是最终
`analytics` 生产基线的验收阻塞项。详细证据见 `HARDWARE_SMOKE_TEST.md`。

## 常见问题

**I2C 找不到 MLX90640**

检查 I2C 是否启用、供电是否为 3.3V、SDA/SCL 是否接反，以及 `i2cdetect -y 1` 是否显示 `0x33`。总线不稳定时把 `i2c_frequency_hz` 从 800000 降到 400000。

**雷达显示 `not_configured`**

这是最终四传感器生产配置的预期状态，不是故障。不要添加 `RADAR_PORT`，也不要用零目标或模拟轨迹改写该状态。

**声音驱动无法启动**

确认 PortAudio 与输入设备已安装。Linux 可先检查 `python -m sounddevice`。模块不会创建音频文件；采集目录中出现音频扩展名应视为隐私测试失败。

**GPIO 或 micro:bit 输出失败**

状态输出错误不会停止采样。先使用 `actuation.device: log` 验证映射，再单独检查引脚编号、串口设备和权限。

**某个环境传感器缺失**

窗口仍会生成，对应环境值为 `null`，健康状态和 `quality.warnings` 会说明缺失来源。
