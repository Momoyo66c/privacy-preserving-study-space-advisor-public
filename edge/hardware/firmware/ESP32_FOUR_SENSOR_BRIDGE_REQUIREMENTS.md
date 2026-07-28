# ESP32 四传感器采集桥接需求

> 本文档可直接交给 Codex 作为实现任务。目标硬件为 WeMos D1 R32
> （ESP32）、HW-485 声音模块、HW-486 光敏模块、HW-507/DHT11
> 温湿度模块和 MLX90640 32 × 24 热阵列。

## 1. 实现目标

在 `edge/hardware/` 范围内实现一条完整、可测试的本地采集链路：

```text
HW-485 / HW-486 / HW-507 / MLX90640
                  |
                  v
          WeMos D1 R32 (ESP32)
                  |
          USB Serial / JSON Lines
                  |
                  v
              Raspberry Pi 5
                  |
        study_space_hardware 驱动接口
```

ESP32 负责读取四个传感器、在内存中生成声音统计量，并通过 USB
串口把数据交给 Raspberry Pi。Raspberry Pi 负责添加 UTC 时间、验证数据、
维护传感器健康状态，并接入现有 `SensorDriver`/采样窗口流程。

本任务不得修改共享字段、枚举、HTTP 端点或隐私原则。缺失或异常数据必须
标记为 degraded/offline，不得伪造正常值。

## 2. 硬件识别与限制

照片中的模块按 PCB 丝印和器件外观识别如下：

| 模块 | 信号类型 | 可以得到的数据 | 不能直接声称的数据 |
|---|---|---|---|
| HW-485 | 模拟声音包络 `AO`，另有阈值输出 `DO` | 相对声音 RMS、标准差、峰值 | 未校准的分贝值、原始语音 |
| HW-486 | 光敏电阻分压，模拟输出 `S` | ADC 原始值、经现场标定的相对亮度 | 未标定的 lux |
| HW-507 / DHT11 | 单总线数字信号 `S` | 摄氏温度、相对湿度 | 高速采样 |
| MLX90640 | I²C，默认地址 `0x33` | 32 × 24 绝对温度矩阵 | RGB 图像、身份信息 |

`HW-485`、`HW-486`、`HW-507` 是常见卖家/PCB 编号，不应把编号当作
芯片厂商型号。HW-507 照片中的蓝色器件本体为 DHT11。

HW-486 只能作为亮度代理值。没有使用参考照度计做标定以前：

- 串口协议必须输出 `light_adc_raw` 和可选 `light_normalized`；
- Raspberry Pi 端必须让共享字段 `light_lux` 保持 `null`；
- 必须在 warning 中注明 `hw486_uncalibrated_light_proxy`；
- 禁止把 ADC 值重命名为 lux。

## 3. 断电接线要求

### 3.1 固定 GPIO 分配

所有接线必须在 ESP32 和传感器断电时完成。所有模块与 ESP32 必须共地。

| 传感器丝印 | 连接到 WeMos D1 R32 | 说明 |
|---|---|---|
| HW-485 `+` | `5V` | 仅给 HW-485 使用 5V |
| HW-485 `G` | `GND` | 共地 |
| HW-485 `AO` | 经 10 kΩ/10 kΩ 分压后接 `GPIO34` | ADC1，只输入 |
| HW-485 `DO` | 不连接 | 5V 供电时禁止直接接 ESP32 |
| HW-486 `+` | `3V3` | 不使用 5V |
| HW-486 `-` | `GND` | 共地 |
| HW-486 `S` | `GPIO35` | ADC1，只输入 |
| HW-507 `+` | `3V3` | 照片正面、排针向下时为中间脚 |
| HW-507 `-` | `GND` | 照片正面、排针向下时为右脚 |
| HW-507 `S` | `GPIO27` | 照片正面、排针向下时为左脚 |
| MLX90640 `VIN` | `3V3` | 以 PCB 丝印为准，不按照片位置猜测 |
| MLX90640 `GND` | `GND` | 共地 |
| MLX90640 `SDA` | `GPIO21` | I²C 数据 |
| MLX90640 `SCL` | `GPIO22` | I²C 时钟 |

