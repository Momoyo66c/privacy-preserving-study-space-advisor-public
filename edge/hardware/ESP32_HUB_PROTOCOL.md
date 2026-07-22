# ESP32 Sensor Hub 串口协议

本文是 ESP32 固件实现者和 Raspberry Pi 驱动维护者使用的协议参考。ESP32 Sensor Hub 通过一条 USB 串口复用热阵列、声音统计、光照和温湿度样本。协议仍保留可选雷达消息，供兼容测试或未来扩展使用；最终四传感器生产固件不启用雷达。Raspberry Pi 将本地消息转换为现有 `SensorDriver` 样本；模块 1 的窗口格式和跨模块契约不变。

## 适用边界

- 串口格式固定为 8 数据位、无校验、1 停止位。`analytics` 和 `smooth`
  使用 `460800 baud`；`live_max` 使用 `921600 baud`。固件和 Pi 主机配置
  必须使用相同波特率。
- 多字节整数和浮点数使用小端序。
- 每个编码帧以 `0x00` 结束。
- 帧内容使用 COBS 编码，因此编码内容本身不包含 `0x00`。
- 单帧负载最多 2048 字节。
- CRC32 使用 IEEE 多项式，与 Python `zlib.crc32` 一致。
- 协议只在 ESP32 和 Raspberry Pi 之间传输，不替代共享 `sensor_window` 契约。

## 解码后的帧格式

| 偏移 | 长度 | 字段 | 约束 |
|---:|---:|---|---|
| 0 | 4 | `magic` | ASCII `PSSA` |
| 4 | 1 | `version` | 当前固定为 `2`；版本 1 的光照负载不兼容 |
| 5 | 1 | `message_type` | 见消息类型表 |
| 6 | 4 | `sequence` | 全局无符号 32 位序号，允许自然回绕 |
| 10 | 4 | `device_uptime_ms` | ESP32 启动后的无符号毫秒数 |
| 14 | 2 | `payload_length` | 0 至 2048 |
| 16 | N | `payload` | 消息类型定义的负载 |
| 16 + N | 4 | `crc32` | 覆盖从 `magic` 到负载末尾 |

发送流程：构造解码帧、追加 CRC32、执行 COBS 编码、追加单个 `0x00`。接收端遇到损坏帧时只丢弃当前帧，并从下一个 `0x00` 继续同步。

## 消息类型与负载

| 类型 | 名称 | 负载 |
|---:|---|---|
| `0x01` | `HEARTBEAT` | `uint32 capability_mask`、`uint32 dropped_samples` |
| `0x02` | `HEALTH` | `uint8 sensor_type`、`uint8 status`、`uint16 error_code`、`uint32 event_count` |
| `0x10` | `THERMAL` | `uint8 width`、`uint8 height`、随后为 `width*height` 个 `int16` 摄氏度百分值 |
| `0x11` | `RADAR` | 可选兼容消息：一份完整的 30 字节 LD2450 上报帧；生产禁用 |
| `0x12` | `SOUND` | `float32 rms`、`float32 std`、`float32 peak`、`uint16 chunk_frames` |
| `0x13` | `LIGHT` | `uint16 adc_raw`、`float32 normalized`、`float32 calibrated_lux`、`uint8 flags` |
| `0x14` | `CLIMATE` | `float32 temperature_c`、`float32 humidity_pct` |

`capability_mask` 从最低位开始依次表示 thermal、radar、sound、light 和 climate。能力位只说明该传感器已成功初始化，不得把缺失设备标记为可用。

`HEALTH.status` 固定为 `0=ok`、`1=degraded`、`2=offline`。`sensor_type` 使用对应的传感器消息类型值。主机收到 `offline` 或能力位撤销后必须清空该传感器的旧队列，避免把断开前的样本当成当前数据。

### 热阵列

MLX90640 必须发送 `width=32`、`height=24` 和恰好 768 个温度值。每个值按摄氏温度乘以 100 后四舍五入为 `int16`。例如 `24.37°C` 编码为 `2437`。这种表示在传感器精度以内，并把每个热帧负载固定为 1538 字节，与具体发布帧率无关。

性能档位只改变传感器子页频率、完整帧发布频率、I²C 时钟和串口波特率，
不改变本协议的热帧结构或协议版本。默认 `analytics` 发布 2 FPS；
`smooth` 计划发布 16 FPS；`live_max` 计划发布 32 FPS。后两档在完成实机
丢帧、噪声、资源和其他传感器公平性验证前均属于实验模式。

### 雷达

该消息只属于可选兼容路径。启用时，ESP32 只对 LD2450 的 30 字节上报帧做边界检查，不改变字段，不插入日志；Raspberry Pi 使用现有解析器完成目标字段验证和窗口内匿名化。最终生产配置禁用此能力，窗口应输出 `radar.health=not_configured`、0 样本和空轨迹。

### 声音

当前声音源是 HW-485 的分压后模拟输出。ESP32 去除 ADC 直流分量，只发送归一化 RMS、标准差、峰值和样本数；这些数值是相对声音活动强度，不是未经校准的 dB。协议没有原始 ADC、PCM 或波形消息类型。固件不得把原始声音写入 Flash、串口日志或文件。

### 光照代理值

当前光照源是 HW-486 LDR 模块，不是数字照度计。`adc_raw` 范围为 0 至 4095，`normalized` 范围为 0 至 1。`flags` bit 0 表示 `calibrated_lux` 是否有效；其余位必须为 0。未用参考照度计标定时，固件必须清除 bit 0，Pi 必须输出 `light_lux=null`、`calibrated_lux=false` 和 `hw486_uncalibrated_light_proxy`，不得把 ADC 值冒充 lux。

### 温湿度

当前温湿度源是 HW-507 模块上的 DHT11，至少间隔约 2 秒读取。`CLIMATE` 的两个浮点字段保持不变，Pi 端测量源标记为 `dht11`。

## 时间和序号

- `sequence` 对所有消息类型共用，用于发现丢包、重复和乱序。
- `device_uptime_ms` 用于排序和诊断，不直接作为 UTC 时间。
- Raspberry Pi 在完整帧到达时记录本机单调时间和 UTC 时间，再生成现有 `SensorSample`。
- ESP32 重启后序号和启动时间可以归零；主机必须把回退识别为设备重启，而不是长期乱序。

## 黄金向量

以下帧用于固件和 Python 编码器的一致性测试：

```text
message_type     = 0x01 HEARTBEAT
sequence         = 1
device_uptime_ms = 1000
payload          = 1f00000000000000
```

包含结尾分隔符的完整编码十六进制：

```text
0850535341020101010103e803010208021f0101010101010535d2de7c00
```

## 接收端失败处理

| 情况 | 行为 |
|---|---|
| COBS 无效 | 丢弃当前帧，增加 `invalid_frames` |
| CRC32 不匹配 | 丢弃当前帧，增加 `checksum_errors` |
| 协议版本不支持 | 丢弃当前帧，增加 `version_errors` |
| 编码帧超过边界 | 丢弃到下一个 `0x00`，保持内存有界 |
| 未知消息类型 | 保留协议级前向兼容，由解复用层忽略并计数 |
| 序号跳变 | 接受后续有效帧，同时记录缺失数量 |
| USB 断开 | 关闭失效句柄并按有限间隔重连 |

协议实现和黄金向量测试位于：

- `src/study_space_hardware/esp32_protocol.py`
- `tests/test_esp32_protocol.py`
