# 四传感器型号识别与接口清单

本文档依据实物照片中的 PCB 丝印、器件外观和项目已确认的采购名称整理。
它用于接线核对和软件开发输入，不替代对应批次卖家的原理图或数据手册。

## 1. 识别结论

| 照片 | 识别型号 | 传感器用途 | 电气接口 | 识别置信度 |
|---|---|---|---|---|
| 图 1 | HW-507 模块，传感器本体为 DHT11 | 温度、相对湿度 | 三针单总线数字接口 | 高；DHT11 外观和三针模块明确，照片未显示 `HW-507` PCB 编号 |
| 图 2 | HW-485 | 相对声音强度 | 模拟输出 `AO` + 阈值数字输出 `DO` | 高；PCB 清楚印有 `HW-485` |
| 图 3 | HW-486 | 环境亮度代理值 | 模拟输出 `S` | 高；PCB 清楚印有 `HW-486` |
| 图 4 | MLX90640 breakout | 32 × 24 热阵列 | I²C | 中高；型号由采购信息确认，照片外观和四针 I²C 丝印相符 |

图 4 无法仅凭当前照片确认：

- breakout 的生产厂家和具体板卡版本；
- 视场角是 55°、110° 还是其他版本；
- 板上是否包含稳压器、电平转换器和 I²C 上拉电阻；
- 镜头朝向与 32 × 24 数组行列方向。

这些信息不会改变基本 I²C 接口，但会影响热图方向、视场范围和供电容差，
应通过商品链接、包装标签或 PCB 背面照片继续核实。

## 2. HW-507 / DHT11 温湿度模块

### 2.1 识别特征

- 蓝色栅格塑料外壳为典型 DHT11。
- 模块为三针版本。
- PCB 上可见 `103` 电阻，通常作为约 10 kΩ 数据线上拉。
- 照片正面、蓝色传感器朝上、排针朝下时，可见左侧 `S` 和右侧 `-`。

### 2.2 引脚

照片正面、蓝色传感器朝上、排针朝下：

| 从左到右 | 丝印 | 功能 | 计划连接 |
|---:|---|---|---|
| 1 | `S` | 单总线数字数据 | ESP32 `GPIO27` |
| 2 | `+` | 电源正极 | ESP32 `3V3` |
| 3 | `-` | 地 | ESP32 `GND` |

中间脚的 `+` 在照片中被排针部分遮挡，但由两侧丝印和常见模块布局推断。
首次上电前仍应查看实物边缘丝印或用万用表确认地脚。

### 2.3 软件接口

- 协议：DHT 单总线时序，不是 UART、I²C 或普通持续数字电平。
- 输出：`temperature_c`、`humidity_pct`。
- 读取周期：连续两次真实读取至少间隔约 2 秒。
- GPIO27 必须能在输出启动脉冲和输入响应之间切换。
- GPIO34 至 GPIO39 只能输入，因此不适合 DHT11。

### 2.4 当前软件兼容性

当前 Raspberry Pi `ClimateDriver` 面向 AHT20/AHTx0 I²C 传感器，不能直接读取
DHT11。使用本模块需要：

- ESP32 固件读取 DHT11；
- 通过 USB 串口输出温湿度；
- Raspberry Pi 串口桥把它转换为现有 `SensorSample`。

## 3. HW-485 声音模块

### 3.1 识别特征

- PCB 丝印为 `HW-485`。
- 使用驻极体麦克风、可调电位器和比较器电路。
- 同时提供模拟声音信号和可调阈值数字信号。

该模块只能用于相对声音活动强度，不能在未校准情况下提供声压级 dB。

### 3.2 引脚

照片正面、麦克风朝上、排针朝下，从左到右：

| 从左到右 | 丝印 | 功能 | 计划连接 |
|---:|---|---|---|
| 1 | `AO` | 模拟输出 | 经 10 kΩ/10 kΩ 分压后接 ESP32 `GPIO34` |
| 2 | `G` | 地 | ESP32 `GND` |
| 3 | `+` | 电源正极 | ESP32 `5V` |
| 4 | `DO` | 比较器阈值数字输出 | 暂不连接 |

### 3.3 电压保护