HW-485 照片正面、排针向下时，四脚从左到右为
`AO`、`G`、`+`、`DO`。HW-486 照片正面、排针向下时，三脚从左到右为
`-`、`+`、`S`。若实物丝印与本文不一致，必须以实物丝印和万用表检查结果
为准，停止上电并更新文档。

### 3.2 HW-485 必需分压

HW-485 使用 5V 供电时，`AO` 可能高于 ESP32 可接受范围。必须按下图分压，
不得把 `AO` 或 `DO` 直接接入 ESP32：

```text
HW-485 AO ---- 10 kΩ ----+---- GPIO34
                         |
                       10 kΩ
                         |
                        GND
```

该分压把最坏情况下的 5V 降为约 2.5V。固件将 GPIO34 配置为
12 位 ADC、`ADC_ATTEN_DB_11`。ESP32 GPIO 仍按 3.3V 逻辑设计，
衰减配置不能使引脚具备 5V 耐受能力。

### 3.3 上电前检查

首次通电前必须完成：

1. 断电状态检查 `5V` 与 `GND`、`3V3` 与 `GND` 无短路。
2. 确认 HW-485 AO 分压中点才连接 GPIO34。
3. 确认 HW-486 和 HW-507 由 3.3V 供电。
4. 确认 MLX90640 的 `SDA`/`SCL` 没有接反，且上拉电压不是 5V。
5. ESP32 只通过自己的 Micro-USB 口连接 Raspberry Pi；不要再并接
   ESP32 的裸 UART TX/RX，也不要从外部电源反向灌入 USB 5V。

## 4. ESP32 固件要求

### 4.1 文件与构建

保留现有串口 smoke sketch，新建：

