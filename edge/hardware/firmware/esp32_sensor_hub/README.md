# ESP32 Sensor Hub 固件

本固件让 ESP32 作为所有传感器的本地采集端，同时保持 Raspberry Pi 之后的 `SensorDriver`、窗口聚合和跨模块 Schema 不变。ESP32 不联网、不保存数据、不输出文本日志；声音只上传统计值，不上传 PCM 或波形。

## 接线

以下引脚适用于当前通用 ESP32 DevKit 配置。接线前必须核对开发板丝印和传感器模块说明；ESP32 GPIO 只能接受 3.3 V 逻辑，电平不确定时使用双向电平转换器。所有模块与 ESP32 必须共地。

| 设备 | 设备端 | ESP32 | 说明 |
|---|---|---|---|
| MLX90640 | SDA / SCL | GPIO21 / GPIO22 | I²C 地址 `0x33` |
| BH1750 | SDA / SCL | GPIO21 / GPIO22 | I²C 地址 `0x23`，可共用总线 |
| AHT20/AHT21 | SDA / SCL | GPIO21 / GPIO22 | I²C 地址 `0x38`，可共用总线 |
| LD2450 | TX / RX | GPIO16 RX2 / GPIO17 TX2 | `256000 8N1`；TX 与 RX 交叉连接 |
| 可选 I2S 麦克风 | BCLK / WS / DATA | GPIO26 / GPIO25 / GPIO33 | 当前默认关闭，接好后才修改配置启用 |
| Raspberry Pi | USB | ESP32 USB 口 | Hub 协议 `460800 8N1`；不需要额外 USB-TTL |

I²C 模块的 VCC 按所购转接板的额定输入供电；不要仅凭传感器芯片电压推断转接板供电。LD2450 的供电和 UART 电平也必须以实际模块资料为准，绝不能把高于 3.3 V 的信号直接送入 ESP32 GPIO。

## 固件配置

引脚、采样频率和功能开关集中在 `sensor_hub_config.h`。默认启用热阵列、雷达、光照和温湿度；I2S 麦克风在真实硬件接入前保持关闭。开机时缺失的 I²C/I2S 设备每 5 秒重试一次，不需要为了后接传感器重新烧录。

## 可复现构建

需要 Arduino CLI 1.x。`sketch.yaml` 固定 ESP32 core 和全部直接编译依赖的版本；profile 构建使用隔离环境，不依赖全局安装的库。

```bash
arduino-cli compile --profile esp32_sensor_hub firmware/esp32_sensor_hub
```

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
study-space-probe --config config/esp32-hub.example.yaml
```

固件与 Python 协议编码器共享黄金向量。主机侧测试会用系统 C++ 编译器编译 `protocol.cpp`，并逐字节核对 COBS、CRC32、协议版本和结尾分隔符：

```bash
python -m pytest tests/test_esp32_firmware_protocol.py
```

真实验收至少包括：启动心跳可解码、能力位与实物一致、传感器断开后能力撤销、重新接入后恢复、USB 断开重连、持续运行无无界队列增长，以及采集目录不存在音频/视频原始文件。
