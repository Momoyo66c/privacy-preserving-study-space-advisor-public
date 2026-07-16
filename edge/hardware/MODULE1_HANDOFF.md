# 模块 1 交接说明

## 当前状态

模块 1 的软件实现已完成，可在没有真实传感器的电脑上安装、测试、生成共享窗口和离线训练会话。自动化测试覆盖正常窗口、降级窗口、驱动异常、数据校验、隐私约束与两分钟模拟运行。

真实 Raspberry Pi 5 与传感器尚未接入本开发环境，因此 `HARDWARE_SMOKE_TEST.md` 中的十分钟连续采集指标仍待执行。仓库中没有用模拟数据冒充真实采集样例。

## 已完成

- 统一传感器 Protocol、基类、重试与 health/degraded/offline 状态。
- MLX90640、HLK-LD2450、声音强度、BH1750 和 AHTx0 驱动。
- 与真实驱动共用数据模型的确定性模拟器。
- 5–10 秒非重叠窗口、完整度计算、警告和窗口局部雷达 ID。
- 本地 JSONL + NPZ 会话、SHA-256 校验和与会话数量保留策略。
- 日志、GPIO RGB LED 与 micro:bit 状态输出。
- 共享 JSON Schema 和 5 个匿名夹具。
- 单元测试与模拟集成测试。

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

## 外部代码与许可证

- MLX90640 驱动通过 PyPI 依赖使用 Adafruit 的 MIT 许可 CircuitPython 包，没有把该仓库源码复制进本项目。
- LD2450 帧字段和流解析参考了 MIT 许可的 `csRon/HLK-LD2450`，具体版本与声明见 `THIRD_PARTY_NOTICES.md`。
- 未复制已检索到的 GPL 或 AGPL 项目源码。
