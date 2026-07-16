# 模块 1：传感器与边缘硬件

## 交付给 AI 的执行指令

你负责实现 Privacy-Preserving Study Space Advisor 的传感器与边缘硬件模块。先完整阅读同目录下的 `00_SHARED_CONTRACT.md`，然后检查现有仓库，在 `edge/hardware/` 中实现本规格。你拥有传感器驱动、采样编排、数据质量检查、本地缓存、模拟器和 LED/micro:bit 状态输出；你不负责训练分类模型、后端数据库或 Dashboard。真实硬件不可用时也必须完成可测试的模拟实现，并让真实驱动可以通过相同接口替换。持续执行直到本模块测试通过、运行文档完整、跨模块夹具可被模块 2 使用。

## 1. 模块使命

在 Raspberry Pi 5 上稳定、同步、隐私友好地采集多模态传感器数据，并把每个 5 至 10 秒采样窗口转换成模块 2 可直接消费的标准对象。同时根据模型输出驱动本地 LED 或 micro:bit 状态指示。

## 2. 负责范围

本模块负责：

- MLX90640 32 x 24 热阵列驱动和帧读取。
- HLK-LD2450 mmWave 雷达串口读取、协议解析和匿名目标数据。
- 声音强度统计，不保存原始语音。
- 光照、温度、湿度读取。
- 多传感器时间戳、滑动/非重叠窗口和数据完整度计算。
- 传感器健康检查、自动重试、降级状态和诊断日志。
- 离线数据采集会话，供模块 2 标注和训练。
- 与真实硬件接口一致的模拟传感器。
- 蓝/绿/黄/红 LED 或 micro:bit 状态指示。

本模块不负责：

- 特征选择、模型训练、模型评估或分类决策。
- 向数据库写入历史记录。
- 推荐排序、LLM 调用或 Web UI。
- 人数精确计数、身份识别或跨窗口人员追踪。

## 3. 建议技术基线

- Python 3.11 或 Raspberry Pi OS 可稳定支持的 Python 3 版本。
- 配置文件采用 YAML 或 TOML，敏感值通过环境变量注入。
- 驱动统一实现 Python `Protocol` 或抽象基类。
- 结构化日志输出 JSON 或稳定的键值格式。
- 测试采用 `pytest`；串口、I2C、GPIO 必须可替换为 fake/mock。

禁止把系统设计成只有连接真实硬件才能导入模块或运行测试。

## 4. 目录和组件

```text
edge/hardware/
|-- README.md
|-- pyproject.toml
|-- config/
|   `-- example.yaml
|-- src/study_space_hardware/
|   |-- config.py
|   |-- clock.py
|   |-- models.py
|   |-- health.py
|   |-- windowing.py
|   |-- orchestrator.py
|   |-- storage.py
|   |-- drivers/
|   |   |-- base.py
|   |   |-- mlx90640.py
|   |   |-- ld2450.py
|   |   |-- sound_level.py
|   |   |-- light.py
|   |   `-- climate.py
|   |-- simulators/
|   |   |-- scenario.py
|   |   `-- sensors.py
|   `-- actuation/
|       |-- status_mapper.py
|       |-- gpio_led.py
|       `-- microbit.py
|-- scripts/
|   |-- probe_sensors.py
|   |-- collect_session.py
|   `-- run_simulator.py
`-- tests/
```

具体文件名允许调整，但职责必须保留。

## 5. 标准驱动接口

每种传感器至少提供：

```python
class SensorDriver(Protocol):
    @property
    def name(self) -> str: ...

    def start(self) -> None: ...

    def read(self) -> SensorSample: ...

    def health(self) -> SensorHealthReport: ...

    def close(self) -> None: ...