```text
edge/hardware/firmware/esp32_sensor_bridge/
|-- esp32_sensor_bridge.ino
|-- protocol.h
|-- sensor_manager.h
`-- sensor_manager.cpp
```

允许在不牺牲可读性的情况下调整拆分方式。固件使用仓库现有 Arduino CLI
流程，目标 FQBN 为 `esp32:esp32:esp32`。依赖必须在
`edge/hardware/firmware/README.md` 中写明安装命令，优先使用：

- Adafruit `DHT sensor library` 读取 DHT11；
- `Adafruit Unified Sensor`，作为 DHT 库依赖；
- SparkFun/Melexis MLX90640 Arduino 库；
- ESP32 Arduino Core 自带 `Wire` 和 ADC API。

不得连接 Wi-Fi、Bluetooth、云服务或 NTP。不得在源码中加入 SSID、
密码、令牌或固定设备路径。

### 4.2 采样配置

使用以下默认值，并将常量集中定义：

| 项目 | 默认值 |
|---|---:|
| USB 串口 | 460800 baud |
| HW-485 ADC | GPIO34、12 bit、11 dB attenuation |
| HW-485 ADC 采样率 | 不低于 4000 samples/s |
| 声音统计输出率 | 4 Hz |
| HW-486 ADC | GPIO35、12 bit、11 dB attenuation |
| 光敏输出率 | 1 Hz |
| DHT11 数据脚 | GPIO27 |
| DHT11 读取周期 | 不短于 2000 ms |
| MLX90640 I²C | SDA 21、SCL 22、400 kHz、地址 `0x33` |
| MLX90640 帧率 | 默认 2 Hz，可降级为 1 Hz |

不能用阻塞式 DHT11 读取或大段串口输出长期阻塞声音采样。可以使用
基于 `millis()`/`micros()` 的非阻塞调度或独立 FreeRTOS task，但必须避免
并发访问同一 I²C/Serial 对象造成竞态。

### 4.3 声音隐私与统计

HW-485 的 ADC 短缓冲区只能驻留在 RAM。每个统计周期应：

1. 采集固定长度 ADC 样本；
2. 计算并去除直流均值；
3. 计算归一化 `rms`、`std` 和 `peak`，范围限制为 0 至 1；
4. 清除/复用缓冲区；
5. 只发送统计结果。

严禁：

- 通过串口输出逐点 ADC 音频样本；
- 写 WAV、PCM、MP3、原始数组或可恢复音频；
- 在日志中打印声音缓冲区；
- 把相对强度标成 dB。

每条声音摘要必须包含 `raw_audio_persisted: false` 和
`measurement_source: "hw485_adc_relative"`。

### 4.4 光敏代理值

HW-486 每次读取至少进行 16 次 ADC 采样并取中位数或截尾均值，以降低噪声。
输出：

- `light_adc_raw`: 0 至 4095；
- `light_normalized`: 0 至 1，可通过固件常量配置方向反转；
- `measurement_source: "hw486_ldr_proxy"`；
- `calibrated_lux: false`。

必须在真实硬件上分别遮住传感器和用灯照射，确认数值方向。方向未确认时，
仍可输出原始值，但不得输出误导性的归一化“越大越亮”语义。

### 4.5 DHT11

- 使用 GPIO27 双向时序读取，不得改用 GPIO34 至 GPIO39。
- 连续两次真实读取间隔不得少于 2 秒。
- 读取失败、校验失败、NaN 或超范围时保留最近成功值及其年龄，但当前健康
  状态必须 degraded；超过 10 秒没有成功读数时标为 offline。
- 正常输出 `temperature_c` 和 `humidity_pct`。
- Raspberry Pi 真实配置中的 climate 期望采样率应改为 0.5 Hz，不得复制
  缓存值伪装成新的 1 Hz 物理读数。

### 4.6 MLX90640

- 初始化 I²C 地址 `0x33`，读取并验证完整 32 × 24 共 768 个温度值。
- 每帧拒绝长度错误、NaN、Infinity 和超出配置范围的温度。
- I²C 失败不得阻断声音、光敏或温湿度输出；连续失败进入 degraded/offline。
- 完整热帧只通过本地 USB 串口交给 Raspberry Pi 的边缘流程，不得进入普通
  日志、后端 Observation、推荐上下文或 LLM。
- 固件不进行人员身份识别、面部处理或跨窗口追踪。

## 5. 串口协议

使用 UTF-8 JSON Lines：每条消息是单行 JSON，以 `\n` 结束。禁止 pretty
print。单行最大 32768 字节。所有消息必须包含：

```json
{
  "schema_version": "1.0",
  "protocol": "pssa-esp32-sensors/1",
  "type": "sample",
  "seq": 1,
  "captured_monotonic_ms": 12345
}
```

ESP32 没有可信 UTC 时钟，因此只发送启动后的单调毫秒数；Raspberry Pi
收到后使用同一时钟映射添加 UTC。禁止用编译时间伪造采样 UTC。

### 5.1 摘要消息

```json
{
  "schema_version": "1.0",
  "protocol": "pssa-esp32-sensors/1",
  "type": "sample",
  "seq": 15,
  "captured_monotonic_ms": 5000,
  "sound": {
    "health": "ok",
    "rms": 0.18,
    "std": 0.04,
    "peak": 0.41,
    "raw_audio_persisted": false,
    "measurement_source": "hw485_adc_relative"
  },
  "light": {
    "health": "degraded",
    "light_adc_raw": 2170,
    "light_normalized": 0.53,
    "calibrated_lux": false,
    "measurement_source": "hw486_ldr_proxy"
  },
  "climate": {
    "health": "ok",
    "temperature_c": 24.8,
    "humidity_pct": 61.0,
    "measurement_source": "hw507_dht11"
  },
  "warnings": ["hw486_uncalibrated_light_proxy"]
}
```

字段缺失时使用 JSON `null` 和 warning，禁止用 `0` 伪装缺失。

### 5.2 热帧消息

```json
{
  "schema_version": "1.0",
  "protocol": "pssa-esp32-sensors/1",
  "type": "thermal_frame",
  "seq": 16,
  "captured_monotonic_ms": 5250,
  "width": 32,
  "height": 24,
  "temperature_c": [23.41, 23.45, 23.39],
  "health": "ok"
}
```

实际 `temperature_c` 必须有 768 项；上例只为缩略展示。温度最多保留两位
小数以控制带宽。固件应直接流式写 JSON 数组，避免构建不必要的多份大对象。
普通 INFO/ERROR 日志不得包含该数组。

### 5.3 启动与状态消息

启动成功后发送：

```json
{"schema_version":"1.0","protocol":"pssa-esp32-sensors/1","type":"ready","firmware_version":"0.1.0","seq":0,"captured_monotonic_ms":0}
```

至少每 5 秒发送一次 `status`，包含四个传感器的健康状态、连续失败次数、
最近成功读取年龄、空闲堆内存和序号。状态消息不得包含热帧或声音原始样本。

序号必须对所有消息全局递增。Raspberry Pi 端检测到序号跳变时记录
`serial_sequence_gap` warning，但后续有效消息仍可恢复。

## 6. Raspberry Pi 适配要求

仅实现 ESP32 固件不足以适配当前软件。当前声音、光照、温湿度和 MLX90640
驱动分别假设 USB 音频、BH1750、AHTx0 和 Pi 直连 I²C，因此必须同步实现
本地串口桥。

### 6.1 单一串口所有者

新增一个 `Esp32SerialHub`，由它独占 `ESP32_PORT`：

- 只打开一次串口，禁止四个驱动分别打开同一设备；
- 后台读取并解析 JSON Lines；
- 验证协议版本、消息类型、有限数值、范围和热帧长度；
- 维护每类传感器的最新有效样本、接收 UTC 和单调时间；
- 处理超长行、无效 UTF-8、损坏 JSON、未知字段、断线和重新连接；
- 可注入 fake serial 和 clock，测试时不要求真实硬件。

在 hub 上提供四个轻量驱动/reader，返回现有 `SensorSample`：

| 数据 | `SensorSample.source` |
|---|---|
| HW-485 | `esp32-hw485-relative-sound` |
| HW-486 | `esp32-hw486-light-proxy` |
| HW-507 | `esp32-hw507-dht11` |
| MLX90640 | `esp32-mlx90640` |

HW-486 未标定时，采样窗口中的 `environment.light_lux` 必须为 `null`，
并带 warning。不得为了通过 Schema 或模型测试伪造 lux。

### 6.2 配置

增加不含机器绝对路径的示例配置：

```yaml
esp32_bridge:
  enabled: true
  port: ${ESP32_PORT}
  baud_rate: 460800
  timeout_s: 1.0
  stale_after_s: 10
  reconnect_delay_s: 1.0

