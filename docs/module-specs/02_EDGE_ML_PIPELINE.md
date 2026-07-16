# 模块 2：数据与边缘机器学习

## 交付给 AI 的执行指令

你负责实现 Privacy-Preserving Study Space Advisor 的数据与边缘机器学习模块。先完整阅读 `00_SHARED_CONTRACT.md` 和模块 1 的输出契约，然后检查仓库，在 `edge/ml/` 中实现可复现的数据校验、特征工程、训练、评估、模型导出和 Raspberry Pi 5 在线推理。你的最终输出不是一个 notebook，而是一套可通过命令行和测试重复运行的工程。真实数据不足时先使用共享夹具和合成数据贯通流程，但不得把合成指标当作真实效果。持续执行直到离线与在线特征一致、模型包可加载、边缘观察负载通过契约校验、测试和基准报告完成。

## 1. 模块使命

把模块 1 产生的多传感器采样窗口转换成稳定、可解释的融合特征，训练课堂状态分类模型，并在 Raspberry Pi 5 本地输出四分类状态、占用等级、初始适合度和置信度。

## 2. 负责范围

本模块负责：

- 数据会话读取、校验、清洗和标签检查。
- 热阵列、雷达、声音和环境数据的特征工程。
- Random Forest 主模型和至少两个基线模型。
- 按采集会话分组的数据划分，防止时间相邻样本泄漏。
- 指标、混淆矩阵、特征重要性和错误分析。
- 模型、特征 Schema、标签映射和 Model Card 导出。
- Raspberry Pi 5 在线推理服务或本地推理循环。
- 把结果转换为共享契约第 7 节的边缘观察负载。
- 生成可选的归一化单帧热图预览，通过独立短时接口提交。
- 低置信度、缺失传感器、模型不兼容时的降级逻辑。

本模块不负责：

- 传感器底层驱动和接线。
- 后端数据库、历史预测或房间推荐排序。
- 用户界面和 LLM 文本生成。

## 3. 目标类别

训练的四个目标类别固定为：

```text
empty_or_low_activity
quiet_study_recommended
discussion_allowed
not_recommended_noisy_or_crowded
```

`unknown` 由在线推理的降级策略产生，不作为常规训练标签。

如果四分类在真实、按会话隔离的测试集上长期无法可靠区分，可以启用三分类实验：

```text
empty
suitable_for_study
not_suitable_for_study
```

三分类只能作为显式 fallback；必须保留四分类实验结果并在 Model Card 解释切换原因。最终跨模块枚举仍需通过适配层映射，不得静默改变共享契约。

## 4. 建议技术基线

- Python、NumPy、pandas、scikit-learn、joblib。
- 数据与训练配置采用 YAML/TOML。
- 测试采用 `pytest`。
- 可视化用于报告，但生产推理不得依赖 notebook 或图形环境。
- 固定随机种子，保存数据清单哈希、配置和包版本。

优先使用可解释、可在 Raspberry Pi 5 上快速运行的模型，不引入没有明确收益的深度学习框架。

## 5. 目录和流水线

```text
edge/ml/
|-- README.md
|-- pyproject.toml
|-- configs/
|   |-- features.yaml
|   `-- train.yaml
|-- src/study_space_ml/
|   |-- data/
|   |   |-- loader.py
|   |   |-- validation.py
|   |   `-- split.py
|   |-- features/
|   |   |-- thermal.py
|   |   |-- radar.py
|   |   |-- sound.py
|   |   |-- environment.py
|   |   `-- fusion.py
|   |-- training/
|   |   |-- baselines.py
|   |   |-- train.py
|   |   `-- evaluate.py
|   |-- inference/
|   |   |-- predictor.py
|   |   |-- confidence.py
|   |   `-- payload.py
|   `-- schemas.py
|-- scripts/
|   |-- validate_dataset.py
|   |-- train_model.py
|   |-- evaluate_model.py
|   |-- export_model.py
|   `-- benchmark_pi.py
|-- artifacts/             # 默认不提交大型二进制模型，按仓库策略处理
`-- tests/
```

## 6. 数据要求

### 6.1 采集目标

- 原型目标为每类 100 至 200 个有效窗口。
- 数据至少来自多个独立采集会话；同一连续录制切出的窗口不得同时出现在训练集和测试集。
- 尽量覆盖不同人数、位置、光照、温湿度、背景热源和声音条件。
- 每个会话记录设备版本、采样配置、房间和场景说明。
- 不记录参与者姓名、学号、原始语音或 RGB 图像。

