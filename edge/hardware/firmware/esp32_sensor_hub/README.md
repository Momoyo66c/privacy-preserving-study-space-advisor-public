# ESP32 Sensor Hub 固件

本固件针对已确认的 WeMos D1 R32 和五个传感器模块：MLX90640、HLK-LD2450、HW-507/DHT11、HW-485 声音模块、HW-486 光敏模块。ESP32 作为本地采集端，同时保持 Raspberry Pi 之后的 `SensorDriver`、窗口聚合和跨模块 Schema 不变。ESP32 不联网、不保存数据、不输出文本日志；声音只上传统计值，不上传 ADC 原始序列。

## 接线

以下引脚适用于当前通用 ESP32 DevKit 配置。接线前必须核对开发板丝印和传感器模块说明；ESP32 GPIO 只能接受 3.3 V 逻辑，电平不确定时使用双向电平转换器。所有模块与 ESP32 必须共地。

| 设备 | 设备端 | ESP32 | 说明 |
|---|---|---|---|
| MLX90640 | SDA / SCL | GPIO21 / GPIO22 | I²C 地址 `0x33`；VIN 接 3V3，GND 共地 |
| HW-507/DHT11 | S | GPIO27 | `+` 接 3V3，`-` 接 GND；单总线，不是普通数字电平 |
| HW-485 | AO | 经 10 kΩ/10 kΩ 分压后接 GPIO34 | 模块 `+` 接 5V、`G` 接 GND；`DO` 不连接 |
| HW-486 | S | GPIO35 | `+` 接 3V3、`-` 接 GND；输出是未标定 ADC 代理值 |
| LD2450 | TX / RX | GPIO16 RX2 / GPIO17 TX2 | TX/RX 交叉连接；5V 供电、GND 共地、256000 8N1 |
| Raspberry Pi | USB | ESP32 USB 口 | Hub 协议 `460800 8N1`；不需要额外 USB-TTL |

HW-485 使用 5 V 供电时，AO 必须先经过 10 kΩ/10 kΩ 分压，不能把 AO 或 DO 直接接入 ESP32。ADC attenuation 不是过压保护。MLX90640 当前按 3.3 V 供电；首次上电前还要确认 breakout 上拉电阻没有接到 5 V。所有模块必须共地。

## 固件配置

引脚、采样频率和功能开关集中在 `sensor_hub_config.h`。当前默认启用五个传感器。DHT11 每 2 秒读取一次；LD2450 使用 UART2 的 256000 8N1 数据流；HW-485 在 ESP32 RAM 中短时采样后只发送归一化 RMS、标准差和峰值，该实物批次的 AO 静音基线接近 0，因此全零窗口按有效静音上报；HW-486 发送 ADC 原始计数和归一化代理值。

HW-485 的模拟引脚无法仅凭静音电平区分“正常安静”和“信号线接地/断开”。首次部署必须做一次有声响应试验；本项目实物已用临时聚合诊断确认，静音窗口为 0，制造声音时 GPIO34 峰值会上升。生产固件不传输原始 ADC 序列。

### 选择热成像性能档位

固件提供三个编译时档位。MLX90640 的刷新率指子页频率；两个子页组成
一幅完整 32 × 24 热图，因此完整画面帧率最多是子页频率的一半。

| 档位 | 宏值 | MLX 子页 | 完整热图 | 运行期 I²C | USB 串口 | 状态 |
|---|---:|---:|---:|---:|---:|---|
| `analytics` | `0` | 8 Hz | 2 FPS 发布 | 400 kHz | 460800 | 默认，实机验证通过 |
| `smooth` | `1` | 32 Hz | 16 FPS 发布 | 1 MHz | 460800 | 仅完成本地编译配置验证 |
| `live_max` | `2` | 64 Hz | 32 FPS 发布 | 1 MHz | 921600 | 仅完成本地编译配置验证 |

普通构建不传宏，始终使用 `analytics`，不会意外改变已经验证的正式采集配置：

```bash
arduino-cli compile --profile esp32_sensor_hub firmware/esp32_sensor_hub
```

编译 `smooth` 或 `live_max`：

```bash
arduino-cli compile --profile esp32_sensor_hub \
  --build-property build.extra_flags=-DPSSA_THERMAL_PROFILE=1 \
  firmware/esp32_sensor_hub

arduino-cli compile --profile esp32_sensor_hub \
  --build-property build.extra_flags=-DPSSA_THERMAL_PROFILE=2 \
  firmware/esp32_sensor_hub
```

> **Warning:** `live_max` 将 USB 串口改为 921600 baud。烧录前必须把 Pi
> 主机配置改为相同波特率。当前尚未在实物上验证 1 MHz I²C、921600
> 串口或 32 FPS 连续运行，不能把本地编译测试当成硬件通过。

MLX90640 初始化和 EEPROM 校准读取始终保持 400 kHz；只有初始化成功后，
高帧率档位才切换到 1 MHz。编译期带宽门禁按最坏 1566 字节热帧计算，
限制热流最多占 UART 理论容量的 80%，为声音、光照、温湿度、心跳和雷达
保留空间。不安全或未知档位会直接编译失败。

HW-486 不是照度计。在使用参考照度计完成标定前，Pi 端固定输出 `light_lux=null`、`calibrated_lux=false` 和 `hw486_uncalibrated_light_proxy` 警告，不能把 ADC 数值写成 lux。遮挡/照射试验还需确认数值方向。

## 可复现构建

需要 Arduino CLI 1.x。`sketch.yaml` 固定 ESP32 core 和全部直接编译依赖的版本；profile 构建使用隔离环境，不依赖全局安装的库。

默认的可复现构建命令见上一节。高帧率档位只改变编译宏，不改变固定的
ESP32 core 和库版本。

当前目标是经典 ESP32-D0WD-V3 的通用 `esp32:esp32:esp32` FQBN。烧录前先确认端口实际对应 ESP32：

```bash
arduino-cli board list
esptool --port /dev/ttyUSB0 chip-id
arduino-cli upload \
  --profile esp32_sensor_hub \
  --port /dev/ttyUSB0 \
  firmware/esp32_sensor_hub
```

端口名可能随 USB 插拔变化；运行配置优先使用 `/dev/serial/by-id/` 中的稳定路径。

## 主机配置与验收

在 Raspberry Pi 上以 Hub 示例配置探测。未接的传感器必须明确返回“不支持”或“离线”，不能用旧样本伪装成功。

```bash
export ESP32_HUB_PORT=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
study-space-probe-sensors --config config/esp32-hub.example.yaml
```

固件与 Python 协议编码器共享黄金向量。主机侧测试会用系统 C++ 编译器编译 `protocol.cpp`，并逐字节核对 COBS、CRC32、协议版本和结尾分隔符：

```bash
python -m pytest tests/test_esp32_firmware_protocol.py
```

真实验收按四个模块逐个进行：DHT11 温湿度有效且读取间隔合规；HW-485 分压后最大电压低于 3.3 V 且声音变化会改变统计量；HW-486 遮挡/照射会改变 ADC 代理值但 `light_lux` 保持空；MLX90640 返回 32×24 有限温度帧。最后再确认 USB 重连和采集目录不存在音频/视频原始文件。