使用 5V 给 HW-485 供电时，`AO` 或 `DO` 可能高于 ESP32 的 3.3V
输入范围。`AO` 必须按以下方式分压：

```text
HW-485 AO ---- 10 kΩ ----+---- ESP32 GPIO34
                         |
                       10 kΩ
                         |
                        GND
```

`DO` 暂不使用，也不得直接连接 ESP32。ADC attenuation 只能调整测量范围，
不能让 GPIO 获得 5V 耐受能力。

### 3.4 软件接口

- 信号：GPIO34 上的模拟电压。
- ADC：ESP32 ADC1、12 bit、11 dB attenuation。
- 处理：短时采样后去除直流分量，计算相对 RMS、标准差和峰值。
- 单位：normalized/relative，不是 dB。
- 隐私：ADC 原始采样只可短暂存在 RAM，不得通过串口发送或写入文件。

### 3.5 当前软件兼容性

当前 `SoundLevelDriver` 使用 PortAudio/USB 音频输入，不会读取 ESP32 ADC。
需要 ESP32 在本地计算统计量，再由 Raspberry Pi 串口桥转换为：

```text
rms
std
peak
raw_audio_persisted=false
```

## 4. HW-486 光敏模块

### 4.1 识别特征

- PCB 丝印为 `HW-486`。
- 顶部为光敏电阻 LDR。
- 板上有固定电阻，与 LDR 构成模拟分压。
- 没有数字总线芯片和可调比较器。

### 4.2 引脚

照片正面、光敏电阻朝上、排针朝下，从左到右：

| 从左到右 | 丝印 | 功能 | 计划连接 |
|---:|---|---|---|
| 1 | `-` | 地 | ESP32 `GND` |
| 2 | `+` | 电源正极 | ESP32 `3V3` |
| 3 | `S` | 模拟分压输出 | ESP32 `GPIO35` |

使用 3.3V 供电后，`S` 可以直接进入 ESP32 ADC。不要将模块改用 5V 后仍把
`S` 直接连接 ESP32。

### 4.3 软件接口

- 信号：GPIO35 上的模拟电压。
- ADC：ESP32 ADC1、12 bit、11 dB attenuation。
- 基础输出：`light_adc_raw`，范围 0 至 4095。
- 可选输出：`light_normalized`，范围 0 至 1。
- 必须通过遮挡和照射试验确认数值方向；不同分压布局可能导致亮时升高或降低。

### 4.4 重要语义限制

HW-486 不是数字照度计。未经参考照度计标定，不得输出或填写 `light_lux`。

未标定阶段应使用：

```text
measurement_source=hw486_ldr_proxy
calibrated_lux=false
light_lux=null
warning=hw486_uncalibrated_light_proxy
```

### 4.5 当前软件兼容性

当前 `LightDriver` 面向 BH1750 I²C 照度计，并直接输出 lux。HW-486 不能直接
替换 BH1750 驱动，需要新增 ESP32 ADC 代理值适配，并允许共享窗口中的
`light_lux` 为 `null`。

## 5. MLX90640 热阵列

### 5.1 已确认特征

- 传感器分辨率：32 × 24，共 768 个热像素。
- 接口：I²C。
- 常见默认 7-bit 地址：`0x33`。
- 传感器本体使用约 3.3V 电源域。
- 当前 breakout 丝印可识别为 `VIN`、`GND`、`SCL`、`SDA`。

### 5.2 引脚

不根据照片的上下/左右位置猜测，直接按 PCB 丝印连接：

| 丝印 | 功能 | 计划连接 |
|---|---|---|
| `VIN` | 电源输入 | ESP32 `3V3` |
| `GND` | 地 | ESP32 `GND` |
| `SDA` | I²C 数据 | ESP32 `GPIO21` |
| `SCL` | I²C 时钟 | ESP32 `GPIO22` |

首次接线建议以 400 kHz I²C 开始。需要确认 breakout 的上拉电阻连接到
3.3V，而不是 5V。

### 5.3 软件接口

- ESP32 I²C 控制器：`Wire`，SDA 21、SCL 22。
- 地址：默认 `0x33`。
- 输出：每帧恰好 768 个有限浮点温度值。
- 校验：拒绝错误长度、NaN、Infinity 和配置范围外温度。
- 完整热帧只用于树莓派本地边缘处理或受控离线训练。
- 完整热帧不得进入后端 Observation、推荐上下文、LLM 或普通日志。

