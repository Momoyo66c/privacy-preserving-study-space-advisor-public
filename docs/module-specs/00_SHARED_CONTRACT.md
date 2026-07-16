# 共享系统契约

## 1. 文档目的

本文档是四个模块之间唯一的公共接口基线。实现者可以在模块内部自由选择类、函数和文件组织，但不得在未同步的情况下修改本文件定义的字段、枚举、语义和隐私约束。

## 2. 项目目标

构建一个运行在 Raspberry Pi 5 和本地/轻量后端上的隐私保护型学习空间推荐系统。系统融合 MLX90640 低分辨率热阵列、HLK-LD2450 mmWave 雷达、声音强度、光照、温湿度等信号，在边缘端判断空间状态；后端保存历史并预测短期占用趋势；推荐层结合用户偏好对房间排序，并用自然语言解释结果。

## 3. 强制隐私原则

- 禁止引入 RGB 摄像头、面部识别、人体身份追踪或个人画像。
- 声音模块只能输出强度或统计特征；原始波形不得写入持久存储、日志或 API。
- 热阵列只用于整体占用和活动估计。若前端显示热图，必须保持 32 x 24 或更低的非识别分辨率。
- 雷达轨迹只能使用匿名临时目标编号；不得跨采样窗口关联为个人身份。
- 日志不得包含密钥、完整提示词中的个人信息或可识别的原始传感器内容。
- LLM 只能接收结构化房间状态、环境摘要、预测和偏好，不得接收原始热阵列、原始雷达帧或声音波形。

## 4. 核心枚举

### 4.1 `room_state`

```text
empty_or_low_activity
quiet_study_recommended
discussion_allowed
not_recommended_noisy_or_crowded
unknown
```

`unknown` 仅用于传感器不足、模型未加载、置信度低于阈值或数据过期等降级场景，不属于模型训练的四个目标类别。

### 4.2 `occupancy_level`

```text
empty
low
medium
high
unknown
```

### 4.3 `sensor_health`

```text
ok
degraded
offline
not_configured
```

### 4.4 `study_mode`

```text
quiet
discussion
any
```

## 5. 时间、标识与版本规则

- 所有时间使用 UTC ISO 8601，例如 `2026-07-16T06:30:00Z`。
- `room_id`、`device_id`、`observation_id` 使用稳定的 ASCII 字符串。
- 所有跨模块负载必须包含 `schema_version`，第一版固定为 `1.0`。
- 后端以 `observation_id` 实现幂等写入；重复提交不得生成重复记录。
- 实时状态默认在 30 秒后标记为 stale；阈值必须可配置。

## 6. 模块 1 到模块 2：采样窗口契约

模块 1 暴露一个标准化采样窗口，不要求使用网络传输。推荐在同一 Raspberry Pi 进程内通过 Python 对象或本地队列交付，并提供可序列化的测试夹具。

```json
{
  "schema_version": "1.0",
  "window_id": "room_a-20260716T063000.000Z",
  "room_id": "room_a",
  "device_id": "pi5-a",
  "window_start": "2026-07-16T06:30:00Z",
  "window_end": "2026-07-16T06:30:05Z",
  "thermal": {
    "health": "ok",
    "frame_count": 20,
    "frames_ref": "local://session-001/window-0001/thermal.npz"
  },
  "radar": {
    "health": "ok",
    "sample_count": 50,
    "tracks": []
  },
  "sound": {
    "health": "ok",
    "rms_mean": 0.18,
    "rms_std": 0.04,
    "peak": 0.41
  },
  "environment": {
    "light_lux": 420.0,
    "temperature_c": 24.8,
    "humidity_pct": 61.0
  },
  "quality": {
    "completeness": 0.98,
    "warnings": []
  }
}
```

要求：

- 默认窗口为 5 秒，可配置为 5 至 10 秒。
- `frames_ref` 只允许在本机离线训练数据中出现，不上传后端。
- 缺失传感器必须通过 `health` 和 `quality.warnings` 表达，禁止伪造零值。
- 模块 2 必须能够使用模拟夹具运行，不得强依赖真实硬件才能测试。

## 7. 模块 2 到模块 3：边缘观察负载

HTTP：`POST /api/v1/edge/observations`

```json
{
  "schema_version": "1.0",
  "observation_id": "01J2Y7YQKQ4J0A4J8R6F5W0M1N",
  "room_id": "room_a",
  "device_id": "pi5-a",
  "observed_at": "2026-07-16T06:30:05Z",
  "window_seconds": 5,
  "room_state": "quiet_study_recommended",
  "occupancy_level": "low",
  "suitability_score": 86,
  "confidence": 0.88,
  "features": {
    "thermal_hot_region_count": 2,
    "radar_active_target_count": 1,
    "sound_rms_mean": 0.18,
    "light_lux": 420.0,
    "temperature_c": 24.8,
    "humidity_pct": 61.0
  },
  "sensor_health": {
    "thermal": "ok",
    "radar": "ok",
    "sound": "ok",
    "environment": "ok"
  },
  "model": {
    "name": "room-state-random-forest",
    "version": "1.0.0",
    "feature_schema_version": "1.0"
  },
  "warnings": []
}
```

