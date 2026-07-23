# 真实教室四场景数据位置、格式与使用方法

## 1. 数据位置

仓库内的去身份化真实数据位于：

```text
edge/hardware/sample_data/real_classroom_v1/
├── dataset_manifest.json
├── labels.csv
├── session-20260723T100559022Z-34fda6f1/
├── session-20260723T103741176Z-ffae7d8c/
├── session-20260723T092556401Z-f75d59c9/
└── session-20260723T093809359Z-c7ab61aa/
```

这是 2026-07-23 在同一教室、同一套设备和固定安装位置采集的四份真实会话。
每份会话包含 9 个五秒非重叠窗口，共 36 个窗口，覆盖共享契约定义的全部四个
训练标签。

| 会话 | 场景标签 | 人数 | 窗口 | 场景说明 |
|---|---|---:|---:|---|
| `session-20260723T100559022Z-34fda6f1` | `empty_or_low_activity` | 0 | 9 | 无人在教室内 |
| `session-20260723T103741176Z-ffae7d8c` | `quiet_study_recommended` | 1 | 9 | 一人自然安静学习 |
| `session-20260723T092556401Z-f75d59c9` | `discussion_allowed` | 2 | 9 | 两人正常音量自然讨论 |
| `session-20260723T093809359Z-c7ab61aa` | `not_recommended_noisy_or_crowded` | 2 | 9 | 两人持续嘈杂活动 |

`dataset_manifest.json` 是机器可读的数据清单，记录会话、传感器来源、主要统计、
采集归档 SHA-256、隐私声明和限制。训练可行性分析见
[`MODEL_TRAINING_READINESS_REPORT.md`](MODEL_TRAINING_READINESS_REPORT.md)。

## 2. 数据概览

下表中的声音是 Windows 麦克风的设备内相对值，不是 dBA；热区是对每个窗口
平均热帧应用相对阈值和连通域统计后的中位数，不能解释为精确人数。

| 标签 | 声音 RMS 均值 | 声音峰值均值 | 热区中位数 | 温度均值 °C | 湿度均值 % | 完整度均值 |
|---|---:|---:|---:|---:|---:|---:|
| 空教室 | 0.00063 | 0.00653 | 2 | 25.90 | 58.24 | 0.6869 |
| 一人安静学习 | 0.00085 | 0.01804 | 1 | 25.74 | 56.66 | 0.7020 |
| 两人正常讨论 | 0.28478 | 0.71048 | 4 | 25.80 | 58.20 | 0.7020 |
| 两人嘈杂活动 | 0.40753 | 0.83044 | 5 | 25.90 | 58.50 | 0.6970 |

正常讨论与嘈杂活动的声音 RMS 均值相差约 43.1%，具有明显的原型区分信号。
空教室与安静学习的声音非常接近，需要结合热帧空间特征，并避免使用简单的
“热区数等于人数”规则。

## 3. 单个会话格式

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

- `session.json`：会话 ID、房间、设备、场景、人数范围、采样配置和隐私声明。
- `windows.jsonl`：每行一个符合
  `shared/contracts/sensor_window.schema.json` 的 `SensorWindow`。
- `relative_features.jsonl`：与窗口一一对应的 HW-486 相对光照和 Windows
  麦克风相对声音统计。
- `thermal/*.npz`：本地训练用 MLX90640 热帧，键名为 `frames`，类型为
  `float32`，形状为 `(N, 768)`；每行可恢复为 24×32，但不得用于身份识别。
- `checksums.json`：会话内每个登记文件的 SHA-256。
- 数据集根目录的 `labels.csv`：36 个窗口的人工场景标签，列为
  `session_id,window_id,label,annotator,notes`。

声音只包含 RMS、标准差和峰值摘要，没有 WAV、PCM 或可恢复语音。光照只提供
设备专属的 0–1 相对值，不是 lux。雷达未安装，所有窗口均明确输出
`health=not_configured`。

## 4. 数据限制

该数据集可以用于接口验证、特征检查、规则阈值锚定和原型验收，但不是独立的
准确率基准：

- 四个标签各只有一次独立会话；真正独立样本数是 4，不是 36。
- 同一会话的相邻窗口高度相关，禁止随机拆到训练集和测试集两边。
- 所有会话来自同一房间、同一天、同一设备和固定安装位置。
- 光照、温湿度变化很小，当前数据无法验证这些特征的泛化价值。
- 空教室仍可能包含静态热源或人体离开后的余热。
- 配置期望 MLX90640 为 2 Hz，实测每个五秒窗口为 4–5 帧，因此平均完整度
  约为 0.70；整包、热帧、环境和声音健康校验均通过。