### 5.4 当前软件兼容性

当前仓库已经有 Raspberry Pi I²C 直连的 MLX90640 驱动。

有两种连接方式：

1. **低改动方案**：MLX90640 直接连接 Raspberry Pi I²C，继续使用现有驱动。
2. **四传感器 ESP32 方案**：MLX90640 连接 ESP32，再增加热帧串口协议和
   Raspberry Pi 串口热帧适配器。

第二种方案不会改变共享契约，但软件和串口带宽改动更大。

## 6. ESP32 控制板

照片中的控制板为 WeMos D1 R32，核心为经典 ESP32 模组，采用
Arduino UNO 外形排针。

本项目分配：

| ESP32 GPIO | 用途 | 说明 |
|---|---|---|
| GPIO34 | HW-485 `AO` | ADC1，只输入，必须经过分压 |
| GPIO35 | HW-486 `S` | ADC1，只输入 |
| GPIO27 | HW-507/DHT11 `S` | 可双向切换，适合 DHT 时序 |
| GPIO21 | MLX90640 `SDA` | I²C 数据 |
| GPIO22 | MLX90640 `SCL` | I²C 时钟 |

ESP32 使用 Micro-USB 与 Raspberry Pi 通信。部署时应使用
`/dev/serial/by-id/` 下的稳定路径识别设备，不应长期依赖
`/dev/ttyUSB0` 这一动态编号。

## 7. 接口总览

```text
HW-485 AO --分压--> GPIO34 --ADC----┐
HW-486 S ----------> GPIO35 --ADC----+
HW-507 S ----------> GPIO27 --DHT----+--> ESP32
MLX90640 SDA/SCL ---> GPIO21/22 I2C--┘      |
                                             |
                                      Micro-USB Serial
                                             |
                                             v
                                       Raspberry Pi 5
```

所有模块必须共地。首次整体上电前，应先逐个连接、逐个验证，再同时连接。

## 8. 软件适配结论

| 传感器 | 当前模块 1 是否可直接使用 | 所需动作 |
|---|---|---|
| HW-485 | 否 | ESP32 计算声音统计量，Pi 新增串口适配 |
| HW-486 | 否 | ESP32 读取 ADC，Pi 按未标定亮度代理值处理 |
| HW-507/DHT11 | 否 | ESP32 读取 DHT11，Pi 新增 climate 串口适配 |
| MLX90640 直连 Pi | 是 | 保持现有 I²C 驱动 |
| MLX90640 经 ESP32 | 否 | 新增 ESP32 热帧读取和 Pi 串口热帧适配 |

四个传感器都接 ESP32 时，不需要重写模块 1 的模型、窗口、存储或共享契约；
需要新增 ESP32 固件、单一串口 hub、四类数据适配器、配置和测试。

## 9. 仍需实物确认

开始实现或上电前，补充确认：

- HW-507 PCB 是否确实由卖家标为 `HW-507`；
- HW-485 在 5V 供电时，分压前后 AO 静态电压和最大电压；
- HW-486 遮挡/照射时 ADC 数值变化方向；
- MLX90640 breakout 厂家、视场角、PCB 背面和供电说明；
- ESP32 在 Raspberry Pi 上对应的稳定 `/dev/serial/by-id/` 路径。

任何一项与本文丝印不一致时，应停止上电，以实物和对应批次资料为准。

## 10. 参考资料

- Espressif ESP32 ADC：
  <https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html>
- Espressif ESP32 受限 GPIO：
  <https://docs.espressif.com/projects/arduino-esp32/en/latest/boards/ESP32-DevKitC-1.html>
- Melexis MLX90640 数据手册：
  <https://www.melexis.com/-/media/files/documents/datasheets/mlx90640-datasheet-melexis.pdf>
- ASAIR DHT11 数据手册：
  <https://www.aosong.com/userfiles/files/media/DHT11%E6%B8%A9%E6%B9%BF%E5%BA%A6%E4%BC%A0%E6%84%9F%E5%99%A8%E8%AF%B4%E6%98%8E%E4%B9%A6%EF%BC%88%E4%B8%AD%EF%BC%89%20A0-1208.pdf>
