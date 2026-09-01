import { defineConfig } from "@playwright/test";

// UI 交互自测：应用已由后端源码服务（http://127.0.0.1:8765/，serves web/dist）
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60000,
  retries: 1,
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:8765",
    channel: "msedge", // 复用系统 Edge，无需下载浏览器
    headless: true,
    viewport: { width: 1440, height: 880 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
});