sensors:
  thermal:
    source: esp32_serial
    sample_rate_hz: 2
  sound:
    source: esp32_serial
    sample_rate_hz: 4
  light:
    source: esp32_serial
    sample_rate_hz: 1
    options:
      calibrated_lux: false
  climate:
    source: esp32_serial
    sample_rate_hz: 0.5
```

部署时使用：

```bash
export ESP32_PORT=/dev/serial/by-id/REPLACE_WITH_ESP32_DEVICE
```

不得把 ESP32 端口填入 `RADAR_PORT`。LD2450 若同时使用，必须有独立
USB-TTL 和独立稳定设备路径。

## 7. 测试与验收

### 7.1 自动测试

至少覆盖：

- 摘要消息和 768 项热帧的正常解析；
- 无效 JSON、未知协议、非有限数值、越界值和错误数组长度；
- 序号跳变、超长行、读取超时、串口断开与恢复；
- 单一 hub 被多个逻辑驱动复用且只打开一次串口；
- DHT11 stale/offline 状态；
- HW-486 未标定时 `light_lux=null`；
- 声音输出只有统计量，仓库和测试输出中不存在原始音频文件；
- 单个传感器失败不影响其他传感器继续产生样本；
- 固件编译和现有模块 1 pytest/compileall 全部通过。

### 7.2 树莓派命令

```bash
ls -l /dev/serial/by-id/
arduino-cli board list
esptool --port /dev/ttyUSB0 chip-id

