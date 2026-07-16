# Shared Contracts

存放跨模块 JSON Schema、枚举和版本说明。修改契约时同时更新：

- `docs/module-specs/00_SHARED_CONTRACT.md`
- 对应 fixture
- 生产方和消费方测试

当前文件：

- `sensor_window.schema.json`：模块 1 输出、模块 2 输入的 5–10 秒传感器窗口契约，版本 `1.0`。

验证示例：

```bash
cd edge/hardware
python -m pytest tests/test_contract_fixtures.py
```

契约禁止额外字段，时间使用 UTC RFC 3339 格式。缺失传感器通过 `health`、`quality.warnings` 和可空字段表达，不得用正常数值填充。