### 6.2 数据验证

验证器至少检查：

- 必填字段、时间顺序、标签枚举和 Schema 版本。
- 热矩阵形状、有限值比例和合理温度范围。
- 雷达样本数、损坏帧统计和目标字段范围。
- 声音只有统计量，没有原始波形引用。
- 环境值单位和明显异常值。
- 窗口完整度和传感器健康状态。
- 重复 `window_id` 和重复内容哈希。

验证输出一份机器可读 JSON 报告和人类可读摘要。严重错误拒绝进入训练；轻微问题可保留但必须记录。

## 7. 特征工程

特征名、顺序、数据类型、缺失值策略和版本必须写入 `feature_schema.json`。离线训练和在线推理调用同一套特征函数。

### 7.1 热阵列候选特征

- 全局均值、标准差、最小值、最大值和高分位数。
- 相对背景的热点像素比例。
- 连通热点区域数量、面积统计和热质心变化。
- 帧间差异、活动程度和时间稳定性。
- 不保存或上传可识别的重建结果。

背景估计必须避免把当前人的热量直接当成永久背景；策略和更新速度可配置。

### 7.2 雷达候选特征

- 当前和窗口内最大/平均活动目标数。
- 速度或位移统计。
- 有活动帧比例。
- 空间分布或轨迹长度的匿名聚合。
- 丢包率和有效样本比例。

不得创建跨窗口个人标识特征。

### 7.3 声音候选特征

- RMS 均值、标准差、峰值。
- 高于安静阈值的时间比例。
- 窗口内强度变化或短时波动。

### 7.4 环境候选特征

- 光照均值。
- 温度、湿度及其舒适区偏差。
- 缺失标记。

### 7.5 融合与缺失值

- 组合成固定顺序的一维数值特征向量。
- 缺失策略必须与训练 Pipeline 一起保存，例如中位数填补加缺失指示器。
- 任何新增/删除/重排特征都提升 `feature_schema_version`。
- 模型加载时检查 Schema 兼容性，不兼容则拒绝推理并报告 `unknown`。

## 8. 数据划分与防泄漏

- 使用 group split，`session_id` 为最小分组单位。
- 推荐训练/验证/测试约为 70/15/15；数据少时使用 GroupKFold 并保留最终独立测试会话。
- 预处理、缺失值填补和缩放只在训练折拟合。
- 不把场景标签、文件名、采集顺序或未来信息作为模型特征。
- 报告每个集合的会话数、窗口数和类别分布。

## 9. 模型训练

必须包含：

1. 规则或多数类基线。
2. Logistic Regression 或 Decision Tree 基线。
3. Random Forest 主模型。

可选比较 SVM、kNN 或 Random Forest Regressor，但不得因为比较模型而延误稳定的主流水线。

Random Forest 调参范围保持小而可解释，至少考虑树数量、最大深度、最小叶节点样本和类别权重。调参只使用训练/验证数据。

## 10. 评估和质量门槛

必须报告：

- Accuracy。
- Macro Precision、Macro Recall、Macro F1。
- 每类 Precision、Recall、F1 和样本数。
- 混淆矩阵。
- 预测置信度分布。
- 特征重要性或 permutation importance。
- 按会话和场景的错误样例分析。

质量目标：

- 目标：独立测试会话 Macro F1 不低于 0.75，且任何主要类别 Recall 不低于 0.60。
- 如果 Macro F1 低于 0.65，不得宣称四分类可靠；执行数据/特征诊断并评估三分类 fallback。
- 0.65 至 0.75 之间可以用于课程原型，但 Dashboard 和 Model Card 必须明确展示置信度与限制。
- 合成数据指标只验证流水线，不能用于达成以上真实数据门槛。

## 11. 置信度与降级

- 默认低置信度阈值建议从 0.55 开始，并通过验证集校准。
- 置信度低于阈值时输出 `room_state=unknown`，保留模型最高类别到仅本地诊断字段，不上传为确定状态。
- 热阵列或雷达单独 degraded 时允许推理，但需在训练中验证对应缺失策略并添加 warning。
- 热阵列和雷达同时 offline 时直接输出 `unknown`。
- 模型文件损坏、Schema 不兼容或输入窗口过期时拒绝正常分类。

