# 模块 1 真实硬件验收记录

状态：**最终四传感器 `analytics` 生产基线已通过实机烧录、基础探测、10 分钟连续采集、会话整包验收和停止后重启。**

本页面向模块维护者和验收人。它只记录已观察的真实结果，不用模拟数据代替实物证据。

## 最终硬件基线

| 项目 | 最终配置 |
|---|---|
| 验收日期 | 2026-07-22，Asia/Singapore |
| Raspberry Pi | Raspberry Pi 5，aarch64，`raspberrypi.local` |
| ESP32 | WeMos D1 R32 / ESP32-D0WD-V3，CH340 USB 串口 |
| 稳定串口 | `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`，460800 baud |
| 生产档位 | `analytics`，MLX90640 8 Hz 子页 / 2 FPS 完整热帧 |
| 启用传感器 | MLX90640、HW-485 声音、HW-486 光敏、HW-507/DHT11 |
| 雷达 | 不安装；固件和真实配置禁用，契约输出 `not_configured` |

本页记录的 10 分钟验收当时使用 HW-485 的 5V 分压方案。验收完成后，现场接线改为 3V3 供电、AO 直连 GPIO34，并重新确认实时 RMS 可产生非零值；当前接线以 `docs/RASPBERRY_PI_CODEX_HANDOFF.md` 为准。HW-486 尚未用参考照度计标定，因此 `light_lux` 必须保持 `null`，并携带 `hw486_uncalibrated_light_proxy` 警告。

## 固件构建与烧录

Pi 使用 Arduino CLI 1.5.1、ESP32 core 3.3.10 和 `sketch.yaml` 固定的库版本构建最终固件：

| 指标 | 结果 |
|---|---:|
| Flash | 336,072 bytes（25%） |
| 全局内存 | 39,092 bytes（11%） |
| 芯片身份 | ESP32-D0WD-V3 revision 3.1 |
| 写后验证 | bootloader、分区与应用镜像均通过；应用输出 `Hash of data verified` |

部署前副本保存在 Pi 的：

```text
/home/pi/privacy-study-space-advisor/.codex-backups/pre-four-sensor-final-20260722T1429
```

## 最终基础探测

烧录后四个传感器均为 `connected=true` 且 `status=ok`：

| 传感器 | 观测值 |
|---|---|
| MLX90640 | 32×24，24.27–27.29°C |
| HW-485 | 静音窗 RMS/peak 为 0；`raw_audio_persisted=false` |
| HW-486 | ADC 332，归一化值 0.081074，`light_lux=null` |
| DHT11 | 21.7°C，63.9% RH |

探测输出只包含上述四项，不构建雷达驱动。

## 10 分钟真实会话

会话 ID：`session-20260722T063105865Z-57c0fc92`

Pi 本地路径：

```text
/home/pi/privacy-study-space-advisor/edge/hardware/data/sessions/session-20260722T063105865Z-57c0fc92
```

| 指标 | 结果 |
|---|---:|
| 运行时间 | 10:01.84 |
| 进程退出码 | 0 |
| 窗口 | 120/120 |
| 热阵列文件 | 120 个 NPZ |
| 热帧总数 | 1,180 |
| 热阵列健康窗口 | 120/120 |
| 声音健康窗口 | 120/120 |
| 雷达语义 | 120/120 为 `not_configured`，总样本 0 |
| 最低完整度 | 0.864865 |
| 平均完整度 | 0.934234 |
| 用户 CPU / 系统 CPU | 10.49 s / 2.34 s |
| 峰值 RSS | 39,040 KiB |
| Swap | 0 |

除未标定光照代理警告外，实测边界差只包含热阵列 9/10、声音 17–19/20 和光照 4/5。未修改阈值或伪造样本来提高完整度。

## 整包、隐私与重启验收

`study-space-verify-session` 返回：

| 指标 | 结果 |
|---|---|
| `valid` | `true` |
| 已检查文件 | 123 |
| 热阵列文件 | 120 |
| 错误 | 0 |
| WAV/PCM/MP3 | 0 |
| MP4/AVI/MOV | 0 |
| JPG/JPEG/PNG | 0 |

会话完成后串口无占用进程。立即重新执行探测成功，四个传感器仍为 `connected=true/status=ok`，Hub 序号缺口、队列丢弃、重连和协议无效帧均为 0。

匿名真实窗口摘要已保存为 `shared/fixtures/sensor_window_real_four_sensor.json`。该夹具移除了本地热阵列引用，不包含个人标识、原始音频、图像、视频或雷达轨迹。

## 复现验收

```bash
cd /home/pi/privacy-study-space-advisor/edge/hardware
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0

PYTHONPATH=src .venv/bin/python scripts/probe_sensors.py \
  --config config/esp32-hub.example.yaml

PYTHONPATH=src .venv/bin/python scripts/collect_session.py \
  --config config/esp32-hub.example.yaml \
  --room room_a \
  --scenario quiet_study_recommended \
  --duration 600 \
  --participant-range 1-4 \
  --realtime

PYTHONPATH=src .venv/bin/python scripts/verify_session.py \
  data/sessions/SESSION_ID
```

## 不影响最终验收的可选项

`smooth`（16 FPS）和 `live_max`（32 FPS）保留为实验性热成像档位。它们已通过编译期配置与带宽门禁，但没有纳入最终生产基线，不应冒充已通过实机稳定性测试。
