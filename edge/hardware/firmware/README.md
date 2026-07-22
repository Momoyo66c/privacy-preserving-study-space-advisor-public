# ESP32 固件

本目录包含生产用 Sensor Hub 和早期链路烟雾测试两个固件。新部署应使用 `esp32_sensor_hub/`；`esp32_serial_smoke/` 只保留为 USB 串口故障排查工具。

## Sensor Hub

`esp32_sensor_hub/` 将 MLX90640、HW-507/DHT11、HW-485 和 HW-486 汇聚到 ESP32，再通过一条 USB 串口连接 Raspberry Pi。详细的接线、可复现构建和验证步骤见 [esp32_sensor_hub/README.md](esp32_sensor_hub/README.md)。二进制协议见 [../ESP32_HUB_PROTOCOL.md](../ESP32_HUB_PROTOCOL.md)。LD2450 协议兼容代码保留，但最终生产固件不启用雷达。

## 串口烟雾测试固件

`esp32_serial_smoke/esp32_serial_smoke.ino` 只验证树莓派到 ESP32 的编译、烧录和串口通信链路。固件不连接 Wi-Fi，不读取传感器，也不保存数据。

## 烧录前确认目标

先查看稳定设备路径和芯片型号。不要只凭 `/dev/ttyUSB0` 猜测设备类型。

```bash
ls -l /dev/serial/by-id/
arduino-cli board list
esptool --port /dev/ttyUSB0 chip-id
```

只有 esptool 明确识别为 ESP32 后，才执行烧录。当前测试板使用通用 ESP32 FQBN：

```bash
arduino-cli compile \
  --fqbn esp32:esp32:esp32 \
  firmware/esp32_serial_smoke

arduino-cli upload \
  --fqbn esp32:esp32:esp32 \
  --port /dev/ttyUSB0 \
  firmware/esp32_serial_smoke
```

烧录烟雾测试固件后，以 115200 baud 打开串口。成功输出如下：

```text
PSSA_ESP32_SMOKE_READY
PSSA_ESP32_HEARTBEAT seq=0
PSSA_ESP32_HEARTBEAT seq=1
```

设备编号会随 USB 插拔改变。部署配置应优先使用 `/dev/serial/by-id/` 下的稳定路径。最终 Sensor Hub 只需要 ESP32 这一条 USB 串口。
