# Privacy-Preserving Study Space Advisor

本目录把 P6 proposal 拆成四份可以直接交给开发人员或 AI 执行的模块目标文档。

## 使用顺序

1. 所有人和所有 AI 先阅读 [`00_SHARED_CONTRACT.md`](./00_SHARED_CONTRACT.md)。
2. 每位负责人只领取一份模块文档，并在共享契约范围内独立实现。
3. 任何接口字段、枚举或目录边界变更，先更新共享契约并通知其他模块。
4. 模块完成不等于项目完成；必须通过共享契约中的四个集成门禁。

## 四个模块

| 模块 | 目标文档 | 主要结果 |
|---|---|---|
| 1. 传感器与边缘硬件 | [`01_SENSOR_EDGE_HARDWARE.md`](./01_SENSOR_EDGE_HARDWARE.md) | 稳定采集隐私友好传感器数据并驱动本地状态指示 |
| 2. 数据与边缘机器学习 | [`02_EDGE_ML_PIPELINE.md`](./02_EDGE_ML_PIPELINE.md) | 训练、评估并在 Raspberry Pi 5 上运行课堂状态分类模型 |
| 3. 后端与数据智能 | [`03_BACKEND_DATA_INTELLIGENCE.md`](./03_BACKEND_DATA_INTELLIGENCE.md) | 接收边缘结果、持久化数据并提供历史与未来占用预测 API |
| 4. 推荐与前端应用 | [`04_RECOMMENDATION_FRONTEND.md`](./04_RECOMMENDATION_FRONTEND.md) | 根据用户偏好排序房间、生成解释并提供可演示的 Dashboard |

## 建议仓库结构

```text
.
|-- edge/
|   |-- hardware/          # 模块 1
|   `-- ml/                # 模块 2
|-- backend/               # 模块 3；模块 4 的推荐服务适配层也在此集成
|-- frontend/              # 模块 4
|-- shared/
|   |-- contracts/         # JSON Schema、枚举、示例负载
|   `-- fixtures/          # 跨模块测试数据
|-- tests/
|   `-- integration/       # 端到端契约测试
`-- docs/
    `-- module-specs/
```

## 全项目完成定义

- 真实传感器或可替换模拟器持续产生有效数据。
- Raspberry Pi 5 在本地输出四种课堂状态之一、占用等级、适合度和置信度。
- 后端可接收、存储、查询并预测未来 15 至 30 分钟的占用等级。
- 用户可设置偏好并获得有排序、有理由、有降级方案的房间推荐。
- Dashboard 能展示当前状态、推荐、趋势、预测、模型置信度和隐私说明。
- 系统不采集 RGB 图像，不保存原始语音，不执行身份识别。
- 在 LLM、网络或部分传感器不可用时，系统仍能以明确的降级状态完成核心演示。