arduino-cli compile \
  --fqbn esp32:esp32:esp32 \
  edge/hardware/firmware/esp32_sensor_bridge

arduino-cli upload \
  --fqbn esp32:esp32:esp32 \
  --port /dev/ttyUSB0 \
  edge/hardware/firmware/esp32_sensor_bridge

python -m serial.tools.miniterm \
  /dev/serial/by-id/REPLACE_WITH_ESP32_DEVICE \
  460800
```

`/dev/ttyUSB0` 只可用于已通过 `esptool chip-id` 确认身份的当次烧录；
长期运行必须使用 `/dev/serial/by-id/`。

### 7.3 真实硬件验收

1. 单独连接并探测每个传感器，再连接全部四个。
2. 遮挡/照亮 HW-486，记录 ADC 方向，不宣称 lux。
3. 安静、说话和拍手时 HW-485 统计量有明显但有限的变化。
4. DHT11 连续运行时真实读取间隔不短于 2 秒。
5. MLX90640 每帧恰好 768 个有限温度值，I²C 地址为 `0x33`。
6. 连续运行至少 10 分钟，无重启、内存持续下降或未处理异常。
7. 逐个拔掉传感器时系统进入 degraded/offline，其他传感器继续工作。
8. Raspberry Pi 能生成现有 5 秒 `sensor_window`；未标定光照为 `null`。
9. 本地采集目录、日志和串口摘要中不存在原始音频。
10. 完整热帧不进入后端 Observation、推荐请求或普通日志。

## 8. Codex 完成任务时必须交付

- ESP32 四传感器固件及版本号；
- Raspberry Pi `Esp32SerialHub` 和四类数据适配；
- 示例配置与依赖安装、编译、烧录、运行说明；
- fake serial 单元测试和相关集成测试；
- 更新 `edge/hardware/README.md`、`firmware/README.md` 和
  `MODULE1_HANDOFF.md`；
- 运行过的命令、测试结果和仍需实物确认的限制；
- 一份按 `HARDWARE_SMOKE_TEST.md` 填写的真实硬件记录；没有真实执行时
  必须明确标为 pending，禁止伪造。

实现前必须阅读：

1. `docs/module-specs/00_SHARED_CONTRACT.md`
2. `docs/module-specs/01_SENSOR_EDGE_HARDWARE.md`
3. `edge/hardware/README.md`
4. `CONTRIBUTING.md`

不得扩展到模块 2、后端或前端，也不得修改共享契约来迁就实现。

## 9. 实现参考

- Espressif Arduino ESP32 ADC API：
  <https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html>
- Espressif ESP32 GPIO/受限引脚说明：
  <https://docs.espressif.com/projects/arduino-esp32/en/latest/boards/ESP32-DevKitC-1.html>
- Melexis MLX90640 官方数据手册：
  <https://www.melexis.com/-/media/files/documents/datasheets/mlx90640-datasheet-melexis.pdf>
- ASAIR DHT11 数据手册：
  <https://www.aosong.com/userfiles/files/media/DHT11%E6%B8%A9%E6%B9%BF%E5%BA%A6%E4%BC%A0%E6%84%9F%E5%99%A8%E8%AF%B4%E6%98%8E%E4%B9%A6%EF%BC%88%E4%B8%AD%EF%BC%89%20A0-1208.pdf>
- Adafruit DHT Arduino 库：
  <https://github.com/adafruit/DHT-sensor-library>
- SparkFun MLX90640 Arduino 库和示例：
  <https://github.com/sparkfun/Qwiic_IR_Array_MLX90640>
