# 当前状态

更新时间：2026-07-18 02:49 SGT

## 当前结论

项目位于 `module1/hardware-foundation` 分支，当前 HEAD 为 `3add5de`。已完成的模块 01 固件、ESP32 烧录、树莓派部署和 GPIO 验证提交均保留，不在本阶段重做。

工作树中唯一已发现的未跟踪内容是 `references/`。其中包含多个 GitHub 仓库和 `clone-results.log`；来源与许可证尚在审计，因此暂不删除、不移动、不整批纳入 Git。

## 执行状态

| 项目 | 状态 | 证据或说明 |
|---|---|---|
| Git 与遗留修改审计 | 已完成 | `git status` 仅报告 `?? references/` |
| 树莓派连接门禁 | 通过 | 2026-07-18 01:43 SGT，SSH 返回 `host=raspberrypi user=pi` |
| 自动任务 | 已取消 | 任务 `1` 已于 2026-07-18 02:31 SGT 删除；当前没有项目自动任务 |
| 协作文档基线 | 已完成 | 三份文档已建立；`git diff --check` 与文件结构检查通过 |
| GitHub 源码与用途分析 | 已完成 | 9 个完整克隆均已 fetch；工作树干净，本地 HEAD 与当前远端分支一致；详见 `REFERENCE_REPOSITORIES.md` |
| 许可证检查 | 已完成 | MIT 6 个、GPLv3 2 个、AGPLv3 1 个；主仓库缺少根许可证，采用保守复用边界 |
| 三层项目骨架 | 已完成 | `edge/`、`backend/` + `shared/`、`frontend/` 及跨层测试入口均存在；根 README 已明确边界 |
| 当前限定阶段终验 | 已完成 | 源码、用途、许可证和三层骨架均有独立记录；模块 01 测试 34 项通过 |
| 模块 01 会话异常元数据 | 已完成 | 新增可重复 `--known-anomaly` 和 `session.json.known_anomalies`；本机与 Raspberry Pi 全套测试均为 35 项 |
| 模块 01 雷达端口安全配置 | 已完成 | `real.example.yaml` 必须从 `RADAR_PORT` 读取独立雷达串口；本机与 Raspberry Pi 全套测试均为 36 项 |
| 模块 01 测试路径兼容 | 已完成 | 配置夹具改为基于测试文件定位；本机与 Raspberry Pi 的模块目录/仓库根目录运行均为 36 项通过 |
| 模块 01 离线会话验收 | 已完成 | 本机与 Pi 的 5 项针对性测试、41 项完整回归通过；Pi 正常/篡改会话 CLI 行为通过 |
| 模块 01 故障注入 | 本地完成 | 新增 8 项 LD2450/MLX90640 压力和恢复用例；49 项全量测试、81% 总覆盖率通过 |

## 当前风险

- `references/` 未跟踪且来源未完全确认，不能把整个目录直接提交。
- 根 README 仍描述四模块并行开发；当前执行方式由本阶段决策覆盖，为单主 Agent 串行推进。
- 实物传感器可用性与本阶段源码/骨架工作无关；树莓派 SSH 连通性仍是继续执行的硬门槛。
- 项目根目录没有许可证文件；在团队明确发布许可证前，不复制 GPL/AGPL 实现，MIT 代码也必须保留其通知。

## 最近验证

- 对 9 个参考仓库检查完整克隆、干净工作树、本地/远端提交一致和许可证文件存在性：通过。
- 检查清单是否包含每个仓库名称与完整提交哈希：通过。
- `git diff --check -- docs`：通过。
- 检查三层目录和 7 个入口 README 是否存在且非空：通过。
- 检查根 README 的三层映射、范围边界和 Markdown 差异：通过。
- 2026-07-18 02:00 SGT 再次检查树莓派 SSH：通过。
- 在 `edge/hardware/` 运行 `.venv/bin/python -m pytest -q`：34 项通过。
- 从仓库根目录直接执行同一测试会因相对 `config/` 路径失败；这是调用目录不正确，按模块 README 进入 `edge/hardware/` 后结果通过。
- 在 `edge/hardware/` 运行 `.venv/bin/python -m pytest tests/test_storage.py`：3 项通过。
- 在 `edge/hardware/` 运行 `.venv/bin/python -m pytest`：35 项通过。
- 在 `edge/hardware/` 运行 `.venv/bin/python -m compileall -q src scripts`：通过。
- Raspberry Pi 增量部署前逐文件比较 SHA-256：4 个目标文件均与本次修改前版本一致，无现场漂移。
- Raspberry Pi 运行 `.venv/bin/python -m pytest tests/test_storage.py`：3 项通过。
- Raspberry Pi 运行 `.venv/bin/python -m pytest`：35 项通过。
- Raspberry Pi 运行 `.venv/bin/python -m compileall -q src scripts`：通过。
- 本机运行 `.venv/bin/python -m pytest tests/test_config.py`：7 项通过。
- 本机运行 `.venv/bin/python -m pytest`：36 项通过。
- 本机运行编译检查和一窗口模拟共享契约检查：通过。
- Raspberry Pi 未设置 `RADAR_PORT` 加载真实配置：按预期失败，并明确报告缺少环境变量。
- Raspberry Pi 设置 `RADAR_PORT=/dev/ld2450-not-connected` 执行真实探测：雷达报告未连接，进程正常退出，未访问 ESP32 串口。
- Raspberry Pi 运行配置测试：7 项通过；完整回归：36 项通过；编译检查：通过。
- 本机从 `edge/hardware/` 运行完整回归：36 项通过。
- 本机从仓库根目录运行 `edge/hardware/.venv/bin/python -m pytest -q edge/hardware/tests`：36 项通过。
- Raspberry Pi 从 `edge/hardware/` 运行完整回归：36 项通过，耗时 0.80 秒。
- Raspberry Pi 从部署根目录运行完整回归：36 项通过；根目录编译检查：通过。
- 本机运行会话验收针对性测试：5 项通过；完整回归：41 项通过。
- 本机运行编译检查、`pip check` 和安装后命令入口帮助：通过。
- Raspberry Pi 运行会话验收针对性测试：5 项通过；完整回归：41 项通过。
- Raspberry Pi 运行编译检查、`pip check` 和安装入口帮助：通过。
- Raspberry Pi 现场生成模拟会话：验收返回有效；加入禁用 `.wav` 后按预期返回失败并报告隐私违规。
- 本机运行 LD2450/MLX90640 针对性测试：14 项通过；完整回归：49 项通过。
- 本机覆盖率：总计 81%，LD2450 驱动 93%；编译检查通过。

## 下一步

提交并推送故障注入阶段，然后在 Raspberry Pi 上运行相同的针对性、全量和覆盖率验证。自动任务保持取消。
