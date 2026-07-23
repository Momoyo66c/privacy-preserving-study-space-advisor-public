# 模块 1 交接说明

更新时间：2026-07-23
分支：`module1/relative-light-calibration`

## 交接结论

**模块 01 已按最终四传感器生产基线完成。**

MLX90640、HW-485、HW-486 和 DHT11 通过 ESP32 Sensor Hub 连接 Raspberry Pi 5。固件已烧录并通过写后哈希，四项基础探测全部正常，10 分钟真实会话的 120 个窗口已通过整包验收。

LD2450 已从最终实物范围移除。为保持 `schema_version=1.0` 和已有模块兼容，共享 `radar` 字段、模拟器和可选驱动仍保留。真实配置固定输出 `radar.health=not_configured`、0 样本和空轨迹，且不计入完整度。

## 已完成能力

- 统一 `SensorDriver` 接口、有界重试、健康状态、降级和幂等释放。
- ESP32 Hub v2：COBS、CRC32、版本、全局序号、能力位、有界队列、断线重连和旧样本清理。
- MLX90640 32×24 热阵列、HW-485 相对声强、HW-486 设备专属两点相对光照、DHT11 温湿度。
- HW-486 标定按暗点/亮点分阶段采集，只保存汇总统计，自动识别 ADC 方向并截断为 0–1；未使用参考照度计，因此始终不声明 lux。
- HW-485 支持带非零环境底噪余量的两阶段相对标定：安静 p95 加 10% 跨度
  余量映射为零，最高 10% 参考样本中位数映射为一；始终不声明 dB。
- HW-485 被判定无可靠响应后，新增 Windows 麦克风替代路径：Windows 只发送
  RMS/标准差/峰值摘要，经 SSH 隧道进入 Pi 回环接收器；原始音频不落盘、
  不上传，且不改变模块 1→2 公共契约。
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
| HW-486 | 两点相对标定已完成：暗点中位数 3648.5、亮点中位数 531.5、跨度 3117；`light_lux=null` |
| DHT11 | 最终探测 21.7°C、63.9% RH |
| 10 分钟会话 | 120 窗口，退出码 0，最低/平均完整度 0.864865/0.934234 |
| 整包验收 | `valid=true`，123 文件，120 热阵列 NPZ，0 错误 |
| 资源 | 峰值 RSS 39,040 KiB，Swap 0 |
| 隐私 | 原始音频、RGB 图像和视频文件均为 0 |
| 重启 | 长会话结束后立即重新探测成功，协议错误/丢帧/重连均为 0 |
| 最终标准回归 | 196 项通过，覆盖率 81.11%（门禁 80%），编译与 wheel 构建通过 |

完整数据见 `HARDWARE_SMOKE_TEST.md`。Pi 上的会话 ID 为 `session-20260722T063105865Z-57c0fc92`。

### 2026-07-23 HW-486 相对标定证据

- 设备：`pi5-a`，profile：
  `/home/pi/.config/pssa/calibration/hw486-relative.json`。
- 暗点：完全遮光，20 个样本，中位数 3648.5，范围 3643–3652，标准差
  2.02 ADC。
- 亮点：正常最亮室内照明，20 个样本，中位数 531.5，范围 530–534，
  标准差 1.19 ADC。
- 自动识别方向为 `decreasing`，有效跨度 3117 ADC，远高于 64 ADC
  门槛。
- 展示桥通过 `HW486_RELATIVE_CALIBRATION_PATH` 持久启用，重启后
  `active` 且 `NRestarts=0`。
- 亮点实时 Observation 为 `light_relative_mean=0.9995`、
  `light_lux=null`、`environment=ok`、`is_stale=false`，同时包含
  `hw486_relative_two_point_calibration` 和
  `hw486_uncalibrated_light_proxy`。
- 标定只保存两组汇总统计，不保存逐次读数；profile 权限为 600，不进入
  Git。

### 2026-07-23 HW-485 高频采样诊断证据

- 诊断复用生产固件约 4 kHz、每窗 400 点的采样，不刷写 ESP32、不改变引脚、
  协议或其他传感器任务。
- 安静阶段：32 个窗口、12,800 个固件采样点。RMS/中心化标准差/峰值的 p95
  分别为 `0.00001648`、`0.00001646`、`0.00032967`；30/32 个窗口全零。
- 持续参考声阶段：手机位于麦克风前约 10–15 cm，以固定中等音量持续播放；
  同样采集 32 个窗口、12,800 个固件采样点。三项 p95 均为 `0`，仅 1/32
  个窗口出现极小非零值。
- 比较结论为 `no_reliable_sound_response`、
  `suitable_for_relative_room_noise=false`。持续参考声没有形成高于安静环境的
  RMS、中心化标准差或峰值响应；当前 AO 通路不能作为可靠教室噪声指标。
