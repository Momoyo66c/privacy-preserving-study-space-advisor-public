import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/gate-a",
  timeout: 30_000,
  webServer: [
    {
      command: "python ../tests/integration/gate_a_server.py",
      url: "http://127.0.0.1:8011/health",
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        GATE_A_BACKEND_PORT: "8011",
      },
    },
    {
      command: "node ./node_modules/vite/bin/vite.js --force --host 127.0.0.1 --port 5177",
      url: "http://127.0.0.1:5177",
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_API_MODE: "real",
        VITE_API_BASE_URL: "http://127.0.0.1:8011",
        VITE_REFRESH_SECONDS: "60",
      },
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:5177",
    trace: "on-first-retry",
  },
  projects: [
    { name: "gate-a-chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
