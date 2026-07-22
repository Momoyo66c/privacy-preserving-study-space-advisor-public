# 模块 1 真实硬件验收记录

状态：**五传感器固件已烧录；四传感器链路通过，LD2450 物理 UART 未收到有效帧。完整验收仍待雷达复测、10 分钟真实会话和高帧率阶梯测试。**

本文件区分“已经观察到的真实结果”和“尚未执行的指标”。旧的 2026-07-18
空载 ESP32 烟雾固件结果只作为链路历史，不代表当前生产 Sensor Hub 状态。

## 当前硬件与软件基线

| 项目 | 当前记录 |
|---|---|
| 最后现场日期与时区 | 2026-07-22，Asia/Singapore |
| Raspberry Pi | Raspberry Pi 5，aarch64，地址最后确认为 `192.0.2.76` |
| ESP32 | WeMos D1 R32 / ESP32-D0WD-V3，经 CH340 USB 串口连接 Pi |
| 生产固件 | `firmware/esp32_sensor_hub/`，协议 v2，默认 `analytics` 档 |
| 当前串口 | 稳定路径 `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`，460800 baud |
| 已实测传感器 | MLX90640、HW-485 声音、HW-486 光敏、HW-507/DHT11；LD2450 已接线但尚未返回有效 UART 帧 |
| LD2450 | 已到货并启用；TX/RX 使用 GPIO16/17，当前能力位为 0，不伪造雷达数据 |
| 当前连接状态 | Pi 通过 `raspberrypi.local` 可达；五传感器固件已部署、编译和烧录 |

HW-485 的 `AO` 必须经过 10 kΩ/10 kΩ 分压后接 GPIO34，并与 ESP32 共地。
该批模块静音基线可为 0；真实有声试验已观察到峰值上升，因此生产固件把全零
窗口视为有效静音，不用软件阈值掩盖接线问题。HW-486 尚未参考照度计标定，
只上传 ADC 代理值，`light_lux` 必须保持 `null`。

## 已完成的真实检查

| 检查 | 实际结果 |
|---|---|
| Sensor Hub 构建 | ESP32 core 3.3.10 和固定库版本编译通过；生产修正版 Flash 336,020 bytes，全局内存 39,092 bytes |
| 烧录完整性 | ESP32-D0WD-V3 应用及引导相关镜像写后哈希校验通过 |
| 协议 | v2 COBS、CRC32、序号、能力位正常；最终探测无 CRC 错误、序号缺口、队列丢弃或重连 |
| MLX90640 | 返回 32×24、768 个有限温度值；最终完整探测观测 25.85–32.8°C |
| HW-485 | 静音 RMS/peak 为 0；制造声音时 GPIO34 聚合峰值曾上升到 230/192 和 27/21 |
| HW-486 | 最终探测 ADC 410；未标定，所以 `light_lux=null` 并携带代理值 warning |
| DHT11 | 最终探测 24.6°C、59.2% RH；读取间隔遵守约 2 秒限制 |
| 五秒正式窗口 | 热阵列 9/10、声音 19/20，光照和温湿度达到配置期望；完整度 0.945946 |
| 隐私扫描 | 正式部署数据目录中 WAV/PCM/MP3/MP4/AVI/MOV 为 0 |
| 热图诊断 | 真实帧序号递增，32×24/768 值；只监听 `127.0.0.1:8765`，停止后端口与串口释放 |
| 串口重新打开 | 停止热图后，同一稳定串口立即重读成功 |
| 模拟长测 | 间歇故障 360 窗口/30:01.16，退出和立即重启成功；优化后两分钟峰值 RSS 24,544 KiB |
| 2026-07-22 五传感器固件 | 相关 95 项通过；Flash 336,484 bytes、全局内存 39,132 bytes；主固件写后哈希通过 |
| 2026-07-22 现场探测 | 热阵列 18.88–27.64°C、声音静音窗 RMS/peak 0、光照 ADC 334、DHT11 21.8°C/64.3% RH；四项 ok，LD2450 degraded |
| degraded 窗口打包 | 真实 5 秒窗口热阵列 10 帧，会话验收 `valid=true`；雷达 0 样本显式标记 degraded |

