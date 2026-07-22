# 模块 3：后端与数据智能

## 交付给 AI 的执行指令

你负责实现 Privacy-Preserving Study Space Advisor 的后端、数据库和短期占用预测。先完整阅读 `00_SHARED_CONTRACT.md`，然后检查仓库，在 `backend/` 中实现 FastAPI 服务、数据模型、迁移、观察写入、房间状态查询、历史聚合、未来 15 至 30 分钟预测、偏好存储和推荐适配接口。模块 4 拥有推荐排序和 LLM 解释算法；你必须定义并暴露 `/api/v1/recommendations` 路由，通过可替换 adapter 调用模块 4，在模块 4 未完成时使用确定的 stub 保障后端测试。持续执行直到 API Schema、数据库迁移、幂等性、预测降级、测试、容器/本地运行和交接文档全部完成。

## 1. 模块使命

建立一个轻量、可靠、可测试的系统中枢：接收 Raspberry Pi 5 的边缘分类结果，保存房间状态和环境摘要，提供实时/历史查询，基于历史数据预测未来占用等级，并向推荐与前端模块提供稳定 API。

## 2. 负责范围

本模块负责：

- HTTP API、请求验证、统一错误处理和 OpenAPI 文档。
- SQLite 原型数据库；保留切换 MySQL/PostgreSQL 的清晰边界。
- 房间、设备、观察、偏好、预测和推荐记录的数据模型。
- 低分辨率热图预览的短时内存缓存和过期查询；禁止持久化。
- 边缘观察幂等写入、最新状态和 stale 判断。
- 历史序列查询与按时间槽聚合。
- 未来 15 至 30 分钟占用等级预测及其降级方案。
- 健康检查、结构化日志、配置和迁移。
- 推荐 adapter 的接口、路由和持久化；具体排序/LLM 逻辑归模块 4。
- 本地匿名账号、会话、选择事件和派生偏好的后端基础设施；不收集姓名、邮箱或学号。

本模块不负责：

- 传感器采集和模型训练。
- 解释完整热阵列或原始雷达数据。
- 推荐评分算法和前端页面视觉实现。
- 校园统一认证、密码找回、管理员后台和生产级多租户权限系统。

## 3. 技术基线

- Python 3.11。
- FastAPI、Pydantic、SQLAlchemy、Alembic。
- 原型默认 SQLite；测试使用临时独立数据库。
- `pytest` + FastAPI test client/httpx。
- 配置来自环境变量和 `.env.example`，不得提交真实密钥。
- 时间统一使用 UTC，数据库保存 timezone-aware 时间。

若仓库已有等价技术栈，优先保持一致；不得同时维护两套后端框架。

## 4. 建议目录

```text
backend/
|-- README.md
|-- pyproject.toml
|-- .env.example
|-- alembic.ini
|-- migrations/
|-- src/study_space_api/
|   |-- main.py
|   |-- config.py
|   |-- logging.py
|   |-- database.py
|   |-- errors.py
|   |-- models/
|   |-- schemas/
|   |-- repositories/
|   |-- services/
|   |   |-- observations.py
|   |   |-- room_status.py
|   |   |-- history.py
|   |   |-- forecasting.py
|   |   `-- recommendations.py
|   |-- adapters/
|   |   |-- recommendation.py
|   |   `-- recommendation_stub.py
|   `-- api/v1/
|       |-- edge.py
|       |-- rooms.py
|       |-- preferences.py
|       `-- recommendations.py
|-- scripts/
|   |-- seed_demo.py
|   `-- generate_history.py
`-- tests/
```

## 5. 数据模型

### 5.1 Room

最低字段：

- `id`: 稳定 `room_id`，主键。
- `name`: 显示名称。
- `location`: 可选的人类可读位置。
- `latitude`、`longitude`: 可选，用于距离偏好；原型可为空。
- `capacity_band`: 可选的小/中/大，不要求精确座位数。
- `active`: 是否参与推荐。
- `created_at`、`updated_at`。

### 5.2 Device

- `id`: `device_id`。
- `room_id`。
- `model`、`firmware_version`。
- `last_seen_at`。
- `active`。

### 5.3 Observation

保存共享契约中的边缘观察负载，至少包含：

- `observation_id` 唯一索引。
- `room_id`、`device_id`、`observed_at`、`received_at`。
- `room_state`、`occupancy_level`。
- `suitability_score`、`confidence`。
- `feature_summary_json`。
- `sensor_health_json`、`warnings_json`。
- `model_name`、`model_version`、`feature_schema_version`。

不得保存完整热阵列、声音波形或长期个人轨迹。

### 5.4 PreferenceProfile

