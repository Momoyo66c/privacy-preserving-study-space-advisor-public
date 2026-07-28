# 非 Module 3 问题与后续工作

更新时间：2026-07-22
审计基线：`main` `315a6f1`

## 1. 范围与判定规则

本文只记录 Module 1、Module 2、Module 4 和跨模块集成问题，不评估 Module 3 内部实现质量。Module 3 只在说明接口依赖时出现。

结论以已合并到 `main` 的受版本控制文件为准。远端分支、未跟踪文件、本机构建产物和口头计划不计为主线已完成能力。

优先级定义：

| 级别 | 含义 |
|---|---|
| P0 | 阻断真实硬件、实时推理或端到端演示，应优先解决 |
| P1 | 不阻断局部开发，但阻断模块验收或可信结果 |
| P2 | 文档、治理或可维护性风险 |

## 2. 结论摘要

| ID | 优先级 | 范围 | 问题 | 当前影响 |
|---|---|---|---|---|
| M1-01 | P0 | Module 1 | ESP32 四传感器实现尚未进入主线 | 当前主线不能按最终硬件组合部署 |
| X-01 | P0 | Module 1 ↔ 2 | 无雷达实时窗口缺少可供 Module 2 使用的热特征 | 实时分类可能主要退化为声音规则 |
| M2-01 | P0 | Module 2 | `edge/ml/` 与根目录 `ml/` 两套实现并存 | 包名、CLI、模型版本和维护入口冲突 |
| M4-01 | P0 | Module 4 | 正式推荐 adapter 和 Dashboard 未提交 | Gate A、C、D 无法完成 |
| X-02 | P0 | 集成 | `tests/integration/` 只有 README | 没有自动证明 SensorWindow 到 UI 的完整链路 |
| M2-02 | P1 | Module 2 | 仍是手写规则基线，没有正式训练评估 | 不能声明真实分类性能 |
| M2-03 | P1 | Module 2 | 没有仓库级 Module 2 CI | 两套实现及契约回归不会被自动阻止 |
| M1-02 | P1 | Module 1 | HW-485/HW-486 未完成物理量标定 | 声音不是 dB，光照不能稳定提供 lux |
| M4-02 | P1 | Module 4 | 没有前端工程、测试和可访问性验收 | 用户无法使用登录、偏好、选择和推荐流程 |
| X-03 | P2 | 仓库 | 状态文档与主线事实存在漂移 | 新成员容易选择错误入口或误判完成度 |
| X-04 | P2 | 仓库 | 根目录没有项目许可证 | 第三方代码复用和对外发布边界不明确 |

## 3. Module 1 问题

### M1-01：四传感器更新未进入主线（P0）

最终硬件选择是：

- MLX90640 热阵列；
- HW-485 相对声音强度；
- HW-486 光敏模块；
- HW-507/DHT11 温湿度模块；
- ESP32 通过 USB 串口向 Raspberry Pi 发送本地传感器摘要和热帧。

但 `main` 当前仍以 Raspberry Pi 直连 MLX90640、LD2450、USB 麦克风、BH1750 和 AHTx0 为主要说明，只包含最小 ESP32 串口 smoke 固件。完整 ESP32 hub、二进制协议、四传感器配置和相应测试仍在 `module1/hardware-foundation`，且尚未通过新的 PR 合并。

建议动作：

1. 由 Module 1 负责人基于最新 `main` 更新分支并发起 PR。
2. 审核协议边界、引脚、电平、隐私约束和四传感器 fixture。
3. 通过 Module 1 CI、固件编译和 Module 2 兼容 smoke 后再 squash merge。
4. 合并后统一根 README、共享契约、Module 1 README 和 Gate B 的硬件描述。

验收条件：`main` 可从空环境构建固件和 Python 包；四传感器窗口通过共享 Schema；雷达明确为 `not_configured`，不伪造零值；原始音频不落盘、不进串口协议和日志。

### M1-02：HW-485 与 HW-486 尚未完成物理量标定（P1）

HW-485 当前只能可靠输出去直流后的相对 RMS、标准差和峰值，不是声压级 dB。HW-486 是光敏电阻代理值，在没有参考照度计和标定曲线时不能可靠输出 lux。四传感器分支因此会把未标定 `light_lux` 设为 `null`，这是正确降级，但会使推荐的亮度维度失效。

建议动作：

- 固定安装位置、供电、电阻分压和 ESP32 ADC 衰减设置。
- 对 HW-485 采集安静、交谈和高噪声场景的相对基线，不把结果命名为 dB。
- 用参考照度计采集多点 HW-486 ADC/lux 对，保存版本化标定参数和误差报告。
- 标定前 UI 和推荐解释必须显示“相对值/不可用”，不能声称精确照度或噪声等级。