- 没有生成或启用 `HW485_RELATIVE_CALIBRATION_PATH`，也没有放宽标定门槛。
  两份诊断文件权限为 600，只包含分位数、最大值、非零窗口数和计数，不含
  音频、ADC 序列或逐窗口值。
- 诊断前后 `dashboard-bridge.env` 与生产固件源码 SHA-256 均保持不变，展示桥
  为 `active`、`NRestarts=0`；MLX90640、HW-486、DHT11 均继续为 `ok`，
  32×24 热图持续刷新，因此未触发回滚。
- 在修复或替代声音输入前，不得把全零值解释为“已确认安静”。若继续使用
  HW-485，下一步应单独验证模块 `DO` 阈值输出或供电/接线；任何降级方案必须
  明确标记为声音活动事件代理，不能声称为 RMS 或 dB。

### Windows 麦克风替代路径

- 配置：`config/esp32-hub-windows-mic.example.yaml`。ESP32 继续提供
  MLX90640、HW-486 和 DHT11，只有声音改用 `RemoteSoundFeatureDriver`。
- Pi 接收端固定绑定 `127.0.0.1:8766`，非回环地址会在启动前被拒绝；
  Windows 通过 `ssh -L 18766:127.0.0.1:8766` 访问。
- 内部负载严格限制为 UUID、房间/设备、UTC 时间、窗口长度和
  `rms/std/peak`；未知字段、非有限值、过期/未来数据、原始音频声明、
  绝对 dB 声明和幂等冲突均拒绝。
- `PSSA_REMOTE_SOUND_TOKEN` 必须是至少 24 个非空白字符的随机秘密，只存在于
  Pi 权限 600 的环境文件与 Windows 当前进程环境，不进入 Git 或日志。
- Windows 代理默认 16 kHz、单声道、1 秒窗口。每个缓冲区在计算后立即释放，
  不创建音频文件；控制台只打印 sample ID、计数、溢出和错误类型。
- 摘要超过 4 秒不会进入窗口，8 秒未收到新摘要时声音为 `offline`，热成像、
  相对光照和温湿度继续运行。该路径为相对测量，始终
  `calibrated_db=false`。
- Windows 麦克风授权、设备选择、动态响应和端到端短时 smoke 已完成。长期采集
  时仍需在 Windows 保持代理进程运行；代理不运行时系统自动回到三传感器模式。

### 2026-07-23 Windows 麦克风 smoke

- Windows 默认输入确认为设备 1：`麦克风阵列 (Realtek(R) Audio)`；系统与
  用户麦克风权限均为 `Allow`。
- Pi 接收器仅监听 `127.0.0.1:8766`，Windows 通过本机
  `127.0.0.1:18766` SSH 转发；环境文件权限为 600，服务
  `active/enabled`、`NRestarts=0`。
- 当前环境 10 个窗口全部发送成功、0 输入溢出。原始归一化 RMS 的中位数为
  `0.00002038`、p95 为 `0.00451765`、最大值为 `0.00733917`；峰值中位数
  `0.00018311`、p95 `0.03591003`、最大值 `0.05725098`，证明持续声强输入
  有明显动态响应。
- 12 秒并发链路 smoke 为 12/12 摘要成功、0 溢出、agent 退出码 0、stderr
  为空。代理运行时后端观察到 `sound=ok`、相对 RMS 非空、相对峰值
  `0.483644`，同时 `thermal=ok`、`environment=ok`。
- 代理停止后 Pi 在 8 秒后把声音变为 `offline`；考虑 5 秒 Observation 发布
  周期，后端最迟约 13 秒显示该状态。桥接层会把声音 RMS/峰值清为 `null`，
  不复用旧值。闭环实测最终为 `sound=offline`、两项声音值均为 `null`，
  `thermal=ok`、`environment=ok`。
- 输出使用固定对数相对曲线增强可见度，始终
  `calibrated_db=false`。它足以替代无响应的 HW-485 做相对教室噪声输入，
  但笔记本位置和 Windows 增益设置改变后需重新验证。

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

# HW-485 替代路径：Pi 服务使用 windows-mic 配置，Windows 经 SSH 隧道发送
export PSSA_REMOTE_SOUND_TOKEN='<random-secret>'
python scripts/probe_sensors.py \
  --config config/esp32-hub-windows-mic.example.yaml

# Windows PowerShell（先建立隧道）
ssh -N -L 18766:127.0.0.1:8766 pi@PI_IP
python scripts/stream_remote_sound.py --list-devices
python scripts/stream_remote_sound.py

# 相对标定分阶段命令；每次独占串口前必须停止展示桥，完成后立即恢复
python scripts/calibrate_light.py capture-dark \
  --config config/esp32-hub.example.yaml \
  --output ~/.config/pssa/calibration/hw486-dark-staging.json