## 12. 占用等级与初始适合度

优先由模型或经验证的规则从融合特征派生：

```text
empty | low | medium | high | unknown
```

初始 `suitability_score` 是边缘端对当前环境的粗略 0 至 100 分，不包含个人偏好。映射必须确定、可测试，并在文档中解释。例如：

- quiet 状态基础分高。
- discussion 状态对通用适合度为中等。
- crowded/noisy 状态基础分低。
- 舒适光照、温湿度可做小幅修正。
- `unknown` 不得给出高分。

最终个性化排序由模块 4 完成。

## 13. 模型包

导出目录至少包含：

```text
model-package/
|-- model.joblib
|-- feature_schema.json
|-- labels.json
|-- preprocessing.json
|-- metrics.json
|-- training_manifest.json
|-- requirements-lock.txt
`-- MODEL_CARD.md
```

`training_manifest.json` 包含随机种子、数据清单哈希、训练配置、代码版本和时间。模型包加载时验证必需文件、版本和哈希。

## 14. 在线推理

在线路径：

```text
SensorWindow -> validation -> feature extraction -> preprocessing
-> classifier -> confidence/degradation -> occupancy/suitability
-> EdgeObservation payload
```

要求：

- 单窗口推理不得访问未来窗口。
- 推理过程不把原始完整热矩阵和雷达轨迹写入日志或上传。
- 如果启用热图预览，只从当前窗口生成一份 32 x 24、0 至 1 的归一化静态矩阵；不包含绝对温度、不形成连续帧，并按共享契约的独立端点发送。
- 后端暂时不可用时，将有限数量的观察负载写入本地可靠队列，恢复后按 `observation_id` 重试。
- 队列大小和保留时间可配置；满时采用明确策略并记录丢弃计数。
- 提供 `--dry-run`，只打印脱敏摘要而不发送后端。

## 15. Raspberry Pi 5 性能基准

在目标设备或等价环境测量：

- 模型加载时间。
- 单窗口特征提取和推理延迟。
- 进程内存占用。
- 连续运行时 CPU 使用率。
- 模型包大小。

目标是 5 秒窗口内从窗口关闭到产生预测不超过 1 秒；若未达到，必须说明瓶颈和优化方案。

## 16. 测试要求

### 单元测试

- 每组特征的确定性、形状和异常输入。
- 离线与在线相同窗口产生完全相同的特征顺序和数值容差结果。
- 标签映射、缺失值、低置信度和状态映射。
- 模型包版本、缺文件和损坏哈希处理。
- EdgeObservation 通过共享 JSON Schema。
- 热图预览长度、归一化范围和禁持久化元数据符合共享契约。

### 流水线测试

- 使用小型固定夹具完成 validate、train、evaluate、export、load、predict 全流程。
- 固定数据和随机种子产生可重复指标。
- 测试集 session 不出现在训练集。

### 集成测试

- 消费模块 1 正常和 degraded 窗口。
- 生成模块 3 可接受的有效、unknown 和重试负载。
- 使用模拟器连续推理至少 2 分钟，无内存持续增长或未处理异常。

## 17. 验收标准

- [ ] 数据验证器能指出结构、标签和隐私问题。
- [ ] 特征 Schema 已版本化，离线/在线共享同一实现。
- [ ] 至少比较两个基线和 Random Forest。
- [ ] 使用按会话隔离的评估，不存在明显数据泄漏。
- [ ] 指标、混淆矩阵和错误分析完整。
- [ ] 模型包可在新进程和 Raspberry Pi 5 环境加载。
- [ ] 低置信度和传感器故障正确输出 `unknown` 或 degraded warning。
- [ ] 输出负载符合共享契约，不含原始语音、完整热帧或长期雷达轨迹。
- [ ] README 包含从数据验证到边缘推理的全部命令。
- [ ] 所有测试和性能基准完成。

## 18. 最终交付物

- `edge/ml/` 工程源码和配置。
- 可复现训练/评估/导出命令。
- 模型包和 Model Card。
- 指标报告、混淆矩阵和错误分析。
- Raspberry Pi 5 基准报告。
- 正常、低置信度和 degraded 的 EdgeObservation 夹具。
- `MODULE2_HANDOFF.md`，说明模型版本、输入 Schema、输出字段、已知限制和模块 3 接入方法。
