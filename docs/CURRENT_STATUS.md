# 当前状态

更新时间：2026-07-20 16:05 SGT

## 当前结论

项目位于 `module1/hardware-foundation` 分支，本次局部改造基线为 `b294565`。已完成的模块 01 驱动、树莓派部署和验证提交均保留；现有 Raspberry Pi 直连模式不会删除。

历史遗留的未跟踪内容仍只有 `references/`。其中包含多个 GitHub 仓库和 `clone-results.log`；不删除、不移动、不整批纳入 Git。本阶段新固件和测试均作为独立提交审阅，不与该目录混合。

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
| 模块 01 故障注入 | 已完成 | 本机与 Pi 的针对性 14 项、全量 49 项和 80% 覆盖率门禁均通过 |
| 模块 01 打包与 CLI | 已完成 | Mac 与 Pi 的全新 wheel 环境均从临时目录跑通四个入口与依赖检查 |
| 模块 01 CI | 已完成 | 单作业顺序执行覆盖率、编译和 wheel；GitHub 使用 checkout v7/setup-python v6 全绿 |
| 模块 01 Pi 长测 | 已完成 | 间歇故障场景 30 分钟、360 窗口，退出与立即重启成功，Schema 和隐私检查通过 |
| 模块 01 内存基线优化 | 已完成 | Pi 完整回归 55 项通过；2 分钟实时峰值 RSS 24,544 KiB，较优化前降低约 42.3% |
| ESP32 Sensor Hub 连接基线 | 已完成 | Pi 新地址 `192.0.2.76` 可达；ESP32 CH340 稳定路径可见；Mac 与 Pi 原始 55 项通过 |
| ESP32 Hub 协议与配置 | 已完成 | COBS、CRC32、全局序号、有界负载、版本和黄金向量已冻结；完整 81 项、覆盖率 85.71% 通过 |
| ESP32 Hub 兼容驱动 | 已完成 | 单串口解复用、五种适配器、重连、有界队列、序号诊断和离线旧样本清理已实现；111 项、86.19% 覆盖率 |
| ESP32 Hub 固件 | 已完成 | 固定 ESP32 core 3.3.10 与四个库版本；热阵列、雷达、光照、温湿度和可选 I2S 声音统计固件通过 Pi 隔离编译与跨语言黄金向量；114 项回归通过 |

## 当前风险

- `references/` 未跟踪且来源未完全确认，不能把整个目录直接提交。
- 根 README 仍描述四模块并行开发；当前执行方式由本阶段决策覆盖，为单主 Agent 串行推进。
- 实物传感器可用性与本阶段源码/骨架工作无关；树莓派 SSH 连通性仍是继续执行的硬门槛。
- 项目根目录没有许可证文件；在团队明确发布许可证前，不复制 GPL/AGPL 实现，MIT 代码也必须保留其通知。
- ESP32 Sensor Hub 尚未烧录；当前 ESP32 仍运行旧心跳固件。固件阶段只能证明可编译与协议一致，不能声称 Hub 已完成真机采集。
- 普通 USB 麦克风不能直接接入经典 ESP32-D0WD-V3；全 Hub 方案需要 I2S 麦克风，或保留 Pi 直连声音驱动。

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
- Raspberry Pi 运行 LD2450/MLX90640 针对性测试：14 项通过；完整回归：49 项通过。
- Raspberry Pi 覆盖率：80.54%，满足 80% 门禁；LD2450 驱动 93%；编译检查通过。
- 本机 CLI 针对性测试：5 项通过；完整回归：54 项；总覆盖率 84.60%，CLI 覆盖率 96%。
- 本机 wheel 在全新虚拟环境安装，从临时目录运行模拟、探测、采集、会话验收和 `pip check`：通过。
- Raspberry Pi 从源码构建 wheel，在全新临时虚拟环境安装并从临时目录运行四个入口与 `pip check`：通过。
- Raspberry Pi 实时间歇故障模拟：360 个 5 秒窗口，耗时 30:01.16，退出码 0，立即重启退出码 0。
- 长测资源：用户 CPU 9.46 秒，系统 CPU 0.06 秒，峰值 RSS 42,560 KiB；20 至 25 分钟 RSS 采样稳定在 43,824 KiB。
- 360 个窗口全部通过共享 Schema、`window_id` 全部唯一；有限重试后完整度均为 1.0。
- 采集目录禁用音频/RGB/视频文件为 0；全树扫描的 2 个 PNG 是 `.venv` 内 coverage 工具图标，不是采集数据。
- 延迟导入修复本机针对性测试 11 项、完整回归 55 项、覆盖率 84.59%、编译检查通过。
- 延迟导入修复在 Raspberry Pi 的针对性测试 11 项、完整回归 55 项、覆盖率 84.59% 通过。
- Pi 优化后实时对照：24 个窗口、2:00.17、退出码 0、峰值 RSS 24,544 KiB；比优化前 42,560 KiB 减少 18,016 KiB（约 42.3%）。
- GitHub Module 1 CI：安装、55 项测试与 80% 覆盖率门禁、编译、wheel 构建全部通过；Action 运行时升级后无 Node 20 注释。
- 2026-07-20 使用新地址 `192.0.2.76` 重连 Raspberry Pi：主机、aarch64 架构、部署目录和 ESP32 CH340 串口均确认存在。
- ESP32 Hub 改造前基线：Mac 与 Raspberry Pi 均为 55 项通过，编译检查通过。
- Hub 协议与配置针对性测试：33 项通过；完整回归：81 项通过；总覆盖率 85.71%；编译检查通过。
- Pi Hub 协议、配置和兼容驱动针对性测试：63 项通过；完整回归：111 项通过；总覆盖率 86.19%；编译检查通过。
- Sensor Hub 固件协议针对性测试：21 项通过；C++ 与 Python 黄金向量逐字节一致，隐私静态门禁通过。
- Pi 使用 Arduino CLI 隔离 profile 编译 Sensor Hub 固件：ESP32 core 3.3.10 和固定库版本解析成功；Flash 333,612 字节（25%），全局内存 38,388 字节（11%）。
- Pi 原生 `c++ -std=c++17 -Wall -Wextra -Werror` 编译并运行固件协议黄金向量：通过。
- 本机完整回归：114 项通过，总覆盖率 86.19%，满足 80% 门禁；Python 编译检查和 `git diff --check` 通过。

## 下一步

进入 Hub 边界与压力回归，补齐队列压力、语义损坏、重连与隐私门禁；通过并独立提交后才部署烧录。自动任务保持取消。
