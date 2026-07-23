# 模块 1 交接说明

更新时间：2026-07-22
分支：`module1/hardware-foundation`

## 交接结论

**模块 01 已按最终四传感器生产基线完成。**

MLX90640、HW-485、HW-486 和 DHT11 通过 ESP32 Sensor Hub 连接 Raspberry Pi 5。固件已烧录并通过写后哈希，四项基础探测全部正常，10 分钟真实会话的 120 个窗口已通过整包验收。

LD2450 已从最终实物范围移除。为保持 `schema_version=1.0` 和已有模块兼容，共享 `radar` 字段、模拟器和可选驱动仍保留。真实配置固定输出 `radar.health=not_configured`、0 样本和空轨迹，且不计入完整度。

## 已完成能力

- 统一 `SensorDriver` 接口、有界重试、健康状态、降级和幂等释放。
- ESP32 Hub v2：COBS、CRC32、版本、全局序号、能力位、有界队列、断线重连和旧样本清理。
- MLX90640 32×24 热阵列、HW-485 相对声强、HW-486 未标定光照代理、DHT11 温湿度。
- 5–10 秒非重叠窗口、有效样本计数、完整度、警告和统一时钟。
- 无雷达备援时的推理安全门禁：热阵列 offline 时输出 `not_inference_ready:thermal_offline_without_radar`。
- 确定性模拟器、单传感器故障注入、两分钟集成和历史 30 分钟间歇故障长测。
- JSONL + NPZ 离线会话、SHA-256、保留策略、隐私文件门禁和严格语义验收。
- `SessionReader` 先验整包，再按窗口流式读取只读热阵列。
- GPIO RGB LED、micro:bit 和无硬件日志指示适配器。
- 回环实时热图：二进制长轮询、时间/空间平滑、真实采集 FPS 和帧龄，不落盘。
- `analytics`、`smooth`、`live_max` 三档编译配置与 UART 带宽门禁。生产固定使用已实机验证的 `analytics`。

## 最终硬件证据

| 项目 | 结果 |
|---|---|
| ESP32 | ESP32-D0WD-V3；Flash 336,072 bytes，全局内存 39,092 bytes，写后哈希通过 |
| MLX90640 | 32×24 有限温度值；最终探测 24.27–27.29°C |
| HW-485 | 静音窗可为 0；只上传 RMS、标准差和峰值 |
| HW-486 | ADC 代理有效；未标定，`light_lux=null` |
| DHT11 | 最终探测 21.7°C、63.9% RH |
| 10 分钟会话 | 120 窗口，退出码 0，最低/平均完整度 0.864865/0.934234 |
| 整包验收 | `valid=true`，123 文件，120 热阵列 NPZ，0 错误 |
| 资源 | 峰值 RSS 39,040 KiB，Swap 0 |
| 隐私 | 原始音频、RGB 图像和视频文件均为 0 |
| 重启 | 长会话结束后立即重新探测成功，协议错误/丢帧/重连均为 0 |
| 最终标准回归 | 145 项通过，覆盖率 84.30%（门禁 80%），编译与 wheel 构建通过 |

完整数据见 `HARDWARE_SMOKE_TEST.md`。Pi 上的会话 ID 为 `session-20260722T063105865Z-57c0fc92`。

## 模块 2 的稳定入口

不连接硬件时，使用共享契约和夹具：

```text
shared/contracts/sensor_window.schema.json
shared/fixtures/sensor_window_*.json
shared/fixtures/sensor_window_real_four_sensor.json
```

读取离线会话：

```python
from study_space_hardware.session_reader import SessionReader

session = SessionReader("data/sessions/SESSION_ID")
metadata = session.metadata
for item in session:
    sensor_window = item.payload
    thermal_frames = item.thermal_frames
```

`SessionReader` 在返回第一个窗口前检查 SHA-256、共享 Schema、隐私文件、元数据、时间顺序、标识一致性和 NPZ 语义。任一检查失败都抛出 `InvalidSessionError`，不返回部分数据。

模块 2 必须：

- 将 `radar.health=not_configured` 视为最终硬件基线，不要伪造零目标特征。
- 根据 `health`、`quality.completeness` 和 `warnings` 处理降级窗口。
- 收到 `not_inference_ready:thermal_offline_without_radar` 时不进行正常推理。
- 保留缺失环境值为 `null`，不得把 HW-486 ADC 代理冒充 lux。
- 只在本地训练/标注流程读取 NPZ，不把热帧放入 Observation。
- 不寻找原始声音，因为模块 01 从不持久化原始波形。

## 常用命令

```bash
cd edge/hardware
source .venv/bin/activate
python -m pytest -q
python -m compileall -q src tests scripts

python scripts/run_simulator.py \
  --config config/example.yaml \
  --scenario degraded_thermal \
  --windows 1

export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
python scripts/probe_sensors.py --config config/esp32-hub.example.yaml

python scripts/collect_session.py \
  --config config/esp32-hub.example.yaml \
  --room room_a \
  --scenario quiet_study_recommended \
  --duration 600 \
  --participant-range 1-4 \
  --realtime

study-space-verify-session data/sessions/SESSION_ID
```

## 运行限制与可选扩展

- 当前 HW-485 使用 3V3 供电，`AO` 直连 GPIO34，`DO` 不接。若改回 5V，必须先增加限压并测量 GPIO34 输入。
- HW-486 未用参考照度计标定前，只能输出 ADC 代理和 warning。
- DHT11 实际读取间隔不得快于约 2 秒。
- `smooth` 和 `live_max` 仅是实验档位，未纳入最终生产验收。
- GPIO RGB LED 或 micro:bit 可作为展示扩展；默认 `log` 指示器与五种状态映射已通过测试。
- `/dev/ttyUSB0` 是动态名称。运行配置始终使用 `/dev/serial/by-id/`。

## 外部代码与许可证

- MLX90640 通过 MIT 许可的 Adafruit 公开 API 使用，未复制其底层源码。
- LD2450 兼容解析器参考 MIT 许可资料并重新实现，版本见 `THIRD_PARTY_NOTICES.md`。
- 未复制检索到的 GPL/AGPL 项目源码。项目根许可证仍需维护者确认。

Pi 地址发现、Mac 后端恢复、无 Git 部署副本同步、systemd 安装、实时页面验收和会话打包的完整顺序见 [`../../docs/RASPBERRY_PI_CODEX_HANDOFF.md`](../../docs/RASPBERRY_PI_CODEX_HANDOFF.md)。