这里的五秒窗口是采样调度验收，不代替规格要求的 10 分钟真实会话。

## 当前标准探测

LD2450 已通过 ESP32 UART2 启用，仍只使用 Sensor Hub 稳定串口，不另设假的 `RADAR_PORT`：

```bash
cd /home/pi/privacy-study-space-advisor/edge/hardware
source .venv/bin/activate
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
python scripts/probe_sensors.py --config config/esp32-hub.example.yaml
```

验收条件：

- [x] MLX90640 返回 32×24 摘要，不把完整矩阵写入普通日志。
- [x] 声音输出只有 RMS、标准差和峰值等统计量。
- [x] HW-486 明确为未标定代理，不伪造 lux。
- [x] DHT11 输出摄氏度和相对湿度百分比。
- [x] 单个设备缺失不会导致主进程崩溃。
- [ ] 修正 LD2450 物理 UART 链路后验证有效帧、噪声恢复和窗口局部目标 ID。

## 待执行：高帧率阶梯

不得直接覆盖正式默认。每个档位都先核对固件 profile 与 Pi 主机 baud：

| 顺序 | 固件档位 | 子页率 / 完整帧上限 | UART | 状态 |
|---|---|---|---|---|
| 1 | `analytics` | 8 Hz / 2 FPS 发布 | 460800 | 已有实机基线 |
| 2 | `smooth` | 32 Hz / 16 FPS | 460800 | 待编译、烧录、实测 |
| 3 | `live_max` | 64 Hz / 32 FPS | 921600 | 待编译、烧录、实测 |

每档记录实际采集 FPS、帧龄、CRC/序号错误、队列丢弃、声音/光照/温湿度样本
公平性、CPU、RSS 和 10 分钟稳定性。32 FPS 是 64 Hz 子页率对应的完整帧上限，
不是当前已证明结果。失败时回退上一档，并保留 `analytics` 为正式默认。

## 待执行：十分钟真实会话

树莓派恢复后，先部署并验证当前提交，再执行：

```bash
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
python scripts/collect_session.py \
  --config config/esp32-hub.example.yaml \
  --room room_a \
  --scenario quiet_study_recommended \
  --duration 600 \
  --participant-range 1-4 \
  --realtime
study-space-verify-session data/sessions/SESSION_ID
```

| 指标 | 结果 |
|---|---|
| 窗口数（5 秒窗口预期 120） | 待执行 |
| 进程未处理异常 | 待执行 |
| 各传感器有效帧/期望帧与丢帧率 | 待执行 |
| 协议 CRC、序号缺口、队列丢弃和重连 | 待执行 |
| 最低/平均窗口完整度 | 待执行 |
| 平均 CPU 与峰值 RSS | 待执行 |
| 会话整包验收 | 待执行 |
| 停止后立即重新探测 | 待执行 |

## 真实会话隐私门禁

- [ ] 没有音频、RGB 图像或视频文件。
- [ ] `session.json.privacy` 的四个字段均为 `false`。
- [ ] `windows.jsonl` 不含姓名、学号或稳定人员标识。
- [ ] 热帧仅位于本地 `thermal/*.npz`，且不进入后端 Observation。
- [ ] 雷达目标 ID 只在当前窗口有效。
- [ ] `study-space-verify-session` 返回 `valid=true`。
- [ ] 选取真实样例前删除现场身份备注，仅保留匿名房间和设备 ID。

## 结论

当前可以确认生产 Sensor Hub 与 MLX90640、HW-485、HW-486、DHT11 的基础采集
链路有效，LD2450 未出帧时能安全降级并生成可验证会话包。不能确认的仍是 LD2450
有效帧与目标响应、16/32 FPS 实机稳定性、10 分钟真实会话和可提交的匿名真实样例。