约束：

- `suitability_score` 为 0 至 100 的整数。
- `confidence` 为 0 至 1 的浮点数。
- `features` 只能包含摘要，不得包含完整热帧、声音波形或可长期关联的轨迹。
- 如果关键传感器失效或模型置信度不足，允许发送 `room_state=unknown`，同时在 `warnings` 解释原因。

成功响应：

```json
{
  "schema_version": "1.0",
  "accepted": true,
  "observation_id": "01J2Y7YQKQ4J0A4J8R6F5W0M1N",
  "server_received_at": "2026-07-16T06:30:06Z"
}
```

## 8. 模块 3 到模块 4：查询契约

最低必需接口：

```text
GET  /health
GET  /api/v1/rooms
GET  /api/v1/rooms/status
GET  /api/v1/rooms/{room_id}
GET  /api/v1/rooms/{room_id}/history?hours=24
GET  /api/v1/rooms/{room_id}/forecast?minutes=30
GET  /api/v1/rooms/{room_id}/thermal-preview
PUT  /api/v1/preferences/{profile_id}
GET  /api/v1/preferences/{profile_id}
POST /api/v1/recommendations
```

### 8.1 隐私保护热图预览契约

为满足 Dashboard 的低分辨率热图展示，模块 2 可以通过独立端点提交“预览”，不得把它混入 Observation 或历史数据库：

```text
PUT /api/v1/edge/rooms/{room_id}/thermal-preview
```

```json
{
  "schema_version": "1.0",
  "room_id": "room_a",
  "captured_at": "2026-07-16T06:30:05Z",
  "width": 32,
  "height": 24,
  "values": [0.0, 0.1, 0.2],
  "normalization": "window_min_max_clipped",
  "expires_in_seconds": 30
}
```

约束：

- `values` 实际长度必须等于 `width * height`；示例为缩略展示。
- 只发送 0 至 1 的归一化预览值，不发送绝对温度、连续帧或人员轨迹。
- 后端只在内存中保留每个房间最新一份，最多 30 秒；不得写入数据库、备份或普通日志。
- 预览不得发送给 LLM。
- 预览缺失或过期不影响推荐，前端显示明确的 unavailable 状态。

`POST /api/v1/recommendations` 请求：

```json
{
  "schema_version": "1.0",
  "profile_id": "demo-user",
  "study_mode": "quiet",
  "preferences": {
    "quiet_priority": 0.9,
    "low_occupancy_priority": 0.8,
    "brightness_priority": 0.4,
    "comfort_priority": 0.5,
    "distance_priority": 0.3
  },
  "candidate_room_ids": ["room_a", "room_b", "room_c"]
}
```

响应中的每个候选房间至少包含：

```json
{
  "room_id": "room_a",
  "rank": 1,
  "score": 88,
  "current_state": "quiet_study_recommended",
  "occupancy_level": "low",
  "forecast_30m": "low",
  "confidence": 0.88,
  "is_stale": false,
  "reasons": [
    "当前适合安静学习",
    "预计未来 30 分钟保持低占用"
  ],
  "explanation": "Room A is currently quiet and is expected to remain lightly occupied."
}
```

## 9. 错误格式

所有 HTTP 错误统一返回：

```json
{
  "schema_version": "1.0",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable summary",
    "details": {},
    "request_id": "req-123"
  }
}
```

不得把堆栈、密钥、数据库连接信息或完整 LLM 请求暴露给前端。

## 10. 跨模块测试夹具

`shared/fixtures/` 至少提供：

- `sensor_window_empty.json`
- `sensor_window_quiet.json`
- `sensor_window_discussion.json`
- `sensor_window_crowded.json`
- `sensor_window_degraded.json`
- `edge_observation_valid.json`
- `edge_observation_unknown.json`
- `recommendation_request.json`
- `recommendation_response.json`
- `thermal_preview.json`

JSON Schema 放在 `shared/contracts/`，CI 中必须校验示例负载。

## 11. 集成门禁

### Gate A：模拟数据贯通

模拟采样窗口经过模块 2 推理，成功写入模块 3，并在模块 4 Dashboard 显示。

### Gate B：真实传感器贯通

至少 MLX90640、LD2450 和一个环境/声音传感器使用真实硬件运行；其他传感器可以明确标记为 degraded，但不得静默伪造。

### Gate C：推荐与降级

至少三个模拟房间可排序。关闭 LLM 后，推荐排序和模板解释仍可用；断开一个传感器后，系统显示降级状态而不崩溃。

### Gate D：最终演示

连续运行至少 15 分钟，展示当前状态变化、历史趋势、未来预测、偏好变化造成的推荐变化、本地 LED/micro:bit 指示，以及隐私说明。

## 12. 变更管理

- 契约修改必须同时更新 JSON Schema、示例负载和受影响测试。
- 破坏兼容性的变更提升 `schema_version`。
- 每个模块应维护 `README`、运行命令、环境变量示例和测试命令。
- 新增依赖前确认 Raspberry Pi 5 可安装、许可证可接受且没有不必要的云端数据上传。
