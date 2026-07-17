# 模块 1 交接说明

## 当前状态

模块 1 的软件实现已完成，并已部署到 Raspberry Pi 5。树莓派本机的 35 项测试、编译检查和两分钟实时模拟均通过。ESP32 烧录与串口心跳也已复验。

MLX90640、LD2450、BH1750、AHTx0 和音频输入设备尚未接入。`HARDWARE_SMOKE_TEST.md` 中的十分钟真实采集指标仍待执行，仓库没有用模拟数据冒充真实采集样例。

## 已完成

- 统一传感器 Protocol、基类、重试与 health/degraded/offline 状态。
- MLX90640、HLK-LD2450、声音强度、BH1750 和 AHTx0 驱动。
- 与真实驱动共用数据模型的确定性模拟器。
- 5–10 秒非重叠窗口、完整度计算、警告和窗口局部雷达 ID。
- 本地 JSONL + NPZ 会话、SHA-256 校验和与会话数量保留策略。
- 离线会话使用结构化 `known_anomalies` 数组记录不含个人身份的已知采集异常。
- `study-space-verify-session` 对会话执行共享 Schema、校验和、NPZ 和隐私文件只读验收。
- 日志、GPIO RGB LED 与 micro:bit 状态输出。
- 共享 JSON Schema 和 5 个匿名夹具。
- 单元测试与模拟集成测试。
- LD2450 确定性随机分块/噪声/粘包/超时恢复和 MLX90640 损坏帧故障注入测试。
- 单作业 CI 执行 80% 覆盖率门禁、编译检查和 wheel 构建。
- Raspberry Pi 5 上的 `dev`/`hardware` 依赖安装和回归测试。
- ESP32-D0WD-V3 的编译、烧录、哈希校验和 115200 baud 心跳验证。

## 模块 2 的入口

模块 2 可以从两个位置读取输入：

1. `shared/fixtures/sensor_window_*.json`：开发和契约测试用的单窗口示例。
2. `data/sessions/<session_id>/windows.jsonl`：离线采集产生的逐窗口数据。

契约文件：

```text
shared/contracts/sensor_window.schema.json
```

每一行都是独立 JSON 对象，`schema_version` 当前为 `1.0`。模块 2 应：

- 根据 `health` 与 `quality.completeness` 处理降级窗口。
- 将缺失环境值保留为 `null`。
- 不把 `radar.tracks[].target_id` 当作跨窗口身份。
- 只在本地离线训练流程解析 `local://.../thermal/*.npz`。
- 不要求原始音频，因为该数据从未落盘。

安装与生成示例：

```bash
cd edge/hardware
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/run_simulator.py \
  --config config/example.yaml \
  --scenario degraded_thermal \
  --windows 1
```

离线会话：

```bash
python scripts/collect_session.py \
  --config config/example.yaml \
  --room room_a \
  --scenario discussion_allowed \
  --duration 60
```

## 已知限制与后续工作

- 当前 `/dev/ttyUSB0` 属于 ESP32，不是 LD2450。连接雷达后必须使用独立串口，并优先使用 `/dev/serial/by-id/` 稳定路径。
- `config/real.example.yaml` 要求显式设置 `RADAR_PORT`；未设置时会安全拒绝加载，避免误用 ESP32 串口。
- Raspberry Pi 的 `/dev/i2c-1` 已启用，但总线扫描没有发现设备。先检查供电和 SDA/SCL 接线，再运行真实探测。
- PortAudio 和 Python 音频依赖已安装，但系统目前没有音频采集设备。
- 需要在实际 Raspberry Pi 5 上确认 MLX90640 的 800 kHz I2C 稳定性；不稳定时先降至 400 kHz。
- 需要按具体 USB-TTL 设备调整 LD2450 串口路径。
- 声卡设备选择目前使用 `sounddevice` 默认输入，部署时应在操作系统层固定默认设备。
- 真实硬件 10 分钟运行、资源占用和重新启动测试尚未执行。
- 状态指示器已实现，但模型分类结果需要由上层调用 `set_state()` 传入。

