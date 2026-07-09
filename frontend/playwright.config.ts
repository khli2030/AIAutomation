import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.UI_E2E_PORT || 3100);
const BASE_URL = process.env.UI_E2E_BASE_URL || `http://127.0.0.1:${PORT}`;

/**
 * Phase 7.5 UI E2E — MOCK_MODE happy path.
 * Starts Next.js against loopback; API calls are intercepted (no real Ansible).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: {
    command: `npx next dev --port ${PORT} --hostname 127.0.0.1`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000",
      // Lab-only for automated UI E2E — not a production secret.
      NEXT_PUBLIC_ADMIN_TOKEN: "ui-e2e-mock-token",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
