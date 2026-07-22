# Module 4 — Sensor Dashboard

零运行时依赖的本地传感器监控界面。当前页面显示温度、湿度、光照、声音强度以及 32 × 24 匿名热分布。默认使用模拟数据，后端不可用时也能独立演示。

## 安装与启动

```bash
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173`。默认 `useMocks=true`，模拟数据每 900 ms 刷新一次。热图通过约 680 ms 的时间插值和浏览器高质量空间采样平滑过渡，界面按钮可随时切换平滑/原始像素显示。

## 切换到真实后端

编辑 `index.html` 中的配置，将 `useMocks` 改为 `false`；也可以直接访问 `http://127.0.0.1:5173/?mode=api`：

```js
window.AIOT_CONFIG = {
  useMocks: false,
  apiBaseUrl: "http://127.0.0.1:8000",
  roomId: "room_a",
  pollIntervalMs: 2500
};
```

前端读取 `GET /api/v1/rooms/{room_id}/live`。后端聚合现有 `RoomStatus` 和 `ThermalPreview`；模块 02 仍通过既有 observation 与 thermal-preview 写接口提供数据，不创建第二条存储路径。

## 检查

```bash
npm test
npm run build
```

页面在手机、平板和桌面使用同一套移动优先布局；所有主要按钮至少 44 px，可键盘操作，并支持 `prefers-reduced-motion`。热图只展示 32 × 24 的 0–1 归一化预览，不含绝对温度、RGB 图像或身份信息。
