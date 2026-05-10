import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the CMD Support frontend smoke suite.
 *
 * The config intentionally has no `webServer` block — tests are expected to
 * run against the Docker stack (`docker compose up -d`). Override the target
 * URL via `E2E_BASE_URL` if you point at a different deployment.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3119',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
