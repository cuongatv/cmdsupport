import { test, expect } from '@playwright/test';
import path from 'node:path';

/**
 * Smoke test: log in as the default admin and confirm we reach the admin
 * dashboard. Selectors target the actual login form in
 * `frontend/src/app/login/page.tsx` (id="email", id="password",
 * Vietnamese button label "Đăng nhập").
 */
const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? 'admin@cmdsupport.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'cmd@1234';

const SCREENSHOT_DIR =
  process.env.SMOKE_SCREENSHOT_DIR ??
  path.resolve(__dirname, '..', '..', '.sisyphus', 'evidence', 'task-0-playwright-smoke');

test('admin login lands on /admin', async ({ page }) => {
  await page.goto('/login');
  await expect(page).toHaveURL(/\/login$/);

  await page.locator('#email').fill(ADMIN_EMAIL);
  await page.locator('#password').fill(ADMIN_PASSWORD);

  await Promise.all([
    page.waitForURL(/\/admin(\/.*)?$/, { timeout: 15_000 }),
    page.getByRole('button', { name: /đăng nhập/i }).click(),
  ]);

  expect(page.url()).toMatch(/\/admin(\/.*)?$/);

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'admin-after-login.png'),
    fullPage: true,
  });
});
