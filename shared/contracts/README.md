# Shared Contracts

存放跨模块 JSON Schema、枚举和版本说明。修改契约时同时更新：

- `docs/module-specs/00_SHARED_CONTRACT.md`
- 对应 fixture
- 生产方和消费方测试

当前 `1.0` Schema：

- `edge_observation.schema.json`：模块 2 提交给模块 3 的脱敏观察摘要。
- `thermal_preview.schema.json`：只在内存中短时保留的 32 x 24 归一化预览。
- `room_metadata.schema.json`、`room_status.schema.json`、`room_history.schema.json`、`forecast_result.schema.json`：模块 3 查询响应。
- `preference_profile.schema.json`、`recommendation_*.schema.json`：模块 4 集成边界。
- `error.schema.json`：统一错误信封。

所有跨模块响应和错误信封都包含 `schema_version=1.0`。降级 Observation 的已知 feature 可以省略或使用 `null`，不得伪造为零。
