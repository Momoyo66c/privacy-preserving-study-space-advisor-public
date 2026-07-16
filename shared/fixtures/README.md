# Shared Fixtures

存放小型、匿名、可复现的跨模块测试负载。禁止提交原始语音、RGB 图像、个人信息和大型采集数据。

当前夹具：

- `sensor_window_empty.json`
- `sensor_window_quiet.json`
- `sensor_window_discussion.json`
- `sensor_window_crowded.json`
- `sensor_window_degraded.json`

这些文件都通过 `shared/contracts/sensor_window.schema.json` 验证。它们用于跨模块契约测试，不代表真实硬件采集结果。
