# 模块 1 真实硬件冒烟测试

状态：**部分执行。ESP32 烧录和树莓派软件验证通过，真实传感器尚未接入。**

本文件记录 Raspberry Pi 5、ESP32 和各类传感器的实际验收结果。ESP32 已连接并完成烧录测试，其他传感器尚未接入。未执行的丢帧率、无效包率和资源占用不得填写或推测。

## 测试信息

| 项目 | 记录 |
|---|---|
| 日期与时区 | 2026-07-18，Asia/Singapore |
| 操作者 | 自动化测试；未记录个人标识 |
| Raspberry Pi 型号 | Raspberry Pi 5，aarch64 |
| Raspberry Pi OS 版本 | Debian Trixie，内核 `6.18.34+rpt-rpi-2712` |
| Python 版本 | 3.13.5 |
| Git commit | `9e5919a` |
| 配置文件 | `config/example.yaml`、`config/real.example.yaml` |
| 已连接硬件 | ESP32-D0WD-V3，通过 CH340 接入 `/dev/ttyUSB0` |
| 未检测到的设备 | MLX90640、LD2450、BH1750、AHTx0、音频输入设备 |

## 已完成的部署与烧录检查

| 检查 | 实际结果 |
|---|---|
| 树莓派部署 | 模块 1 已部署到 `/home/pi/privacy-study-space-advisor` |
| Python 环境 | `.venv` 已安装 `dev` 与 `hardware` 依赖 |
| 自动测试 | `36 passed in 0.76s` |
| Pi 5 GPIO 后端 | 安装 `swig` 与 `liblgpio-dev` 后，`board`/`lgpio` 导入通过 |
| 两分钟实时模拟 | 24 个 5 秒窗口，耗时 2:00.20，退出码 0 |
| 模拟峰值内存 | 25,040 KiB |
| I²C | 已启用 `/dev/i2c-1`，总线扫描未发现从设备 |
| 音频输入 | PortAudio 可导入，系统检测到 0 个采集设备 |
| ESP32 编译 | Flash 281,392 bytes（21%），全局变量 22,092 bytes（6%） |
| ESP32 烧录 | 写入和哈希校验通过，硬复位成功 |
| ESP32 串口 | 115200 baud 连续读取 5 条 `PSSA_ESP32_HEARTBEAT` |
| ESP32 端口释放 | 连续 3 轮打开、读取和关闭，每轮收到 2 条心跳，结束后无进程占用串口 |
| 真实配置降级 | 探测进程退出码 0；缺失设备返回 offline/degraded，未发生未处理异常 |
| 雷达端口保护 | 未设置 `RADAR_PORT` 时拒绝加载；显式不存在端口时安全报告未连接，未访问 ESP32 串口 |
| 隐私文件检查 | 部署目录内 WAV、PCM、MP3、FLAC 文件数量为 0 |
| 无传感器长测 | 间歇故障模拟 360 窗口/30:01.16，退出和立即重启通过，峰值 RSS 42,560 KiB |
| 内存优化复测 | 延迟加载验收依赖后 24 窗口/2:00.17，峰值 RSS 24,544 KiB，降低约 42.3% |

ESP32 的硬件地址没有写入本文件。`/dev/ttyUSB0` 当前属于 ESP32，不能同时作为 `config/real.example.yaml` 中的 LD2450 端口。

## 1. 连接探测

```bash
cd edge/hardware
source .venv/bin/activate
export RADAR_PORT=/dev/serial/by-id/REPLACE_WITH_LD2450_USB_TTL_DEVICE
python scripts/probe_sensors.py \
  --config config/real.example.yaml \
  | tee hardware-probe.json
```

检查：

- [ ] MLX90640 返回 32 × 24 帧摘要，没有打印完整温度矩阵。
- [ ] LD2450 能从噪声或截断数据后恢复到有效帧。
- [ ] 声音输出只有 RMS 与峰值等统计值。
- [ ] 光照、温度和湿度单位正确。
- [x] 缺失传感器被标记为 degraded/offline，不会导致进程崩溃。

## 2. 十分钟连续采集

在不记录姓名、学号或可识别备注的前提下执行：

```bash
export RADAR_PORT=/dev/serial/by-id/REPLACE_WITH_LD2450_USB_TTL_DEVICE
python scripts/collect_session.py \
  --config config/real.example.yaml \
  --room room_a \
  --scenario quiet_study_recommended \
  --duration 600 \
  --participant-range 1-4 \
  --realtime
```

| 指标 | 结果 |
|---|---|
| 窗口数（5 秒窗口预期 120） | 待填写 |
| 进程未处理异常 | 待填写 |
| 热阵列有效帧/期望帧 | 待填写 |
| 热阵列丢帧率 | 待填写 |
| 雷达有效帧/期望帧 | 待填写 |
| 雷达无效包或流重同步次数 | 待填写 |
| 最低窗口完整度 | 待填写 |
| 平均 CPU 使用率 | 待填写 |
| 峰值常驻内存 | 待填写 |
| 会话校验和验证 | 待填写 |

建议同时使用 `top`、`htop` 或 `pidstat` 记录资源占用，但不要把系统用户名、网络地址或其他机器隐私写入提交文件。

## 3. 隐私检查

```bash
find data/sessions -type f
```

- [ ] 没有 `.wav`、`.pcm`、`.mp3`、`.flac` 等音频文件。
- [ ] 没有 RGB 图像或视频。
- [ ] `session.json` 中 `raw_audio_persisted` 为 `false`。
- [ ] `windows.jsonl` 不含姓名、学号或稳定人员标识。
- [ ] 热帧只存在本地 `thermal/*.npz`。
- [ ] 相邻窗口中的雷达目标 ID 不用于跨窗口追踪。

## 4. 释放与重启

- [x] ESP32 串口连续 3 轮打开、读取和关闭均成功，结束后端口未被占用。
- [ ] 真实传感器采集正常结束后，可立即再次运行 `probe_sensors.py`。
- [ ] 中断进程后，串口、I2C 和 GPIO 未被持续占用。
- [ ] LED/micro:bit 输出失败不会中断采样。

## 结论

当前结论为部分通过。树莓派部署、硬件依赖、I²C 启用、软件回归、两分钟实时模拟、ESP32 编译烧录和串口通信均已验证。真实传感器没有接入，因此 10 分钟采集、丢帧率、无效包率、环境单位和进程重启释放仍不能填写。

下一次测试前先完成物理接线：MLX90640、BH1750 和 AHTx0 接到 I²C 总线，LD2450 使用独立 USB-TTL 串口，USB 麦克风作为音频输入。接线完成后重新运行第 1 至第 4 节，不得用模拟结果替代真实测量。
