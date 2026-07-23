# Privacy-Preserving Study Space Advisor

[![Gate A integration](https://github.com/Momoyo66c/privacy-preserving-study-space-advisor/actions/workflows/gate-a-ci.yml/badge.svg)](https://github.com/Momoyo66c/privacy-preserving-study-space-advisor/actions/workflows/gate-a-ci.yml)
[![Backend CI](https://github.com/Momoyo66c/privacy-preserving-study-space-advisor/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/Momoyo66c/privacy-preserving-study-space-advisor/actions/workflows/backend-ci.yml)
[![Module 1 CI](https://github.com/Momoyo66c/privacy-preserving-study-space-advisor/actions/workflows/module1-ci.yml/badge.svg)](https://github.com/Momoyo66c/privacy-preserving-study-space-advisor/actions/workflows/module1-ci.yml)

面向校园学习空间的隐私保护型 AIoT 推荐系统。Raspberry Pi 5 通过 ESP32 Sensor Hub 采集低分辨率热阵列、声音强度、相对光照和温湿度；边缘流程把数据转换为不含身份信息的房间状态摘要；后端负责状态、历史、短期预测、登录会话、选择记录和偏好学习；React Dashboard 展示房间状态、实时传感器、推荐、趋势和隐私说明。共享契约保留可选雷达字段，但最终生产硬件不安装雷达。

> 状态快照（2026-07-23）：最新 `origin/main` 为 `c0cedc8`。当前分支正在把已完成实机验收的四传感器 Module 1、实时展示接口和 Raspberry Pi 接管流程整合到这条主线；Module 2 规则基线、Module 3 后端、Module 4 React Dashboard 和 Gate A 已在主线。

## 当前系统链路

```mermaid
flowchart LR
    H["Module 1：模拟器 / ESP32 四传感器 Hub"] -->|"SensorWindow 1.0"| M["Module 2：校验、特征与规则基线"]
    M -->|"EdgeObservation 1.0"| B["Module 3：FastAPI、SQLite、状态与预测"]
    B -->|"真实 API"| D["Module 4：React Dashboard"]
    B --> S["当前确定性 recommendation stub"]
    S --> D
```

Gate A 已证明模拟链路可以从 Module 1 连续运行到真实后端和浏览器。四传感器采集、匿名会话与实时展示已完成实机侧验收；Gate B 仍需在最新主线上复核真实数据经过 Module 2 推理后的完整链路。正式推荐算法属于 Gate C。

## 模块完成情况

| 模块 | 目录 | 已进入 `main` 的能力 | 仍需完成 |
|---|---|---|---|
| Module 1：传感器与边缘硬件 | `edge/hardware/` | 统一驱动接口、ESP32 Hub、MLX90640/HW-485/HW-486/DHT11、确定性模拟器、窗口化、会话采集与校验、实时预览和无雷达生产配置 | 完成最新 `main` 回归与 PR 审核；HW-485/HW-486 在没有参考仪器前继续按相对值使用 |
| Module 2：边缘 ML | `edge/ml/` | `SensorWindow` 校验、特征提取、确定性规则模型、`EdgeObservation` 生成与后端上传 CLI | 合并或移除根目录第二套 `ml/`；补无雷达实时热特征；用真实标签完成训练、独立评估、Model Card 和 Pi benchmark；增加专用 CI |
| Module 3：后端与数据智能 | `backend/` | FastAPI、SQLite/Alembic、Observation 幂等写入、状态/历史/15–30 分钟预测、热图 TTL、认证、选择记录、偏好学习、清理/seed/backtest、Docker 和后端 CI | 生产部署、安全加固和外部数据库不在当前原型范围；正式推荐算法仍由 Module 4 提供 |
| Module 4：推荐与前端 | `frontend/` 与后端 adapter 边界 | React/Vite Dashboard、mock/真实 API、注册登录、手动偏好、显式选择教室、学生/演示管理视图、组件和 Playwright 测试 | 后端仍使用 `StubRecommendationAdapter`；需实现正式规则评分、模板/LLM 降级；补选择历史、学习开关/重置、删除账号和失败 outbox 等完整 UI |

注意：当前规则模型和 recommendation stub 只用于集成与演示，不能作为真实环境下的分类准确率或正式个性化推荐效果声明。

## 集成门禁

| 门禁 | 目标 | 当前状态 |
|---|---|---|
| Gate A — 模拟数据贯通 | Module 1 模拟窗口 → Module 2 → Module 3 → Dashboard | **已完成并进入 CI**；Python 集成测试和真实 API Playwright E2E 均通过 |
| Gate B — 真实传感器贯通 | 最终四传感器持续产生有效窗口并完成边缘推理 | **部分完成**；四传感器烧录、探测、10 分钟会话和整包校验已通过，仍需在最新主线复核真实窗口经过 Module 2 到 Dashboard 的完整链路 |
| Gate C — 推荐与降级 | 三个房间由正式规则确定排序，LLM/单传感器故障不阻断核心流程 | **未完成**；Dashboard 已有，但正式 Module 4 adapter、模板解释和 LLM provider 尚未实现 |
| Gate D — 最终演示 | 连续运行至少 15 分钟并展示状态、趋势、预测、偏好变化、推荐和本地指示 | **未完成**；依赖 Gate B、Gate C 和现场记录 |

Gate A 的实现与限制见 [`tests/integration/GATE_A_HANDOFF.md`](tests/integration/GATE_A_HANDOFF.md)。

## 隐私边界

- 不使用 RGB 摄像头、面部识别、身份追踪或个人画像。
- 不保存或上传原始语音；声音模块只输出 RMS、标准差、峰值等强度统计。
- 完整热帧只允许在本地离线会话中短期使用；后端 Observation、推荐上下文和日志不得包含完整热阵列。
- 浏览器热图仅为短时、归一化的 32 × 24 预览，后端不持久化。
- 登录账号不收集姓名、邮箱或学号；密码使用 Argon2id，数据库只保存会话令牌哈希。
- LLM 未来只能润色已经确定的结构化理由，不能更改排名，也不能接收原始传感器或身份数据。

## 快速验证 Gate A

需要 Python 3.11、Node.js 22，以及首次运行时安装 Playwright Chromium。

```bash
python -m pip install -e './edge/hardware' -e './edge/ml[dev,thermal]' -e './backend[dev]'
python -m pytest -q tests/integration/test_gate_a.py

cd frontend
npm ci
npx playwright install chromium
npm run gate-a:e2e
```

浏览器测试会启动临时 SQLite 后端和 Vite，不会写入项目数据库，也不需要真实传感器、边缘令牌或 LLM Key。

## 分模块运行

Module 1 模拟器：

```bash
python -m pip install -e './edge/hardware[dev]'
python edge/hardware/scripts/run_simulator.py \
  --config edge/hardware/config/example.yaml \
  --scenario quiet_study_recommended \
  --windows 2
```

Module 2 处理共享 fixture：

```bash
python -m pip install -e './edge/ml[dev,thermal]'
study-space-ml-predict-window shared/fixtures/sensor_window_quiet.json \
  --out edge_observation.json
```

Module 3 后端：

```bash
cd backend
python -m pip install -e '.[dev]'
alembic upgrade head
study-space-api seed-demo --reset
uvicorn study_space_api.main:app --reload --host 127.0.0.1 --port 8000
```

Module 4 Dashboard：

```bash
cd frontend
npm ci
npm run dev
```

前端默认使用 mock 模式。连接真实后端时，在 `frontend/.env` 中设置：

```text
VITE_API_MODE=real
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_REFRESH_SECONDS=10
VITE_LIVE_SENSOR_POLL_MS=1000
VITE_SOUND_POLL_MS=250
```

后端 OpenAPI 位于 `http://127.0.0.1:8000/docs`，前端默认位于 `http://127.0.0.1:5173`。具体环境变量、迁移、seed、硬件依赖和故障排查请阅读各模块 README。

## 仓库结构

```text
.
|-- edge/
|   |-- hardware/          # Module 1
|   `-- ml/                # Module 2 的规范实现
|-- ml/                    # 待迁移/移除的第二套 Module 2 实现
|-- backend/               # Module 3；Module 4 adapter 在此注入
|-- frontend/              # Module 4 Dashboard
|-- shared/
|   |-- contracts/         # JSON Schema 和公共枚举
|   `-- fixtures/          # 跨模块固定测试负载
|-- tests/integration/     # Gate A–D 集成测试入口
|-- docs/module-specs/     # 目标规格与共享契约
|-- AGENTS.md              # AI 仓库级规则
`-- CONTRIBUTING.md        # 分支、提交和 PR 规则
```

各模块只能通过 `shared/contracts/` 约定的负载交换数据。Module 1 不负责分类，Module 2 不负责后端历史，Module 3 不拥有正式推荐算法，Module 4 不得让 LLM 改变确定性排名。

## 当前优先事项

1. 完成 PR #9 在最新 `main` 上的标准回归、审查和 Raspberry Pi 接管部署。
2. 确定实时热帧在 Module 1 与 Module 2 之间的内存边界，保证无雷达情况下仍能提取占用特征且不上传完整热帧。
3. 合并两套 Module 2，实现真实数据训练、评估与专用 CI。
4. 实现 Module 4 正式确定性推荐 adapter、模板解释和可选 LLM provider，完成 Gate C。
5. 补齐登录用户的历史管理、学习控制、删除账号和选择失败重试 UI。
6. 完成 Gate B 主线端到端复核、Gate D 15 分钟演示和项目许可证决策。

## 文档入口

- [共享系统契约](docs/module-specs/00_SHARED_CONTRACT.md)
- [Module 1 规格](docs/module-specs/01_SENSOR_EDGE_HARDWARE.md) / [运行说明](edge/hardware/README.md)
- [Raspberry Pi 接管与完成操作手册](docs/RASPBERRY_PI_CODEX_HANDOFF.md)
- [Module 2 规格](docs/module-specs/02_EDGE_ML_PIPELINE.md) / [运行说明](edge/ml/README.md)
- [Module 3 规格](docs/module-specs/03_BACKEND_DATA_INTELLIGENCE.md) / [运行说明](backend/README.md) / [交接说明](backend/MODULE3_HANDOFF.md)
- [Module 4 规格](docs/module-specs/04_RECOMMENDATION_FRONTEND.md) / [运行说明](frontend/README.md) / [交接说明](frontend/MODULE4_HANDOFF.md)
- [Gate A 交接说明](tests/integration/GATE_A_HANDOFF.md)
- [项目使用与协作教程](docs/USAGE_GUIDE.md)
- [贡献与 Pull Request 规则](CONTRIBUTING.md)

根 README 记录当前主线事实，`docs/module-specs/` 描述目标验收标准。历史状态文档如与代码或本页冲突，应视为待归档材料而不是当前执行入口。

原始 Proposal 含团队成员信息，默认保留在团队本地资料中，不上传仓库。若需要纳入 GitHub，应先生成脱敏版本并由团队确认。
