# 模块 1：传感器与边缘硬件

本模块在 Raspberry Pi 5 或普通开发电脑上采集并编排热阵列、毫米波雷达、声音强度、光照和温湿度数据。每个 5 至 10 秒窗口都会转换为共享 `sensor_window` 契约，供模块 2 直接读取。

模块遵守以下隐私边界：

- 不采集 RGB 图像。
- 声音只在内存中计算 RMS、标准差和峰值，不保存 WAV、PCM 或其他原始音频。
- 雷达目标 ID 只在当前窗口内有效，不用于跨窗口追踪。
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
| 雷达 | HLK-LD2450 串口帧同步、包长校验、目标位置与速度解析 |
| 声音 | 短时内存缓冲区的 RMS、标准差和峰值统计 |
| 环境 | BH1750 光照与 AHTx0 温湿度驱动 |
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

`config/example.yaml` 默认启用模拟器，适合开发和 CI。`config/real.example.yaml` 关闭模拟器，作为 Raspberry Pi 配置起点。

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

## Raspberry Pi 5 接线

以下引脚使用 Raspberry Pi 的物理引脚编号与 BCM 名称共同说明。接线前断电，并确认所有外设电压与模块版本。

| 设备 | Raspberry Pi 连接 | 说明 |
|---|---|---|
| MLX90640 | 3.3V、GND、SDA/BCM2、SCL/BCM3 | I2C，常见地址 `0x33`（YAML 十进制为 `51`） |
| BH1750 | 3.3V、GND、SDA/BCM2、SCL/BCM3 | 与 MLX90640 共用 I2C 总线 |
| AHT20/AHTx0 | 3.3V、GND、SDA/BCM2、SCL/BCM3 | 与其他 I2C 设备地址不得冲突 |
| HLK-LD2450 | 5V/GND 与 USB-TTL 串口 | 使用 3.3V 逻辑兼容的 USB-TTL，默认 256000 baud |
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
export RADAR_PORT=/dev/serial/by-id/REPLACE_WITH_LD2450_USB_TTL_DEVICE
python scripts/probe_sensors.py --config config/real.example.yaml
```

`RADAR_PORT` 必须显式设置为 LD2450 独立 USB-TTL 的稳定设备路径。不要把当前属于 ESP32 的 `/dev/ttyUSB0` 填入该变量；无法确认设备身份时先停止探测并检查 `ls -l /dev/serial/by-id/`。

在 64 位 Raspberry Pi OS 上，`hardware` extra 会同时安装 Pi 5 所需的
`lgpio` 后端。安装后可先运行 `python -c "import board, lgpio"`，确认
Blinka 与 GPIO 后端均可导入，再探测真实传感器。

`probe_sensors.py` 对每个驱动输出连接状态、最近一次安全摘要和健康状态。它不会打印完整热矩阵或保存声音缓冲区。

如果使用 micro:bit，将 `actuation.device` 改为 `microbit`，并在 `actuation.options.port` 设置串口。GPIO 模式需要在选项中提供 `red_pin`、`green_pin` 和 `blue_pin`。

## ESP32 烧录与串口检查

仓库提供最小 ESP32 串口烟雾固件，用于确认树莓派能够识别、编译、烧录和读取开发板。固件不采集传感器数据，也不连接网络。操作命令和成功输出见 [`firmware/README.md`](firmware/README.md)。

烧录前必须读取芯片型号，并核对 `/dev/serial/by-id/`。`/dev/ttyUSB0` 只是动态设备名，不代表它一定是 LD2450。ESP32 与 LD2450 同时接入时应使用两个独立串口，并通过 `RADAR_PORT` 给出雷达对应的稳定设备路径。

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

真实采集时改用 `config/real.example.yaml` 并加入 `--realtime`。输出结构：

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

## 窗口契约

JSON Schema 位于 `../../shared/contracts/sensor_window.schema.json`，示例位于 `../../shared/fixtures/`。

默认 5 秒窗口的期望样本数为：

- 热阵列：10 帧（2 Hz）
- 雷达：50 个串口样本（10 Hz）
- 声音：20 个统计样本（4 Hz）
- 光照：5 个样本（1 Hz）
- 温湿度：5 个样本（1 Hz）

`quality.completeness` 是所有已启用传感器有效样本数与期望样本数之比，范围为 0–1。单个传感器故障不会中止窗口；窗口会携带 degraded/offline 健康状态与警告。雷达目标会被重新命名为窗口局部 ID，例如 `target-8f10aa32-1`。

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

当前自动化测试已在无物理传感器的开发环境通过。真实硬件的 10 分钟连续采集、丢帧率、无效包率和资源占用仍需在 Raspberry Pi 上执行，记录模板见 `HARDWARE_SMOKE_TEST.md`。仓库不伪造真实硬件样例。

## 常见问题

**I2C 找不到 MLX90640**

检查 I2C 是否启用、供电是否为 3.3V、SDA/SCL 是否接反，以及 `i2cdetect -y 1` 是否显示 `0x33`。总线不稳定时把 `i2c_frequency_hz` 从 800000 降到 400000。

**LD2450 一直 offline**

确认 `RADAR_PORT` 指向 LD2450 独立 USB-TTL 的稳定设备路径，并检查权限与 256000 baud。不要仅凭 `/dev/ttyUSB0` 这类动态名称识别设备。损坏或截断的数据包会被跳过，后续有效帧仍可重新同步。

**声音驱动无法启动**

确认 PortAudio 与输入设备已安装。Linux 可先检查 `python -m sounddevice`。模块不会创建音频文件；采集目录中出现音频扩展名应视为隐私测试失败。

**GPIO 或 micro:bit 输出失败**

状态输出错误不会停止采样。先使用 `actuation.device: log` 验证映射，再单独检查引脚编号、串口设备和权限。

**某个环境传感器缺失**

窗口仍会生成，对应环境值为 `null`，健康状态和 `quality.warnings` 会说明缺失来源。
