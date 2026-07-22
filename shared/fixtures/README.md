# Shared Fixtures

Authenticated fixtures are synthetic contract examples only. The credential fixture contains an explicitly fake password and must never be reused as a deployed credential. Session, preference-learning, and room-selection fixtures contain no name, email, student number, cookie, raw audio, thermal frame, radar track, or precise personal location.

存放小型、匿名、可复现的跨模块测试负载。禁止提交原始语音、RGB 图像、个人信息和大型采集数据。

模块 1 提供以下 SensorWindow 夹具：

- `sensor_window_empty.json`
- `sensor_window_quiet.json`
- `sensor_window_discussion.json`
- `sensor_window_crowded.json`
- `sensor_window_degraded.json`

这些文件都通过 `shared/contracts/sensor_window.schema.json` 验证。它们用于跨模块契约测试，不代表真实硬件采集结果。

模块 3 提供有效/unknown Observation、热图预览、匿名偏好、房间状态、预测和 recommendation stub 的固定负载。所有夹具均须由对应共享 Schema 验证。
