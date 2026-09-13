import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  expect: { timeout: 10000 },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "firefox", use: { browserName: "firefox" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  use: {
    baseURL: "http://127.0.0.1:3001",
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "../.venv/bin/python tests/serve_backend.py",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: "npm run start -- --port 3001",
      url: "http://127.0.0.1:3001",
      reuseExistingServer: false,
      env: { POLICY_API_URL: "http://127.0.0.1:8001" },
      timeout: 30000,
    },
  ],
});
