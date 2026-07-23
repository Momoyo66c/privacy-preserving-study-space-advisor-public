# 真实双人讨论数据位置、格式与使用方法

## 1. 数据位置

本仓库包含两份短时、去身份化的真实传感器会话：

```text
edge/hardware/sample_data/real_two_person_v1/
├── dataset_manifest.json
├── labels.csv
├── session-20260723T092556401Z-f75d59c9/
└── session-20260723T093809359Z-c7ab61aa/
```

| 会话 | 场景标签 | 窗口 | 说明 |
|---|---|---:|---|
| `session-20260723T092556401Z-f75d59c9` | `discussion_allowed` | 9 | 两人自然、正常音量讨论 |
| `session-20260723T093809359Z-c7ab61aa` | `not_recommended_noisy_or_crowded` | 9 | 两人持续嘈杂活动 |

两次会话都使用五秒非重叠窗口。它们是真实数据，不是模拟器输出。
`dataset_manifest.json` 记录传感器来源、窗口数量、主要统计、采集归档哈希、
隐私声明和已知限制。

## 2. 单个会话格式

每个会话目录包含：

```text
<session_id>/
├── session.json
├── windows.jsonl
├── relative_features.jsonl
├── thermal/
│   └── <window_id>.npz
└── checksums.json
```

- `session.json`：会话 ID、房间、设备、场景、人数区间、采样配置和隐私声明。
- `windows.jsonl`：每行一个符合 `shared/contracts/sensor_window.schema.json`
  的 `SensorWindow`。
- `relative_features.jsonl`：与窗口一一对应的 HW-486 相对光照和 Windows
  麦克风相对声音统计。
- `thermal/*.npz`：本地训练用 MLX90640 热帧，键名为 `frames`，类型为
  `float32`，形状为 `(N, 768)`；每行可恢复为 24×32，但不得用于身份识别。
- `checksums.json`：会话内每个文件的 SHA-256。
- 根目录 `labels.csv`：18 个窗口的独立人工标签，列为
  `session_id,window_id,label,annotator,notes`。

声音只包含 RMS、标准差和峰值等 0–1 相对摘要，没有 WAV、PCM 或可恢复语音。
声音不是 dBA；光照不是 lux。雷达在所有窗口中均为预期的
`health=not_configured`。

## 3. 数据限制

这是一份真实数据锚点和端到端样例，不是完整训练集：

- 只有两个会话、18 个窗口和四个目标标签中的两个。
- 两次会话来自同一房间、同一套设备和同一天。
- 正常讨论 RMS 平均为 `0.2848`，嘈杂活动 RMS 平均为 `0.4075`。
- 配置期望 MLX90640 为 2 Hz，但本次实测每个五秒窗口为 4–5 帧，因此会话
  平均完整度约为 0.70；整包、热帧和声音健康校验仍全部通过。
- 不得用这18个窗口单独宣称模型准确率，也不得把模拟数据指标当作真实指标。

## 4. 验证完整会话

在仓库根目录创建模块 1 环境后，对两份会话分别运行：

```bash
cd edge/hardware
python -m venv .venv
python -m pip install -e ".[dev]"

python scripts/verify_session.py \
  sample_data/real_two_person_v1/session-20260723T092556401Z-f75d59c9

python scripts/verify_session.py \
  sample_data/real_two_person_v1/session-20260723T093809359Z-c7ab61aa
```

两个命令都应输出 `"valid": true`。验证器会检查 Schema、UTC 时间顺序、
SHA-256、热帧形状和有限值、未登记文件、符号链接以及禁止的音频/图片/视频
扩展名。

也可以使用模块 1 的严格读取器：

```python
from study_space_hardware.session_reader import SessionReader

session = SessionReader(
    "sample_data/real_two_person_v1/"
    "session-20260723T092556401Z-f75d59c9"
)
for item in session:
    sensor_window = item.payload
    thermal_frames = item.thermal_frames  # float32 (N, 768)
    relative_features = item.relative_features
```