验收条件：标定方法、设备、日期、样本和误差可复现；参数进入配置而不是散落在固件中；缺少标定时继续输出 `null` 和 warning。

## 4. Module 1 ↔ Module 2 接口问题

### X-01：无雷达实时推理缺少热占用特征（P0）

当前 `edge/ml` 的热特征提取器只会从会话目录中的本地 NPZ 读取完整热帧并计算热区数量。实时 `SensorWindow` 通常只有 `thermal.health` 和 `frame_count`，没有 `frames_ref`；四传感器 fixture 也采用这种结构。与此同时，最终硬件不再配置 LD2450。

因此，即使热传感器健康，Module 2 的 `thermal_hot_region_count` 仍可能为 `null`；规则模型会主要依赖 HW-485 声音统计。安静但有人占用的房间存在被判断为 `empty_or_low_activity` 的明显风险。

建议选择以下一种契约安全方案：

1. **推荐方案**：Module 1 在 Raspberry Pi 内存中提供非持久化热帧给 Module 2，Module 2 复用同一热特征实现；序列化 `SensorWindow` 和后端负载仍不包含完整热帧。
2. Module 1 在窗口边界计算并交付版本化、不可识别的热摘要，但这会改变共享契约，必须同步 Schema、fixture 和测试。
3. 如果暂时只用声音分类，必须把模型标记为实验性降级，不得作为最终占用模型。

验收条件：对无雷达的四传感器实时窗口，热区特征不为 `null`；有人静坐、空房、多人讨论和热传感器离线场景有独立测试；热帧不进入后端、普通日志或 LLM。

## 5. Module 2 问题

### M2-01：存在两套同名实现（P0）

仓库同时跟踪：

- 规范目录 `edge/ml/`，包名 `study-space-ml`，模型版本 `0.3.0`；
- 根目录 `ml/`，包名 `privacy-study-space-ml`，模型版本 `0.1.0`。

两者都安装 `study_space_ml` Python 包，并注册重叠的 `study-space-ml-*` CLI。不同安装顺序可能覆盖入口或导入另一套代码，文档中的命令也不完全一致。

建议动作：

1. 以模块规格指定的 `edge/ml/` 为唯一目标目录。
2. 对比并迁移根目录 `ml/` 中仍有价值的测试或契约保护。
3. 删除第二套包、旧 artifact 和重复 CLI，同时更新所有文档与工作流引用。
4. 添加测试，确保 wheel 只包含一份 `study_space_ml`。

验收条件：仓库只有一个 Module 2 `pyproject.toml`、一个模型版本来源和一套 CLI；干净虚拟环境安装后所有命令指向 `edge/ml`。

### M2-02：没有真实数据训练与评估（P1）

当前 `edge/ml` 明确是确定性规则基线。它适合契约联调，但尚未完成规格要求的至少两个基线与 Random Forest 对比、按会话切分、Macro F1、混淆矩阵、错误分析和 Raspberry Pi 5 性能报告。

建议动作：

- 先完成真实会话与独立 `labels.csv`，禁止在运行时窗口中混入标签。
- 按 `session_id` 分组切分训练/验证/测试，避免相邻窗口泄漏。
- 比较多数类、规则模型和 Random Forest；数据不足时保留规则模型，不制造性能结论。
- 固化特征 Schema、模型包、Model Card、训练命令和 Pi benchmark。

验收条件：指标可从版本化命令复现；模型可在新进程与 Pi 5 加载；所有性能声明注明数据范围和限制。

### M2-03：缺少 Module 2 CI（P1）

`.github/workflows/` 当前有仓库文档检查、Module 1 CI 和后端 CI，没有 Module 2 专用工作流。Module 2 的测试、打包、共享 fixture 兼容和重复包问题不会在 PR 中自动门禁。

建议动作：新增顺序 CI 作业，至少执行：

```bash
python -m pip install -e './edge/ml[dev,thermal]'
python -m pytest edge/ml/tests
python -m compileall -q edge/ml/src edge/ml/scripts
python -m pip wheel edge/ml --no-deps --wheel-dir /tmp/module2-wheel
```

同时用共享正常、degraded 和最终四传感器 fixture 运行 `SensorWindow -> EdgeObservation` 契约测试。

验收条件：相关路径的 PR 自动触发；测试、编译、wheel 和共享契约任一步失败都会阻止合并。

## 6. Module 4 问题

### M4-01：正式推荐能力尚未实现（P0）

