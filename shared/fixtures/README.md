# Shared Fixtures

存放小型、匿名、可复现的跨模块测试负载。禁止提交原始语音、RGB 图像、个人信息和大型采集数据。

模块 1 提供以下 SensorWindow 夹具：

- `sensor_window_empty.json`
- `sensor_window_quiet.json`
- `sensor_window_discussion.json`
- `sensor_window_crowded.json`
- `sensor_window_degraded.json`
- `sensor_window_real_four_sensor.json`: 2026-07-22 四传感器 10 分钟验收会话中的匿名真实窗口摘要。本地热阵列引用已移除，不包含个人标识、原始音频或雷达轨迹。

这些文件都通过 `shared/contracts/sensor_window.schema.json` 验证。它们用于跨模块契约测试；除明确标记的 `sensor_window_real_four_sensor.json` 外，其他 SensorWindow 夹具均为可复现模拟数据。

模块 3 提供有效/unknown Observation、热图预览、匿名偏好、房间状态、预测和 recommendation stub 的固定负载。所有夹具均须由对应共享 Schema 验证。