```

要求：

- `read()` 返回采样时间戳、值、单位和质量标记。
- 驱动异常转换为本模块定义的可诊断异常，不让底层库异常直接穿透主循环。
- `close()` 可重复调用，确保串口、I2C 和 GPIO 正确释放。
- 短暂读取失败可重试；持续失败必须切换为 degraded/offline。

## 6. 各传感器目标

### 6.1 MLX90640

- 读取并验证 32 x 24 温度矩阵。
- 帧率可配置；演示默认值应在 Raspberry Pi 5 和总线能力内稳定运行。
- 对 NaN、明显越界温度、损坏帧进行标记和丢弃统计。
- 不在后端负载或普通日志中打印完整矩阵。
- 离线采集时保存为紧凑二进制格式，例如 NumPy NPZ，而不是巨型 JSON。

### 6.2 HLK-LD2450

- 串口参数可配置。
- 解析目标位置、速度/运动状态等设备实际可提供的字段。
- 目标编号仅在当前采样窗口有效；新窗口重新匿名化。
- 校验消息边界和长度；损坏包不得使采集进程退出。
- 记录帧数、有效目标数、无效包数和最近成功时间。

### 6.3 声音强度

- 只计算 RMS、标准差、峰值或等价强度统计。
- 内存中的短缓冲区计算完成后立即释放。
- 禁止写入 WAV、PCM、MP3 或任何可恢复语音内容。
- 配置与日志中明确声明 `raw_audio_persisted=false`。

### 6.4 光照和温湿度

- 输出标准单位：lux、摄氏度、相对湿度百分比。
- 对设备缺失或当前传感器只能输出代理值的情况，明确标记来源和质量。
- 不允许把缺失值替换为看似正常的固定数值。

## 7. 采样窗口与质量

- 默认使用不重叠 5 秒窗口，可通过配置改为 5 至 10 秒。
- 所有传感器时间戳来自同一单调时钟和 UTC 墙上时钟映射。
- 每个窗口生成 `window_id`、开始/结束时间、各传感器样本数和健康状态。
- `quality.completeness` 等于实际有效采样量与预期采样量的比例，限制为 0 至 1。
- 某个非关键环境传感器缺失时仍交付窗口并标记 degraded。
- 热阵列和雷达同时 offline 时，窗口仍可用于诊断，但必须标记不可用于正常推理。
- 完整输出遵循共享契约第 6 节。

## 8. 离线数据采集模式

提供命令行工具：

```text
collect_session --room room_a --scenario quiet_study_recommended --duration 300
```

每个采集会话至少保存：

```text
data/sessions/<session_id>/
|-- session.json
|-- windows.jsonl
|-- thermal/
|   `-- <window_id>.npz
`-- checksums.json
```

`session.json` 包含：

- `session_id`、房间、场景标签、开始/结束时间。
- 设备和驱动版本。
- 采样配置。
- 参与人数使用区间或场景描述，不记录姓名和学号。
- 操作者备注和已知异常。

数据文件必须可被模块 2 在没有硬件的电脑上读取。

## 9. 模拟器

模拟器至少支持以下场景：

- `empty_or_low_activity`
- `quiet_study_recommended`
- `discussion_allowed`
- `not_recommended_noisy_or_crowded`
- `degraded_thermal`
- `degraded_radar`
- `intermittent_failure`

模拟值应有时间变化和少量噪声，避免每个窗口完全相同。固定随机种子时输出必须可复现。模拟器生成的窗口必须通过同一数据模型和验证逻辑，不得走测试专用捷径。

## 10. 本地状态指示

默认映射：

| 状态 | 颜色 |
|---|---|
| `empty_or_low_activity` | 蓝 |
| `quiet_study_recommended` | 绿 |
| `discussion_allowed` | 黄 |
| `not_recommended_noisy_or_crowded` | 红 |
| `unknown`、系统启动或严重降级 | 白色/闪烁模式，按硬件能力实现 |

要求：

- 映射写在单独纯函数中并有单元测试。
- GPIO 和 micro:bit 输出使用适配器，允许在无硬件环境记录目标颜色。
- 蜂鸣器只能作为显式演示动作，默认关闭，不连续鸣叫。
- 状态更新失败不得阻断传感器采集。

## 11. 配置项

至少包含：

- `room_id`、`device_id`
- 采样窗口长度
- 每种传感器是否启用、总线/串口/GPIO 参数
- 期望采样率
- 重试次数和离线阈值
- 本地数据目录和保留策略
- 模拟器场景和随机种子
- 状态指示设备类型

提交 `example.yaml`，不得提交真实密钥或机器专用绝对路径。

## 12. 测试要求

### 单元测试

- 每个驱动的正常读取、损坏数据、超时和关闭行为。
- 采样窗口边界、样本计数、完整度和警告生成。
- 声音模块不产生原始音频文件。
- LED 状态映射覆盖所有枚举。
- 固定种子的模拟器输出可复现。

### 集成测试

- 使用全模拟传感器连续运行至少 2 分钟，无未处理异常。
- 单个传感器 offline 时仍持续输出 degraded 窗口。
- 输出至少一份共享契约规定的有效夹具和一份 degraded 夹具。

### 硬件烟雾测试

- `probe_sensors.py` 输出每个传感器的连接、最近读数和健康状态。
- 真实硬件连续采集至少 10 分钟，记录丢帧率、无效包率和资源占用。
- 进程退出后可再次启动，不出现串口/I2C/GPIO 被占用。

## 13. 验收标准

- [ ] 模拟模式可在普通开发电脑运行。
- [ ] 标准采样窗口与共享 JSON 示例一致。
- [ ] 至少提供 MLX90640、LD2450 和声音/环境传感器的真实或可安装驱动。
- [ ] 任何单个传感器故障不会导致主进程崩溃。
- [ ] 原始语音从未落盘或发送。
- [ ] 离线采集会话可被模块 2 加载。
- [ ] LED/micro:bit 对五种状态均有确定行为。
- [ ] README 包含安装、接线、配置、模拟运行、真实运行和故障排查步骤。
- [ ] 所有自动测试通过，并给出一次真实硬件烟雾测试记录。

## 14. 最终交付物

- `edge/hardware/` 可运行源码。
- 配置示例和接线说明。
- 传感器探测、采集会话和模拟器命令。
- 单元测试与集成测试。
- 两份共享窗口夹具：正常和降级。
- 一份不含个人数据的真实采集样例。
- `MODULE1_HANDOFF.md`，列出已完成内容、硬件限制、已知问题和模块 2 的使用方法。