## 5. 用模块 2 检查和提取特征

当前模块 2 可以直接消费完整会话目录。先安装：

```bash
cd edge/ml
python -m venv .venv
python -m pip install -e ".[dev]"
```

从 `edge/ml` 目录运行：

```bash
DATA=../hardware/sample_data/real_two_person_v1

study-space-ml-interface \
  "$DATA/session-20260723T092556401Z-f75d59c9"

study-space-ml-run-pipeline \
  "$DATA/session-20260723T092556401Z-f75d59c9" \
  --features-out /tmp/discussion-features.jsonl \
  --observations-out /tmp/discussion-observations.jsonl

study-space-ml-run-pipeline \
  "$DATA/session-20260723T093809359Z-c7ab61aa" \
  --features-out /tmp/noisy-features.jsonl \
  --observations-out /tmp/noisy-observations.jsonl
```

在 Windows PowerShell 中可以把 `/tmp/...` 换成 `$env:TEMP\...`。传入完整
会话目录而不是单独的 `windows.jsonl`，模块 2 才能解析 `local://` 引用并读取
NPZ 热帧。

## 6. 当前可执行的规则基线重标定

模块 2 当前实现的是确定性规则基线，不是 Random Forest。规则重标定入口每次
只接收一个 `windows.jsonl` 或一个会话目录。要利用两个场景的声音中位数，
先在临时目录合并窗口；这一步不会复制热帧，只适用于当前基于声音阈值的规则
重标定：

```bash
cd edge/ml
DATA=../hardware/sample_data/real_two_person_v1

cat \
  "$DATA/session-20260723T092556401Z-f75d59c9/windows.jsonl" \
  "$DATA/session-20260723T093809359Z-c7ab61aa/windows.jsonl" \
  > /tmp/real-two-person-windows.jsonl

study-space-ml-train-rule \
  --windows /tmp/real-two-person-windows.jsonl \
  --labels "$DATA/labels.csv" \
  --out artifacts/rule_model_real_two_person
```

PowerShell 等价命令：

```powershell
$data = "..\hardware\sample_data\real_two_person_v1"
Get-Content `
  "$data\session-20260723T092556401Z-f75d59c9\windows.jsonl", `
  "$data\session-20260723T093809359Z-c7ab61aa\windows.jsonl" |
  Set-Content "$env:TEMP\real-two-person-windows.jsonl"

study-space-ml-train-rule `
  --windows "$env:TEMP\real-two-person-windows.jsonl" `
  --labels "$data\labels.csv" `
  --out artifacts\rule_model_real_two_person
```

随后可使用新规则产物推理：

```bash
study-space-ml-predict-jsonl \
  "$DATA/session-20260723T093809359Z-c7ab61aa" \
  --artifact artifacts/rule_model_real_two_person \
  --out /tmp/noisy-observations-custom.jsonl
```

由于合并文件不在任何单个会话目录中，重标定阶段不会解析 NPZ 热帧；当前规则
训练代码只使用声音中位数和雷达目标中位数，这不会影响声音阈值计算。特征检查
和正式推理仍应逐会话传入完整目录。

## 7. 后续混合训练要求

虚拟数据必须标记 `synthetic=true`、生成器版本和随机种子，并与这两份真实
会话保持不同来源。训练、验证和测试必须以 `session_id` 分组，不能随机拆分
同一会话的相邻窗口。

模块 2 后续实现 Random Forest 时应：

1. 增加多会话目录加载器，同时保留每个会话的 NPZ 解析上下文。
2. 把真实与虚拟来源写入训练清单，真实样本给予更高权重。
3. 至少补齐 `empty_or_low_activity` 和 `quiet_study_recommended` 的真实锚点。
4. 最终测试只使用未参与调参的真实会话。
5. 报告真实测试 Macro F1、逐类召回率和混淆矩阵；模拟指标不能作为真实效果。

在这些工作完成前，本数据集只用于接口验证、特征检查、声音阈值锚定和演示。
