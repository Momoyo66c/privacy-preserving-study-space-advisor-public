# 模块 01 规格复核

复核日期：2026-07-21  
依据：`docs/module-specs/00_SHARED_CONTRACT.md`、`docs/module-specs/01_SENSOR_EDGE_HARDWARE.md`

## 结论

模块 01 的本地可实现范围已经具备：统一驱动、窗口聚合、共享 Schema、模拟器、
离线会话、NPZ、校验和、隐私门禁、状态指示适配器、ESP32 Hub 协议及当前四个
实物传感器适配。模块 2 现在可通过 `SessionReader` 先完成整包验收，再按窗口流式
读取共享对象和可选热阵列，不需要连接硬件，也不需要自行解析本地 URI。

仍不能关闭模块 01 的全部硬件验收：LD2450 尚未到货；`smooth`/`live_max` 尚未
烧录；真实四传感器 10 分钟正式会话、32 FPS 链路稳定性和匿名真实样本尚未生成。

## 数据边界复核

| 边界 | 当前实现 | 验收状态 |
|---|---|---|
| ESP32 → Pi | COBS、CRC32、协议版本、序号、能力位、长度上限、有界队列和自动重连 | 已完成；高帧率档待实机 |
| Pi 驱动 → 窗口 | 同一 UTC/单调时钟、5–10 秒非重叠窗口、样本数、健康、完整度和窗口局部雷达 ID | 已完成 |
| 窗口 → 磁盘 | `windows.jsonl` 共享对象；热阵列为每窗口压缩 NPZ；声音只有统计量 | 已完成 |
| 会话完整性 | 全文件 SHA-256、共享 JSON Schema、元数据一致性、时间顺序、NPZ 形状/计数/有限值/温度范围、禁止媒体文件和符号链接 | 已完成 |
| 会话 → 模块 2 | `SessionReader` 验证整包后流式返回窗口与只读 `float32 (N, 768)` 热阵列 | 已完成 |
| 模块 2 → 后端 | 不属于模块 01；模块 01 不生成分类、Observation 或热图预览上传 | 边界明确 |

## 01 规格逐项状态

| 规格项 | 状态 | 证据或剩余条件 |
|---|---|---|
| MLX90640 32×24、异常帧校验、NPZ | 已完成 | 驱动、Hub、窗口、会话验证测试覆盖 |
| LD2450 驱动、损坏包恢复、窗口内匿名化 | 软件完成，实物待测 | 真实传感器尚未到货 |
| 声音仅保留 RMS/标准差/峰值 | 已完成 | 会话验收拒绝音频扩展名；Hub 不传原始 ADC 序列 |
| 光照、温湿度缺失/代理值语义 | 已完成 | HW-486 未标定时 `light_lux=null` 并给出 warning；DHT11 使用标准单位 |
| 单传感器失败仍交付降级窗口 | 已完成 | 故障注入、模拟集成和 Hub 重连测试覆盖 |
| 两分钟模拟连续运行 | 已完成 | 既有 24 窗口实测和自动集成测试 |
| 状态颜色纯映射与 GPIO/micro:bit 适配 | 软件完成 | 五种状态单元测试通过；实体指示器尚未接入 |
| README 安装、接线、配置、运行、排障 | 已完成，需随硬件结果继续更新 | ESP32 Hub 接线与高帧率边界已有说明 |
| 真实硬件 10 分钟连续采集 | 待执行 | 需要树莓派恢复连接；记录丢帧、无效包、资源和重启释放 |
| 至少 MLX90640、LD2450 和一个环境/声音实物贯通 | 待 LD2450 | 当前 MLX90640、HW-485、HW-486、DHT11 已贯通 |
| 不含个人数据的真实采集样例 | 待生成 | 必须来自真实 10 分钟会话并通过只读验收，不用模拟数据替代 |

## 模块 2 读取方式

先安装模块 01 wheel 或 editable 包，然后直接使用：

```python
from study_space_hardware.session_reader import SessionReader

session = SessionReader("data/sessions/SESSION_ID")
for item in session:
    sensor_window = item.payload
    thermal_frames = item.thermal_frames  # None 或只读 float32，形状 (N, 768)
```

构造 `SessionReader` 时会先验证整包；校验和、Schema、隐私、时间、标识或 NPZ
任一项失败都会抛出 `InvalidSessionError`，不会向模块 2 暴露部分有效的数据。

## 恢复树莓派后的固定顺序

1. 核对稳定串口路径、固件构建 profile 和主机 baud，先跑 `analytics` 基线。
2. 烧录 `smooth`，验证 16 FPS、协议错误、其他传感器公平性和资源占用。
3. 烧录 `live_max`，以 921600 baud 验证 32 FPS；失败时保留 `smooth`，不修改正式默认。
4. 恢复正式 `analytics` 或验收通过的档位，执行真实四传感器 10 分钟会话。
5. 运行 `study-space-verify-session`，去除任何现场身份信息后再选取匿名样例。
6. LD2450 到货后补做 Gate B；此前模块 01 只能标记“当前四传感器完成，雷达待实物”。
