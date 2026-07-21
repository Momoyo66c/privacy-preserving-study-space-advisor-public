# 模块 1 交接说明

更新时间：2026-07-21
分支：`module1/hardware-foundation`

## 当前结论

模块 01 的软件、模拟、离线打包和当前四个实物传感器适配已经完成。真实
MLX90640、HW-485、HW-486 和 DHT11 已通过 ESP32 Sensor Hub 在 Raspberry Pi 5
上完成基础探测和五秒窗口验收。LD2450 尚未到货，10 分钟真实会话和高帧率
阶梯尚未执行，因此不能把整个模块标记为最终硬件验收完成。

树莓派当前离线。2026-07-21 增加的热图平滑、高帧率 profile 和会话读取增强
只有本地测试证据，尚未部署或烧录。详细状态以 `HARDWARE_SMOKE_TEST.md` 和
`REQUIREMENTS_AUDIT.md` 为准。

## 已完成能力

- 统一 `SensorDriver` 接口、重试、健康、降级、离线与幂等释放。
- MLX90640、LD2450、声音强度、光照、温湿度直连驱动及 ESP32 Hub 兼容适配器。
- ESP32 Hub v2：COBS、CRC32、协议版本、全局序号、能力位、有界负载、队列、
  断线重连和旧样本清理。
- 当前实物型号固件：MLX90640、HW-485、HW-486、HW-507/DHT11；LD2450 可选。
- 5–10 秒非重叠窗口、完整度、警告、环境缺失语义和窗口局部雷达目标 ID。
- 确定性模拟器、单设备故障注入、两分钟集成与 30 分钟间歇故障长测。
- JSONL + 压缩 NPZ 离线会话、SHA-256、保留策略和禁止原始音频/图像/视频。
- `study-space-verify-session` 整包验收及模块 2 `SessionReader` 流式读取边界。
- GPIO RGB LED、micro:bit 和无硬件日志状态适配器；状态输出失败不阻断采集。
- 本地回环热图：二进制最新帧长轮询、时间/空间平滑、真实采集 FPS 与帧龄，
  只保留内存最新帧。
- 三档热成像配置：`analytics` 2 FPS、`smooth` 16 FPS、`live_max` 32 FPS；
  编译期 UART 80% 带宽门禁和 400 kHz 初始化/1 MHz 高速 I²C 分离。

## 当前真实硬件证据

| 项目 | 结果 |
|---|---|
| ESP32 | ESP32-D0WD-V3 生产 v2 烧录与写后哈希通过 |
| MLX90640 | 32×24/768 有限温度值；最终探测 25.85–32.8°C |
| HW-485 | 静音可为 0；有声试验确认 GPIO34 聚合值会上升；只上传统计量 |
| HW-486 | ADC 代理有效；未标定，`light_lux=null` |
| DHT11 | 最终探测 24.6°C、59.2% RH |
| 正式五秒窗口 | 热阵列 9/10、声音 19/20，环境达到期望，完整度 0.945946 |
| Hub 健康 | 最终探测无 CRC 错误、序号缺口、队列丢弃或重连 |
| 连续热图 | 真实序号递增，回环监听，停止后串口可立即重新打开 |

这些数据不等于 10 分钟真实会话，也不证明 `smooth`/`live_max` 稳定。

## 模块 2 的稳定入口

开发期单窗口输入：

```text
shared/fixtures/sensor_window_*.json
shared/contracts/sensor_window.schema.json
```

离线会话输入不应直接拼接 `local://` 路径。安装模块 01 包后使用：

```python
from study_space_hardware.session_reader import SessionReader

session = SessionReader("data/sessions/SESSION_ID")
metadata = session.metadata
for item in session:
    sensor_window = item.payload
    thermal_frames = item.thermal_frames
```

`SessionReader` 在暴露第一个窗口前验证整包。它检查 SHA-256、共享 Schema、
隐私字段、未登记/禁止文件、房间与设备一致性、UTC 时间和非重叠窗口、NPZ
引用/形状/帧数/有限值/温度范围。失败时抛出 `InvalidSessionError`，不会返回
部分数据；正常热阵列为只读 `float32 (N, 768)`，缺失时为 `None`。

模块 2 必须继续遵守：

- 根据 `health`、`quality.completeness` 和 warnings 处理降级窗口。
- 保留缺失环境值为 `null`，不得把 HW-486 ADC 代理冒充 lux。
- 不把 `radar.tracks[].target_id` 用作跨窗口身份。
- 只在本地训练/标注流程读取 NPZ；不把热帧放入 Observation。
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

python scripts/collect_session.py \
  --config config/example.yaml \
  --room room_a \
  --scenario discussion_allowed \
  --duration 60

study-space-verify-session data/sessions/SESSION_ID
```

树莓派当前生产 Hub 探测：

```bash
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
python scripts/probe_sensors.py --config config/esp32-hub.example.yaml
```

实时热图：

```bash
PYTHONPATH=src .venv/bin/python scripts/live_thermal.py \
  --config config/esp32-hub.example.yaml
```

服务默认只监听 `127.0.0.1:8765`；Mac 通过 SSH 本地端口转发访问。页面的
60 FPS 是插值渲染率，实际采集 FPS 单独显示。

## 仍待完成

1. 树莓派恢复后部署当前分支，先跑 144 项模块 01 回归和固定 Arduino 工具链构建。
2. 按 `analytics → smooth → live_max` 顺序烧录和实测；`live_max` 主机与固件均用
   921600 baud，失败时回退，不修改正式默认。
3. 使用当前四传感器执行 10 分钟真实会话，记录丢帧、协议错误、CPU、RSS、
   完整度和停止后重启。
4. 会话通过 `study-space-verify-session` 后，清除现场身份信息并选取匿名真实样例。
5. LD2450 到货后接 ESP32 UART2，补做真实帧、损坏流恢复、窗口匿名化和 Gate B。
6. 如演示需要实体状态灯，再完成 GPIO RGB LED 或 micro:bit 的接线验收；软件
   适配器与五种状态映射已经通过单元测试。

## 硬件注意事项

- HW-485 5 V 供电时，`AO` 经 10 kΩ/10 kΩ 分压中点接 GPIO34；接线前实测不超过
  3.3 V，所有模块共地。
- HW-486 未用参考照度计标定前只输出 ADC 代理和 warning。
- DHT11 读取间隔不得快于约 2 秒。
- LD2450 未到货前保持能力关闭；不要用零值或模拟轨迹伪装在线。
- `/dev/ttyUSB0` 是动态名称。部署使用 `/dev/serial/by-id/`，烧录前再次确认芯片。
- 完整接线、构建 profile 和烧录命令见 `firmware/esp32_sensor_hub/README.md`。

## 外部代码与许可证

- MLX90640 通过 MIT 许可的 Adafruit CircuitPython 包公开 API 使用，未复制其底层源码。
- LD2450 协议解析参考 MIT 许可资料并重新实现，版本见 `THIRD_PARTY_NOTICES.md`。
- 未复制检索到的 GPL/AGPL 项目源码；项目根许可证仍需维护者最终确认。