## 验证命令

```bash
cd edge/hardware
source .venv/bin/activate
python -m pytest
python -m compileall -q src scripts
python scripts/probe_sensors.py --config config/example.yaml
```

真实硬件验收使用 `config/real.example.yaml` 和 `HARDWARE_SMOKE_TEST.md`。

## 2026-07-18 树莓派验证记录

```text
部署提交: b232ee1
pytest: 34 passed in 0.88s
compileall: passed
Pi 5 GPIO: board/lgpio imports passed after installing swig and liblgpio-dev
两分钟实时模拟: 24 windows, 2:00.20, exit 0
实时模拟峰值内存: 25040 KiB
I2C: /dev/i2c-1 enabled, no device address detected
音频: 0 capture devices
ESP32: compile/upload/hash verification passed
串口: 5 consecutive PSSA_ESP32_HEARTBEAT lines received
串口释放: 3 open/read/close cycles passed; no process retained the port
真实配置探测: exit 0; missing sensors reported offline/degraded
隐私文件: 0 WAV/PCM/MP3/FLAC files in deployment tree
会话异常元数据提交: ad4aa44
会话异常元数据针对性测试: 3 passed
更新后完整回归: 35 passed in 0.77s
更新后 compileall: passed
雷达端口安全配置提交: 9e5919a
缺少 RADAR_PORT: 按预期拒绝加载真实配置
不存在的专用雷达端口: 安全报告未连接，probe exit 0
雷达配置测试: 7 passed
雷达配置后完整回归: 36 passed in 0.76s
雷达配置后 compileall: passed
本机模块目录与仓库根目录测试: 均为 36 passed
Raspberry Pi 模块目录测试: 36 passed in 0.80s
Raspberry Pi 部署根目录测试: 36 passed
Raspberry Pi 部署根目录 compileall: passed
会话验收工具提交: a33e736
Raspberry Pi 会话验收针对性测试: 5 passed
Raspberry Pi 会话验收后完整回归: 41 passed
Raspberry Pi 模拟会话 CLI: valid PASS
Raspberry Pi 禁用 WAV 篡改检测: invalid PASS
Raspberry Pi 故障注入针对性测试: 14 passed
Raspberry Pi 故障注入后完整回归: 49 passed
Raspberry Pi 覆盖率门禁: 80.54%（要求 80%）
Raspberry Pi LD2450 驱动覆盖率: 93%
Mac 全新 wheel 环境四入口: passed
Raspberry Pi 全新 wheel 环境四入口: passed
Raspberry Pi 全新 wheel 环境 pip check: passed
Raspberry Pi 间歇故障长测: 360 windows / 30:01.16 / exit 0
长测峰值 RSS: 42,560 KiB
长测共享 Schema: 360 passed；window_id 360 unique
长测立即重启: passed
长测采集目录禁用媒体文件: 0
延迟导入后 Pi 完整回归: 55 passed / 84.59% coverage
延迟导入后实时对照: 24 windows / 2:00.17 / exit 0
延迟导入后峰值 RSS: 24,544 KiB（降低约 42.3%）
```

离线会话交付模块 2 前运行：

```bash
study-space-verify-session data/sessions/SESSION_ID
```

详细证据和仍待完成的真实传感器步骤见 `HARDWARE_SMOKE_TEST.md`。ESP32 烧录命令见 `firmware/README.md`。

## 外部代码与许可证

- MLX90640 驱动通过 PyPI 依赖使用 Adafruit 的 MIT 许可 CircuitPython 包，没有把该仓库源码复制进本项目。
- LD2450 帧字段和流解析参考了 MIT 许可的 `csRon/HLK-LD2450`，具体版本与声明见 `THIRD_PARTY_NOTICES.md`。
- 未复制已检索到的 GPL 或 AGPL 项目源码。
