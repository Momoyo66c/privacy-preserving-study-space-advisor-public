# 项目使用与四人协作教程

## 1. 这份教程适合谁

本教程用于四位组员和协助开发的 AI。仓库采用 monorepo：大家共享同一个 GitHub 仓库，但每个人负责一个模块、使用独立分支、通过固定接口协同。

当前仓库首先提供架构、模块目标和协作骨架。功能代码会按四份模块规格逐步实现，因此某些运行命令只有在对应模块完成后才会生效。

## 2. 准备软件

每位成员安装：

- Git。
- VS Code 或其他编辑器。
- Python 3.11，供模块 1、2、3 和推荐服务使用。
- Node.js LTS，供模块 4 前端使用。
- GitHub 账号，并接受仓库协作者邀请。

负责 Raspberry Pi 的成员还需要 Raspberry Pi OS、I2C/串口/GPIO 权限以及实际传感器依赖。

验证：

```bash
git --version
python --version
node --version
npm --version
```

## 3. 第一次获取仓库

```bash
git clone https://github.com/<owner>/privacy-preserving-study-space-advisor.git
cd privacy-preserving-study-space-advisor
git status
```

如果使用 SSH：

```bash
git clone git@github.com:<owner>/privacy-preserving-study-space-advisor.git
```

不要把仓库克隆到 OneDrive 自动同步目录，避免虚拟环境和 Git 文件锁冲突。

## 4. 分配四位成员

在 GitHub 仓库首页的 Settings → Collaborators 中邀请其他三位组员。建议分工表：

| 人员 | 分支前缀 | 负责目录 |
|---|---|---|
| 成员 A | `module1/` | `edge/hardware/` |
| 成员 B | `module2/` | `edge/ml/` |
| 成员 C | `module3/` | `backend/` |
| 成员 D | `module4/` | `frontend/` 和推荐 adapter |

把真实姓名和 GitHub 用户名记录在团队自己的 Issue 或 Project 中，不需要写入传感器数据和应用数据库。

## 5. 每个成员开始开发

以模块 2 为例：

```bash
git switch main
git pull --ff-only
git switch -c module2/initial-pipeline
```

先阅读：

```text
docs/module-specs/00_SHARED_CONTRACT.md
docs/module-specs/02_EDGE_ML_PIPELINE.md
edge/ml/README.md
CONTRIBUTING.md
```

模块开发不得等待所有真实硬件完成。模块 1 提供模拟窗口，模块 2 提供固定模型/观察 fixture，模块 3 提供 seed 数据，模块 4 提供 mock API。每个模块都应能独立测试。

## 6. 如何直接把任务交给 AI

给 AI 的上下文至少包含：

1. 仓库根目录。
2. `AGENTS.md`。
3. `00_SHARED_CONTRACT.md`。
4. 负责模块的目标文档。

可直接使用以下提示词：

```text
你正在实现 Privacy-Preserving Study Space Advisor 的模块 2。
请先完整阅读仓库根目录 AGENTS.md、
docs/module-specs/00_SHARED_CONTRACT.md 和
docs/module-specs/02_EDGE_ML_PIPELINE.md。

检查现有仓库后给出简短实施计划，然后直接实现当前规格中尚未完成的最高优先级内容。
严格保持共享字段、枚举和隐私规则；不要修改其他模块的内部代码。
实现测试、运行测试并更新 README/MODULE2_HANDOFF.md。
最后列出改动文件、测试结果、已知限制和其他模块需要配合的事项。
```

替换模块编号和目标文档即可交给另外三位成员的 AI。不要只发送一句“完成模块 2”，否则 AI 可能缺少接口和验收背景。

## 7. 建议开发顺序

### 第一阶段：接口和模拟数据

- 模块 1：建立驱动接口和四场景模拟器。
- 模块 2：建立窗口加载、特征 Schema 和固定假模型。
- 模块 3：建立 FastAPI、数据库迁移和 seed。
- 模块 4：建立 mock API、静态推荐列表和偏好界面。

完成条件：不需要真实硬件，也能让一份模拟数据从窗口走到 Dashboard。

### 第二阶段：真实能力

- 模块 1 接入 MLX90640、声音、光照和温湿度传感器；雷达只保留可选兼容接口。
- 模块 2 采集标注数据、训练 Random Forest 并导出模型包。
- 模块 3 加入历史聚合和 15/30 分钟预测。
- 模块 4 加入确定性评分、LLM adapter 和模板 fallback。

### 第三阶段：集成和演示

- 用共享 JSON Schema 验证负载。
- 真实 Pi 向后端持续发送 Observation。
- Dashboard 展示 fresh/stale、置信度和 degraded。
- 关闭 LLM、断开一个传感器，验证系统仍可演示。

