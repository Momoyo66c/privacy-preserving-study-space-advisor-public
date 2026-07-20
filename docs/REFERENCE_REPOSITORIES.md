# GitHub 参考源码清单

核验时间：2026-07-18 01:55 SGT

## 核验方法

`references/clone-results.log` 记录了 9 次成功克隆。本次又对每个仓库串行执行 `git fetch --all --prune`，检查当前分支、HEAD、对应 `origin/<branch>`、工作树状态、README 和根许可证文件。9 个仓库均为完整克隆，工作树干净，且本地 HEAD 与对应远端分支一致。

`references/` 仍是未跟踪的本地资料目录。本清单记录可复现的上游版本，但不把第三方仓库整体纳入本项目历史。

## 仓库、用途与复用结论

| 仓库 | 核验版本 | 用途 | 许可证 | 本项目结论 |
|---|---|---|---|---|
| [Adafruit_CircuitPython_MLX90640](https://github.com/adafruit/Adafruit_CircuitPython_MLX90640) | `main` / `6a537df6af2fce6ad301e2022a7084da9b25af19` | Raspberry Pi/CircuitPython 的 MLX90640 驱动与公开 API | MIT | 模块 01 已通过 PyPI 依赖调用公开 API，未内嵌底层驱动；保留 MIT 归属声明 |
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | `7.x` / `7823e4a62b17ea0ee81bdd4e79911c94e637f964` | ESP32/Arduino 的 JSON 序列化库 | MIT | 当前串口冒烟固件没有使用；未来如加入结构化固件输出，可作为依赖引入并保留声明 |
| [HLK-LD2450](https://github.com/csRon/HLK-LD2450) | `main` / `1b65a026873ab2db3d22d3b3bb99ef16fbcdd4f0` | LD2450 串口协议、目标字段和示例 | MIT | 模块 01 的帧布局参考来源；现有 `THIRD_PARTY_NOTICES.md` 已记录版本、归属和重新实现边界 |
| [IoTProject-ZonePresenceDetection-LD2450](https://github.com/nick28s/IoTProject-ZonePresenceDetection-LD2450) | `main` / `d5a93d9473c22b2d54e121bffdb336c3a20daa7c` | ESP32 雷达分区检测与 Web 界面示例 | GPLv3 | 只用于方案对照；本阶段不复制代码，也不引入其 Web 界面 |
| [PiThermalCam](https://github.com/tomshaffner/PiThermalCam) | `master` / `cdee56f18ee7779e172f506be6edf624cde5de40` | Raspberry Pi 上的 MLX90640 采集、可视化和 Flask 示例 | AGPLv3 | 只用于部署经验对照；不复制代码，不把网络应用部分并入本项目 |
| [SparkFun_MLX90640_Arduino_Example](https://github.com/sparkfun/SparkFun_MLX90640_Arduino_Example) | `master` / `29260f68a86e6b920cd6ec8a7e724e74c9ad8647` | Arduino 读取 MLX90640 和串口可视化示例 | 代码 MIT；硬件资料 CC BY-SA 4.0 | 可参考 MIT 代码的传感器初始化方式；硬件设计和附带资料需按各自授权另行检查 |
| [async-mqtt-client](https://github.com/marvinroger/async-mqtt-client) | `develop` / `3d93fc7f662e65366f8e2b0d88b108f874f035b9` | ESP32/ESP8266 异步 MQTT 客户端 | MIT | 当前模块 01 不需要 MQTT；仅在后续传输方案明确采用 MQTT 时再评估依赖 |
| [classroom-occupancy](https://github.com/Kautumn06/classroom-occupancy) | `master` / `fb51f958b0fb36efb3696a3943fe5cb80d1dcf9f` | 教室占用数据清洗与模型实验 | MIT | 只用于数据字段和实验方法参考；当前阶段不实现或复制机器学习流程 |
| [crowdaware-node](https://github.com/crowdaware-inno-wing-iot/crowdaware-node) | `main` / `d36757924f34a81322d3293127b100fdb5145d9e` | ESP32 + MLX90640 的隐私友好人群检测与 UDP 遥测 | GPLv3 | 只用于架构对照；不复制固件、检测算法或可视化代码 |

## 许可证边界

项目根目录当前没有 `LICENSE`、`COPYING` 或 `NOTICE`，因此不能把“第三方许可证允许复用”误写成“已经确定与本项目发布许可证兼容”。在团队确定项目许可证前采用以下保守规则：

- MIT 项目优先通过包管理器作为依赖使用；若复制或实质性改编代码，保留版权和 MIT 许可文本。
- GPLv3 与 AGPLv3 仓库只用于行为、协议和架构对照，不复制实现。若以后确需使用，必须先由项目负责人确认整个分发方式和源码公开义务。
- SparkFun 的代码与硬件资料采用不同许可证；不能用代码的 MIT 结论覆盖硬件文件或第三方数据手册。
- 任何新增第三方复用都先更新本清单和相应模块的第三方声明，再进入产品代码。

以上是工程复用边界记录，不替代正式法律意见。