python scripts/calibrate_light.py capture-bright \
  --config config/esp32-hub.example.yaml \
  --staging ~/.config/pssa/calibration/hw486-dark-staging.json \
  --output ~/.config/pssa/calibration/hw486-relative.json
python scripts/calibrate_light.py status \
  --profile ~/.config/pssa/calibration/hw486-relative.json \
  --device-id pi5-a

# 不保存数据的 HW-485 串口/统计预检
python scripts/calibrate_sound.py preflight \
  --config config/esp32-hub.example.yaml

# HW-485 固件高频窗口诊断；只保存分位数等汇总，不刷固件、不改协议
python scripts/diagnose_sound.py capture \
  --config config/esp32-hub.example.yaml \
  --label quiet \
  --output ~/.config/pssa/diagnostics/hw485-quiet.json
python scripts/diagnose_sound.py capture \
  --config config/esp32-hub.example.yaml \
  --label reference \
  --output ~/.config/pssa/diagnostics/hw485-reference.json
python scripts/diagnose_sound.py compare \
  --quiet ~/.config/pssa/diagnostics/hw485-quiet.json \
  --reference ~/.config/pssa/diagnostics/hw485-reference.json \
  --device-id pi5-a

# 分阶段声音测试标定
python scripts/calibrate_sound.py capture-quiet \
  --config config/esp32-hub.example.yaml \
  --output ~/.config/pssa/calibration/hw485-quiet-staging.json
python scripts/calibrate_sound.py capture-reference \
  --config config/esp32-hub.example.yaml \
  --staging ~/.config/pssa/calibration/hw485-quiet-staging.json \
  --output ~/.config/pssa/calibration/hw485-relative-trial.json
python scripts/calibrate_sound.py status \
  --profile ~/.config/pssa/calibration/hw485-relative-trial.json \
  --device-id pi5-a

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

- `sample_data/real_two_person_v1/` 已加入两份 2026-07-23 去身份化真实会话：
  `discussion_allowed` 和 `not_recommended_noisy_or_crowded` 各9个窗口。两份
  会话均 `valid=true`，共包含88帧 MLX90640 数据；数据清单、人工标签和训练
  使用边界见 [`REAL_DATASET_GUIDE.md`](REAL_DATASET_GUIDE.md)。
- 当前模块 2 只提供确定性规则基线重标定，不提供完整的多会话 Random Forest
  训练。真实样本只能用于接口/特征验证和声音阈值锚定；仍需补齐另外两个标签
  并由模块 2 实现按 `session_id` 分组的混合训练与真实独立测试。
- 当前 HW-485 使用 3V3 供电，`AO` 直连 GPIO34，`DO` 不接。若改回 5V，必须先增加限压并测量 GPIO34 输入。
- ESP32 生产固件已经以约 4 kHz、每窗 400 点采样 HW-485；高频诊断只读取
  既有 RMS、中心化标准差和峰值汇总，不刷写固件、不保存逐窗口值。诊断前后
  必须复核 MLX90640、HW-486、DHT11 和展示桥服务；异常时停止后续步骤并恢复
  诊断前服务配置。
- HW-485 的相对 profile 只适用于当前设备、模块电位器、供电、安装位置和
  环境；任一条件变化后需要重新测试。它不会产生跨设备可比的 dB。
- HW-486 两点方案是当前房间和设备的相对标尺，不是跨设备可比的 lux；环境、
  安装角度或传感器改变后应重新采集暗亮锚点。
- 标定 profile 必须匹配 `device_id`，暗亮中位数至少相差 64 ADC count。展示桥
  通过 `HW486_RELATIVE_CALIBRATION_PATH` 启用；删除变量并重启即可安全回退。
- DHT11 实际读取间隔不得快于约 2 秒。
- `smooth` 和 `live_max` 仅是实验档位，未纳入最终生产验收。
- GPIO RGB LED 或 micro:bit 可作为展示扩展；默认 `log` 指示器与五种状态映射已通过测试。
- `/dev/ttyUSB0` 是动态名称。运行配置始终使用 `/dev/serial/by-id/`。

## 外部代码与许可证

- MLX90640 通过 MIT 许可的 Adafruit 公开 API 使用，未复制其底层源码。
- LD2450 兼容解析器参考 MIT 许可资料并重新实现，版本见 `THIRD_PARTY_NOTICES.md`。
- 未复制检索到的 GPL/AGPL 项目源码。项目根许可证仍需维护者确认。

Pi 地址发现、Mac 后端恢复、无 Git 部署副本同步、systemd 安装、实时页面验收和会话打包的完整顺序见 [`../../docs/RASPBERRY_PI_CODEX_HANDOFF.md`](../../docs/RASPBERRY_PI_CODEX_HANDOFF.md)。