- 不得用这 36 个窗口随机切分后宣称模型准确率，也不得把模拟数据指标当作
  真实效果。

## 5. 验证完整会话

先在模块 1 环境安装开发依赖：

```bash
cd edge/hardware
python -m venv .venv
python -m pip install -e ".[dev]"
```

Linux/macOS：

```bash
DATA=sample_data/real_classroom_v1
for SESSION in "$DATA"/session-*; do
  python scripts/verify_session.py "$SESSION"
done
```

Windows PowerShell：

```powershell
$data = "sample_data\real_classroom_v1"
Get-ChildItem $data -Directory -Filter "session-*" | ForEach-Object {
  python scripts\verify_session.py $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "session validation failed" }
}
```

四个命令都应输出 `"valid": true`。验证器会检查 Schema、UTC 时间顺序、
SHA-256、热帧形状和有限值、未登记文件、符号链接以及禁止的音频、RGB 图片
和视频扩展名。

也可以使用模块 1 的严格读取器：

```python
from study_space_hardware.session_reader import SessionReader

session = SessionReader(
    "sample_data/real_classroom_v1/"
    "session-20260723T103741176Z-ffae7d8c"
)
for item in session:
    sensor_window = item.payload
    thermal_frames = item.thermal_frames  # 只读 float32 (N, 768)
    relative_features = item.relative_features
```

## 6. 用模块 2 提取特征和生成观察

模块 2 可以直接消费完整会话目录：

```bash
cd edge/ml
python -m venv .venv
python -m pip install -e ".[dev]"

DATA=../hardware/sample_data/real_classroom_v1
study-space-ml-interface \
  "$DATA/session-20260723T103741176Z-ffae7d8c"

study-space-ml-run-pipeline \
  "$DATA/session-20260723T103741176Z-ffae7d8c" \
  --features-out /tmp/quiet-features.jsonl \
  --observations-out /tmp/quiet-observations.jsonl
```

在 Windows PowerShell 中把 `/tmp/...` 换成 `$env:TEMP\...`。必须传入完整会话
目录，而不是单独传入 `windows.jsonl`，模块 2 才能在正确上下文解析
`local://` 引用并读取 NPZ 热帧。

## 7. 当前规则基线重标定

模块 2 当前实现的是确定性规则基线，不是 Random Forest。规则训练入口每次
接收一个窗口文件，因此先在临时目录合并四份 `windows.jsonl`：

```bash
cd edge/ml
DATA=../hardware/sample_data/real_classroom_v1
cat "$DATA"/session-*/windows.jsonl > /tmp/real-classroom-windows.jsonl

study-space-ml-train-rule \
  --windows /tmp/real-classroom-windows.jsonl \
  --labels "$DATA/labels.csv" \
  --out artifacts/rule_model_real_classroom
```

Windows PowerShell：

```powershell
$data = "..\hardware\sample_data\real_classroom_v1"
$lines = Get-ChildItem $data -Directory -Filter "session-*" |
  ForEach-Object { Get-Content "$($_.FullName)\windows.jsonl" }
$windows = "$env:TEMP\real-classroom-windows.jsonl"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($windows, [string[]]$lines, $utf8NoBom)

study-space-ml-train-rule `
  --windows $windows `
  --labels "$data\labels.csv" `
  --out artifacts\rule_model_real_classroom
```

随后可在完整会话上使用新规则产物：

```bash
study-space-ml-predict-jsonl \
  "$DATA/session-20260723T093809359Z-c7ab61aa" \
  --artifact artifacts/rule_model_real_classroom \
  --out /tmp/noisy-observations-custom.jsonl
```

合并文件不在任一会话目录内，因此重标定阶段不会解析 NPZ；当前规则训练代码
只利用声音和兼容雷达摘要。特征检查和正式推理仍应逐会话传入完整目录。

## 8. 后续虚拟数据与正式训练

当前仓库中的该目录全部是真实数据，尚未混入虚拟会话。建议后续为每个标签
生成 30–50 个带固定随机种子的独立虚拟会话，并强制记录
`synthetic=true`、生成器版本和随机种子，放入与本目录分离的位置。

训练、验证和测试必须按 `session_id` 分组。虚拟数据可以用于打通训练流程和
覆盖传感器缺失，但最终效果报告必须使用未参与调参的真实会话。模块 2 后续
实现统计模型时，应报告真实集 Macro F1、逐类召回率和混淆矩阵；在获得更多
独立真实会话前，只能把结果称为原型结果。
