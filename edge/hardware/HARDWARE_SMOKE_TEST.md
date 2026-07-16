# 模块 1 真实硬件冒烟测试

状态：**尚未执行**

本文件用于在 Raspberry Pi 5 与真实传感器到位后记录验收结果。当前提交只在无物理硬件环境完成自动化测试，因此不能填写或推测丢帧率、无效包率和资源占用。

## 测试信息

| 项目 | 记录 |
|---|---|
| 日期与时区 | 待填写 |
| 操作者 | 待填写；不要写学号或其他个人标识 |
| Raspberry Pi 型号 | Raspberry Pi 5 / 待确认 |
| Raspberry Pi OS 版本 | 待填写 |
| Python 版本 | 待填写 |
| Git commit | 待填写 |
| 配置文件 | `config/real.example.yaml` 的本地副本 |
| 传感器型号/固件 | 待填写 |

## 1. 连接探测

```bash
cd edge/hardware
source .venv/bin/activate
python scripts/probe_sensors.py \
  --config config/real.example.yaml \
  | tee hardware-probe.json
```

检查：

- [ ] MLX90640 返回 32 × 24 帧摘要，没有打印完整温度矩阵。
- [ ] LD2450 能从噪声或截断数据后恢复到有效帧。
- [ ] 声音输出只有 RMS 与峰值等统计值。
- [ ] 光照、温度和湿度单位正确。
- [ ] 缺失传感器被标记为 degraded/offline，不会导致进程崩溃。

## 2. 十分钟连续采集

在不记录姓名、学号或可识别备注的前提下执行：

```bash
python scripts/collect_session.py \
  --config config/real.example.yaml \
  --room room_a \
  --scenario quiet_study_recommended \
  --duration 600 \
  --participant-range 1-4 \
  --realtime
```

| 指标 | 结果 |
|---|---|
| 窗口数（5 秒窗口预期 120） | 待填写 |
| 进程未处理异常 | 待填写 |
| 热阵列有效帧/期望帧 | 待填写 |
| 热阵列丢帧率 | 待填写 |
| 雷达有效帧/期望帧 | 待填写 |
| 雷达无效包或流重同步次数 | 待填写 |
| 最低窗口完整度 | 待填写 |
| 平均 CPU 使用率 | 待填写 |
| 峰值常驻内存 | 待填写 |
| 会话校验和验证 | 待填写 |

建议同时使用 `top`、`htop` 或 `pidstat` 记录资源占用，但不要把系统用户名、网络地址或其他机器隐私写入提交文件。

## 3. 隐私检查

```bash
find data/sessions -type f
```

- [ ] 没有 `.wav`、`.pcm`、`.mp3`、`.flac` 等音频文件。
- [ ] 没有 RGB 图像或视频。
- [ ] `session.json` 中 `raw_audio_persisted` 为 `false`。
- [ ] `windows.jsonl` 不含姓名、学号或稳定人员标识。
- [ ] 热帧只存在本地 `thermal/*.npz`。
- [ ] 相邻窗口中的雷达目标 ID 不用于跨窗口追踪。

## 4. 释放与重启

- [ ] 正常结束采集后，可立即再次运行 `probe_sensors.py`。
- [ ] 中断进程后，串口、I2C 和 GPIO 未被持续占用。
- [ ] LED/micro:bit 输出失败不会中断采样。

## 结论

待真实硬件测试后填写：通过、部分通过或失败，并列出可复现的问题、对应日志和修复 commit。
