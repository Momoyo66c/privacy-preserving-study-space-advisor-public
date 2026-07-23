# Shared Contracts

## Authenticated preference-learning contracts

- `auth_credentials.schema.json` and `auth_session_response.schema.json`: local username/password session bootstrap. Passwords appear only in the request and must never be logged or persisted in plaintext.
- `authenticated_recommendation_request.schema.json`: sends only study mode and candidate room IDs. User identity and effective preferences come from the current server session.
- `me_preferences.schema.json`: separates manual, learned, and effective values plus per-dimension evidence counts.
- `me_preference_update.schema.json`: updates manual preferences and the learning switch.
- `room_selection_request.schema.json`, `room_selection_accepted.schema.json`, and `room_selection_history.schema.json`: record and return explicit choices with UUID idempotency keys. Client timestamps and client-supplied user IDs are forbidden.
- `user_response.schema.json` and `delete_result.schema.json`: current local-user summary and destructive-action result.

存放跨模块 JSON Schema、枚举和版本说明。修改契约时同时更新：

- `docs/module-specs/00_SHARED_CONTRACT.md`
- 对应 fixture
- 生产方和消费方测试

当前 `1.0` Schema：

- `sensor_window.schema.json`：模块 1 输出、模块 2 输入的 5–10 秒传感器窗口契约，版本 `1.0`。
- `edge_observation.schema.json`：模块 2 或受限实时桥接提交给模块 3 的脱敏观察摘要；可选相对声音峰值和相对光照字段均限制在 0 至 1。
- `thermal_preview.schema.json`：只在内存中短时保留的 32 x 24 归一化预览。
- `room_metadata.schema.json`、`room_status.schema.json`、`room_history.schema.json`、`forecast_result.schema.json`：模块 3 查询响应。
- `preference_profile.schema.json`、`recommendation_*.schema.json`：模块 4 集成边界。
- `error.schema.json`：统一错误信封。

验证模块 1 示例：

```bash
cd edge/hardware
python -m pytest tests/test_contract_fixtures.py
```

契约禁止未声明字段，时间使用 UTC RFC 3339 格式。所有跨模块负载和错误信封都包含 `schema_version=1.0`。缺失传感器通过 `health`、`quality.warnings` 和可空字段表达；降级 Observation 的已知 feature 可以省略或使用 `null`，不得伪造为零。
