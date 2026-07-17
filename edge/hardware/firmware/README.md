# ESP32 串口烟雾测试固件

`esp32_serial_smoke/esp32_serial_smoke.ino` 只验证树莓派到 ESP32 的编译、烧录和串口通信链路。固件不连接 Wi-Fi，不读取传感器，也不保存数据。它不是 LD2450 固件，不能把同一个串口同时配置成雷达端口。

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

烧录完成后，以 115200 baud 打开串口。成功输出如下：

```text
PSSA_ESP32_SMOKE_READY
PSSA_ESP32_HEARTBEAT seq=0
PSSA_ESP32_HEARTBEAT seq=1
```

设备编号会随 USB 插拔改变。部署配置应优先使用 `/dev/serial/by-id/` 下的稳定路径，并为 ESP32 和 LD2450 分配不同的串口设备。
