import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
    env: {
      VITE_API_MODE: "mock",
    },
    exclude: ["tests/e2e/**", "tests/gate-a/**", "node_modules/**", "dist/**"],
  },
});