- `profile_id`。
- `study_mode`。
- `quiet_priority`、`low_occupancy_priority`、`brightness_priority`、`comfort_priority`、`distance_priority`，范围 0 至 1。
- 可选 `preferred_temperature_c`。
- `created_at`、`updated_at`。

不要求保存真实姓名、学号或邮箱。演示默认使用匿名 profile。

### 5.5 Forecast

- `room_id`、`generated_at`、`target_at`、`horizon_minutes`。
- `predicted_occupancy_level`。
- `confidence` 或可用性评分。
- `method`、`model_version`。
- `input_start_at`、`input_end_at`。
- `fallback_reason`。

### 5.6 RecommendationRecord

- 请求 ID、匿名 profile ID、生成时间。
- 候选房间、最终排名和分数。
- 规则理由、LLM 是否使用、LLM provider/model 标识。
- 降级原因和延迟。

不得保存 API 密钥或不必要的完整提示词。

## 6. API 要求

### 6.1 `GET /health`

返回应用、数据库和推荐 adapter 的状态。即使推荐 adapter 不可用，只要核心 API 可用，HTTP 可返回 200 并把该依赖标记为 degraded。

### 6.2 `POST /api/v1/edge/observations`

- 严格验证共享契约第 7 节。
- `observation_id` 重复时返回与首次写入一致的成功语义，不重复插入。
- 未知房间或设备的策略可配置：原型可自动登记设备，但房间必须预先存在或明确使用 seed。
- `observed_at` 过度超前或过旧时添加 warning 或拒绝，阈值可配置。
- 保存后更新设备 `last_seen_at`。
- 不在日志中输出完整 features JSON；只记录 ID、房间、状态、延迟和结果。

### 6.3 房间查询

`GET /api/v1/rooms` 返回房间元数据。

`GET /api/v1/rooms/status` 返回所有 active 房间的最新观察、数据年龄、`is_stale`、最近预测和传感器降级摘要。

`GET /api/v1/rooms/{room_id}` 返回单房间当前状态和元数据。

没有观察数据时返回房间对象和 `room_state=unknown`，不是 500。

### 6.4 历史查询

`GET /api/v1/rooms/{room_id}/history?hours=24&bucket_minutes=5`

返回：

- 时间桶。
- 主要/最后 room state。
- 平均 suitability 和 confidence。
- 占用等级的序数聚合。
- 声音、光照、温湿度摘要。
- 缺失桶或数据覆盖率。

限制最大查询跨度和返回点数，防止一次加载整个数据库。

### 6.5 预测查询

`GET /api/v1/rooms/{room_id}/forecast?minutes=30`

- `minutes` 第一版支持 15 或 30。
- 返回预测占用等级、目标时间、方法、置信/可靠性和降级原因。
- 数据不足时仍返回一个明确的 fallback 结果，不抛 500。

### 6.6 偏好接口

`PUT /api/v1/preferences/{profile_id}` 做 upsert，并验证 0 至 1 范围。

`GET /api/v1/preferences/{profile_id}` 在不存在时返回明确 404；前端可创建默认 profile。

### 6.7 热图预览

`PUT /api/v1/edge/rooms/{room_id}/thermal-preview` 严格验证 32 x 24、0 至 1 的归一化值，只把每个房间的最新预览保存在进程内存中，最长 30 秒。

`GET /api/v1/rooms/{room_id}/thermal-preview` 返回最新未过期预览。不存在或已过期时返回明确的 unavailable 响应，不回退到数据库历史。

预览不得进入 ORM 模型、数据库、备份、普通请求日志或推荐/LLM 上下文。

### 6.8 推荐路由

`POST /api/v1/recommendations`：

1. 验证请求和候选房间。
2. 加载当前状态、预测和房间元数据。
3. 调用 `RecommendationAdapter.rank(context)`。
4. 保存推荐记录。
5. 返回共享契约格式。

模块 3 只定义 adapter protocol 和 stub。模块 4 提供正式 adapter。stub 必须确定、明显标记 `explanation_source=stub`，不得被误认为最终推荐算法。

## 7. 最新状态与 stale 逻辑

- 对每个房间选择 `observed_at` 最新且已接受的 Observation。
- 默认超过 30 秒为 stale，可配置。
- stale 状态仍可显示，但推荐算法必须受到明显惩罚或排除。
- 如果设备 offline、关键传感器 degraded 或状态 unknown，在响应中原样暴露。
- 服务端接收时间和设备观察时间都保留，用于诊断时钟漂移和网络延迟。

## 8. 历史占用编码

预测内部可以使用序数映射：

```text
empty=0, low=1, medium=2, high=3
```

`unknown` 不直接映射为 0；应作为缺失值处理。输出时必须映射回枚举，不向前端暴露含义不清的裸整数。