`frontend/` 在主线只跟踪一份 README。后端暴露了 Module 4 可替换的 `RecommendationAdapter` 协议，但默认仍是显式 stub；没有规格要求的模式匹配、占用、未来可用性、亮度、舒适度、距离归一化、fresh/stale 分桶和确定性 tie-breaker 正式实现。

建议动作：

1. 在 Module 4 范围实现 `module4-rule-based-v1` adapter。
2. 缺失维度退出权重并重新归一化，不把缺失值当 0 分。
3. LLM 只润色已确定的事实理由；超时、无 Key 或非法输出时回退模板，排名不得改变。
4. 覆盖至少三个房间、不同 study mode、stale/unknown/degraded、缺失环境维度和稳定 tie-breaker。

验收条件：相同输入产生相同排序；每个理由都有字段证据；LLM 关闭后排序和模板解释仍可用；禁止字段不会进入 provider 请求。

### M4-02：Dashboard 和用户流程尚未实现（P1）

主线没有受版本控制的 `package.json`、`src/`、组件测试或 E2E。Module 3 已提供登录、服务器偏好、选择历史和个性化推荐接口，但当前没有用户界面消费这些能力。

建议动作：

- 建立 React + TypeScript + Vite 工程和集中 API 层。
- 实现注册/登录、偏好设置、推荐列表、房间详情、显式“选择此教室”、历史管理和删除账号流程。
- 选择写入成功后才显示确认；失败使用同一 `selection_id` 重试，登出清理用户缓存。
- 覆盖 loading、empty、stale、unknown、degraded、后端断开、热图 unavailable 和 LLM fallback。
- 加入键盘操作、表单标签、非颜色状态表达和响应式布局测试。

验收条件：mock 与真实后端模式都可运行；组件测试与 E2E 通过；浏览详情和刷新不会误记为选择；浏览器不保存密码、Cookie 或完整选择上下文。

## 7. 跨模块与仓库问题

### X-02：没有端到端集成测试（P0）

`tests/integration/` 当前只有 README。现有模块测试不能证明四个模块在同一契约版本下能够连续工作。

建议按顺序建立：

1. Gate A：共享/模拟窗口 → Module 2 → Observation → 后端 → Dashboard mock/real API。
2. Gate B：四传感器窗口 → 无雷达推理 → 后端状态与预测。
3. Gate C：三个房间 → 正式推荐 → LLM 关闭与单传感器故障降级。
4. Gate D：至少 15 分钟演示 smoke，检查状态、趋势、预测、偏好变化、推荐和本地指示。

验收条件：无硬件、无 LLM Key 时 Gate A/C 可在 CI 运行；硬件 Gate B/D 有独立、可审计的现场记录。

### X-03：状态文档漂移（P2）

`docs/CURRENT_STATUS.md` 和 `docs/PLAN.md` 仍描述旧分支、旧提交及“冻结完整 ML、Dashboard”的历史阶段，与当前 `main` 已合并 Module 2、Module 3 的事实不一致。Module 1 README 也仍以旧硬件组合为主。

建议动作：四传感器 PR 合并后统一刷新状态、计划、决策和模块 README；历史阶段保留为明确标记的归档段落，不再作为当前执行入口。

验收条件：根 README、CURRENT_STATUS、PLAN、共享契约和各模块 README 对模块状态、硬件清单、目录和下一步没有相互矛盾。

### X-04：项目许可证未确定（P2）

仓库根目录没有 `LICENSE`。这不会阻止本地开发，但会使团队代码的对外授权、第三方实现复用和发布条件不清晰。

建议动作：由项目负责人和团队明确发布策略后添加根许可证；在此之前继续只把 GPL/AGPL 参考仓库用于对照，复制 MIT 代码时保留原始通知。

验收条件：根许可证、第三方通知和 README 的发布说明一致。

## 8. 建议执行顺序

1. Module 1 负责人发起四传感器 PR；审核、修复并合并。
2. 解决 X-01，让无雷达实时热特征真正进入 Module 2。
3. 合并 Module 2 双实现并添加 Module 2 CI。
4. 用真实会话建立可复现的 Module 2 训练与评估基线。
5. 实现 Module 4 确定性推荐 adapter。
6. 实现 Dashboard、认证后偏好和显式选择流程。
7. 建立 Gate A–D 集成测试与最终演示记录。
8. 最后统一状态文档并处理项目许可证决策。

任何步骤如需修改跨模块负载，必须同时更新 `docs/module-specs/00_SHARED_CONTRACT.md`、对应 JSON Schema、fixture 和受影响测试。