## 8. 日常 Git 工作流

开始一天工作：

```bash
git switch main
git pull --ff-only
git switch module1/sensor-drivers
git rebase main
```

完成一个小目标：

```bash
git status
git add edge/hardware tests
git commit -m "feat(module1): add sensor health reporting"
git push -u origin module1/sensor-drivers
```

然后在 GitHub 创建 Pull Request，填写模板并请求另一位成员评审。

## 9. Pull Request 评审重点

所有 PR 检查：

- 是否只修改当前目标相关文件。
- 是否有测试以及真实测试结果。
- 是否泄露密钥、个人数据或原始语音。
- 是否改变共享字段、枚举、端点或语义。
- 是否更新 README 和 handoff。

跨模块 PR 额外检查：

- `shared/contracts/` JSON Schema 是否更新。
- `shared/fixtures/` 示例是否更新。
- 生产方和消费方测试是否同时更新。
- 是否保持旧版本兼容，或正确提升 `schema_version`。

## 10. 环境变量和密钥

每个模块提交 `.env.example`，成员在本地复制：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

真实 `.env` 已被 `.gitignore` 忽略。LLM API Key 只能放在后端环境，不得放入 `frontend/` 或以 `VITE_` 等公开前缀暴露。

如果密钥被误提交：立即撤销并重新生成，随后清理 Git 历史。仅从文件中删除并不能使旧提交中的密钥失效。

## 11. 数据与大型文件

以下内容默认不进入 Git：

- 原始/大型传感器采集数据。
- Python 虚拟环境和 Node `node_modules`。
- 模型缓存和临时导出。
- 原始音频、RGB 图像和个人信息。

小型、匿名、可复现的 fixture 可以放入 `shared/fixtures/`。正式模型如超过 GitHub 常规文件限制，应使用 Release、对象存储或团队商定的 Git LFS；在决定前只提交模型生成脚本和哈希。

## 12. 各模块运行入口约定

实现完成后，每个目录 README 必须提供一致入口：

```text
安装依赖
配置环境
运行模拟/开发模式
运行真实模式
运行测试
常见故障
```

预期命令形式：

```bash
# 模块 1/2/3
python -m pytest

# 模块 3
uvicorn study_space_api.main:app --reload

# 模块 4
npm install
npm run dev
npm test
```

最终准确命令以各模块 README 为准。

## 13. 本地集成建议

模块 3 和 4 可先在普通电脑运行；模块 1 和 2 在 Raspberry Pi 或模拟模式运行。

推荐端口：

```text
Backend API: http://localhost:8000
Frontend:    http://localhost:5173
OpenAPI:     http://localhost:8000/docs
```

不要在代码中写死 IP。Pi 使用环境变量指定后端，例如：

```text
BACKEND_BASE_URL=http://<developer-machine-ip>:8000
```

仅在可信局域网演示；课程原型不等于生产级安全部署。

## 14. 四个集成门禁

### Gate A：模拟数据贯通

- 四场景模拟窗口可产生。
- 模块 2 输出合法 EdgeObservation。
- 模块 3 成功写入并查询。
- 模块 4 显示状态和推荐。

### Gate B：真实传感器贯通

- MLX90640、声音、光照和温湿度传感器工作；未配置雷达必须保持 `not_configured`，不能伪造零目标数据。
- 采集连续运行 10 分钟。
- Pi 端分类和本地指示工作。

### Gate C：推荐与降级

- 至少三个房间可排序。
- 偏好变化导致合理排名变化。
- LLM 关闭时模板解释仍工作。
- 单传感器故障显示 degraded，不使系统崩溃。

### Gate D：最终演示

- 连续运行 15 分钟。
- 展示当前状态、历史、预测、置信度和隐私说明。
- 展示 quiet/discussion 偏好切换。
- 展示 LED/micro:bit 与 Dashboard 状态一致。

## 15. 常见问题

### 为什么只有一个仓库？

四个模块共享接口和课程演示，monorepo 更容易同步 Schema、fixture、文档和端到端测试。

### 可以直接改其他成员目录吗？

小修复可在同一个 PR 中说明；较大修改应先开 Issue 并让对应模块负责人处理。跨模块接口不得私自修改。

### 没有真实硬件能否开发？

可以。每个模块都必须支持模拟或 mock。真实硬件只用于 Gate B 及之后的验证。

### LLM 不可用怎么办？

推荐排序由确定规则产生，LLM 只负责解释。系统自动使用模板解释，因此核心演示不应中断。

### 如何知道任务完成？

以模块规格末尾的“验收标准”和“最终交付物”为准，不以“代码能运行一次”为准。