## 9. 时间序列预测

第一版按由简到繁实现：

1. 同星期/同时间槽历史平均。
2. 最近窗口 rolling average。
3. 在数据足够时比较 Random Forest Regressor 或分类器。

推荐的确定性 fallback：

- 有至少 3 个近期有效点：最近窗口加权平均。
- 近期不足但有同时间槽历史：时间槽平均。
- 只有当前点：保持当前占用等级，低可靠性。
- 完全无数据：`unknown`。

预测服务必须记录使用的方法和输入数据范围。模型训练不得使用目标时间之后的数据。评估至少采用按时间顺序的 backtest，报告 Macro F1/MAE 等适合指标，并与“保持当前值”基线比较。

## 10. 数据保留和隐私

- 原型默认保留 Observation 30 天，可配置。
- 推荐记录默认保留 7 天或课程演示所需最短周期。
- 提供清理命令或后台任务。
- 删除房间/设备时优先软删除或显式迁移，避免误丢演示数据。
- 数据库备份不得包含密钥。
- 开发 seed 使用虚构房间和匿名 profile。

## 11. 可靠性和安全

- 所有输入通过 Pydantic 验证，拒绝 NaN、无限值、越界分数和未知枚举。
- 限制请求体大小，防止上传完整热帧或超大 features。
- CORS 只允许配置的前端 origin。
- LLM 密钥只由模块 4 adapter 在服务端读取，不返回浏览器。
- 日志带 `request_id`，错误响应遵循共享契约。
- 数据库事务失败必须回滚。
- `/health` 不泄露连接字符串和密钥。

原型可使用简单 demo token 保护写入接口；如果不实现认证，必须绑定可信网络并在 README 明确风险。

## 12. 演示数据

提供：

```text
seed_demo.py
```

至少创建三个房间和过去 24 小时的合理历史，使其呈现：

- 一个安静、低占用房间。
- 一个适合讨论的中等占用房间。
- 一个拥挤或即将拥挤的房间。

生成器使用固定种子、明显标注 synthetic，并允许重置。

## 13. 测试要求

### 单元测试

- Schema 边界、枚举、时间和数值验证。
- stale 判断和最新状态选择。
- 占用等级序数映射，不把 unknown 当 empty。
- 预测各级 fallback。
- 推荐 adapter 成功、超时、异常和 stub 行为。
- 热图预览的形状、数值范围、TTL、过期和不落库行为。

### API 测试

- Observation 正常写入、重复写入、非法负载和未知房间。
- 房间无数据、fresh、stale、degraded 状态。
- 历史聚合桶和查询限制。
- 15/30 分钟预测及数据不足。
- 偏好 upsert 和范围验证。
- 统一错误格式和 request ID。

### 数据库测试

- 从空库执行全部迁移。
- 升级后的 Schema 可读写。
- 唯一索引保证幂等。
- 测试相互隔离，不依赖开发数据库。

### 集成测试

- 读取模块 2 的有效和 unknown 夹具。
- 生成模块 4 所需 status、history、forecast 上下文。
- 使用 stub 完成 `/recommendations` 端到端请求。

## 14. 性能目标

原型本地环境中：

- 单个 Observation 写入 P95 小于 300 ms。
- 房间状态列表 P95 小于 500 ms。
- 24 小时历史查询 P95 小于 1 秒。
- 不含外部 LLM 的推荐上下文准备 P95 小于 500 ms。

若目标未达成，提交可复现测量和瓶颈说明，不做无依据的微优化。

## 15. 验收标准

- [ ] 空数据库可通过迁移和 seed 启动。
- [ ] 所有共享 API 路径存在并出现在 OpenAPI。
- [ ] Observation 写入幂等且拒绝隐私违规的大负载。
- [ ] fresh、stale、unknown、degraded 均有明确响应。
- [ ] 历史聚合和 15/30 分钟预测可运行，并提供数据不足 fallback。
- [ ] 模块 4 可通过 adapter 注入正式推荐实现。
- [ ] SQLite 测试通过，数据库访问未散落在路由层。
- [ ] README 包含配置、迁移、seed、启动、测试和 API 示例。
- [ ] `.env.example` 不含真实密钥。
- [ ] 自动测试通过，性能和预测评估报告完成。

## 16. 最终交付物

- `backend/` 源码、迁移和配置示例。
- OpenAPI 文档和共享 JSON Schema 对齐记录。
- 演示 seed 与历史生成器。
- 预测方法、backtest 和限制说明。
- 单元、API、数据库和集成测试。
- `MODULE3_HANDOFF.md`，说明启动方式、数据库位置、端口、API、推荐 adapter 接入点和已知问题。
