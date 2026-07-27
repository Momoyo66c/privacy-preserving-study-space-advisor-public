# Integration Tests

存放跨模块端到端测试，按 Gate A 至 Gate D 逐步建立。测试优先使用模拟器和共享契约，并允许在没有真实硬件和 LLM Key 时运行。

## Gate A：模拟数据贯通

Gate A 使用真实模块实现完成以下路径：

```text
Module 1 deterministic simulator
  -> SensorWindow
  -> Module 2 EdgePredictor
  -> EdgeObservation
  -> Module 3 POST /api/v1/edge/observations
  -> status/history/recommendation APIs
  -> Module 4 Dashboard in real API mode
```

Python 契约与 API smoke：

```bash
python -m pip install -e './edge/hardware' -e './edge/ml[dev,thermal]' -e './backend[dev]'
python -m pytest -q tests/integration/test_gate_a.py
```

Dashboard real API E2E：

```bash
cd frontend
npm ci
npx playwright install chromium
npm run gate-a:e2e
```

测试后端使用临时 SQLite 数据库、三个虚构房间和 Module 1 当次生成的模拟窗口，不写入项目数据库，不需要 LLM Key，也不会发送完整热帧、声音波形或雷达轨迹。

## Gate C：正式推荐与降级

Gate C 的仓库级集成测试固定验证三个房间的 quiet/discussion 排名、LLM
成功与断线时确定性字段不变，以及单个环境传感器离线不会阻断推荐：

```bash
python -m pytest -q tests/integration/test_gate_c.py
```

测试使用内存中的 fake explanation provider，不要求 CI 安装 Ollama。真实
Windows Ollama 的 E 盘配置和性能结果见
[`../../docs/GATE_C_LOCAL_LLM.md`](../../docs/GATE_C_LOCAL_LLM.md)。
