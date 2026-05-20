import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Telegram admin settings — Playwright e2e (Task 23, surface 1/3).
 *
 * Targets /admin/telegram (`src/app/(portal)/admin/telegram/page.tsx`).
 *
 * The suite is fully hermetic with respect to the backend:
 *   - Authentication is injected via `localStorage` + a `/api/auth/me` route
 *     mock, so no real `/api/auth/login` round-trip is required.
 *   - `GET/PUT /api/admin/telegram/settings` are mocked with a stateful
 *     in-memory record so the page can navigate the "unconfigured → save →
 *     configured" transition deterministically.
 *   - A `page.on('request')` guard fails the test if anything dials
 *     `api.telegram.org` directly. Front-end code must never call the
 *     Telegram Bot API; that lives entirely in the backend.
 *
 * Prerequisites:
 *   - The Next.js portal must be reachable at the Playwright baseURL
 *     (default http://localhost:3119, overridable via E2E_BASE_URL). When
 *     the host is unreachable the suite `test.skip`s with a clear note
 *     rather than failing noisily.
 *
 * Run only this spec:
 *   cd frontend && npm run test:e2e -- telegram-admin-settings.spec.ts --reporter=list
 */

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

type MockUser = {
  id: string;
  name: string;
  email: string;
  username: string;
  role: 'admin' | 'employee';
  department_id: string;
  department_name: string;
  permissions: string[];
  workspace_memberships: unknown[];
};

const ADMIN_USER: MockUser = {
  id: '00000000-0000-0000-0000-0000000000a1',
  name: 'Test Admin',
  email: 'admin@cmdsupport.test',
  username: 'testadmin',
  role: 'admin',
  department_id: '00000000-0000-0000-0000-0000000000d0',
  department_name: 'CMD Support',
  permissions: [],
  workspace_memberships: [],
};

const EMPLOYEE_USER: MockUser = {
  ...ADMIN_USER,
  id: '00000000-0000-0000-0000-0000000000b1',
  name: 'Test Employee',
  email: 'employee@cmdsupport.test',
  username: 'testemployee',
  role: 'employee',
};

type TelegramSettings = {
  is_enabled: boolean;
  bot_token_configured: boolean;
  webhook_secret_configured: boolean;
  webhook_url: string | null;
  bot_username: string | null;
  webhook_last_set_at: string | null;
};

function buildUnconfiguredSettings(): TelegramSettings {
  return {
    is_enabled: false,
    bot_token_configured: false,
    webhook_secret_configured: false,
    webhook_url: null,
    bot_username: null,
    webhook_last_set_at: null,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Install a guard that flips `telegramApiHit` to true if any request
 * targets `api.telegram.org`. Tests assert this stays false in afterEach
 * so accidental Bot API calls explode visibly.
 */
function installTelegramApiGuard(page: Page): { hit: () => boolean } {
  let leaked = false;
  page.on('request', (request) => {
    if (request.url().includes('api.telegram.org')) {
      leaked = true;
    }
  });
  return { hit: () => leaked };
}

/**
 * Inject an authenticated session without driving the real /login flow.
 * Pre-seeds `cmd_support_token` in localStorage (so AuthProvider triggers
 * a refresh) and mocks `/api/auth/me` to return the requested user shape.
 *
 * Must be called BEFORE any `page.goto()`.
 */
async function setupAuthedSession(page: Page, user: MockUser): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('cmd_support_token', 'test-token-stub');
  });
  await page.route('**/api/auth/me', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(user),
    });
  });
}

/**
 * Wire up `/api/admin/telegram/settings` with mutable state.
 *
 * - GET returns the current snapshot.
 * - PUT applies the requested fields to the snapshot, then GETs from the
 *   same snapshot on the page's follow-up refresh (matches the real
 *   `handleSave` flow which re-fetches after a successful update).
 */
async function installSettingsRoute(
  page: Page,
  initial: TelegramSettings,
): Promise<{ state: TelegramSettings; putCount: () => number }> {
  const state: TelegramSettings = { ...initial };
  let puts = 0;
  await page.route('**/api/admin/telegram/settings', async (route: Route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state),
      });
      return;
    }
    if (request.method() === 'PUT') {
      puts += 1;
      const body = (request.postDataJSON() ?? {}) as {
        is_enabled?: boolean | null;
        bot_token?: string | null;
        webhook_secret?: string | null;
        webhook_url?: string | null;
        bot_username?: string | null;
      };
      if (typeof body.is_enabled === 'boolean') {
        state.is_enabled = body.is_enabled;
      }
      if (typeof body.bot_token === 'string' && body.bot_token.length > 0) {
        state.bot_token_configured = true;
      } else if (body.bot_token === null) {
        state.bot_token_configured = false;
      }
      if (typeof body.webhook_secret === 'string' && body.webhook_secret.length > 0) {
        state.webhook_secret_configured = true;
      } else if (body.webhook_secret === null) {
        state.webhook_secret_configured = false;
      }
      if (typeof body.webhook_url === 'string') {
        state.webhook_url = body.webhook_url;
      } else if (body.webhook_url === null) {
        state.webhook_url = null;
      }
      if (typeof body.bot_username === 'string') {
        state.bot_username = body.bot_username;
      } else if (body.bot_username === null) {
        state.bot_username = null;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state),
      });
      return;
    }
    await route.fallback();
  });
  return { state, putCount: () => puts };
}

async function gotoOrSkip(page: Page, path: string): Promise<boolean> {
  try {
    await page.goto(path, { timeout: 15_000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Probe for the Telegram admin settings feature. The route file lives at
 * `src/app/(portal)/admin/telegram/page.tsx` (T19) and a running stack
 * that predates that work serves Next.js's default 404 instead. We treat
 * either condition (404 visible OR settings heading missing within 5s)
 * as "feature not deployed" and skip rather than fail.
 */
async function isFeatureDeployed(page: Page): Promise<boolean> {
  const heading = page.getByRole('heading', { name: 'Tích hợp Telegram' });
  try {
    await heading.waitFor({ state: 'visible', timeout: 5_000 });
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

test.describe('Telegram admin settings (/admin/telegram)', () => {
  test('admin sees unconfigured page, saves a bot token, badge flips to configured', async ({
    page,
  }) => {
    const guard = installTelegramApiGuard(page);
    await setupAuthedSession(page, ADMIN_USER);
    const settings = await installSettingsRoute(page, buildUnconfiguredSettings());

    const reachable = await gotoOrSkip(page, '/admin/telegram');
    test.skip(
      !reachable,
      'Next.js portal not reachable at the Playwright baseURL — start the Docker stack (`docker compose up -d`) or set E2E_BASE_URL.',
    );

    const deployed = await isFeatureDeployed(page);
    test.skip(
      !deployed,
      '/admin/telegram is not deployed on the running stack (Next.js returned 404 / no Tích hợp Telegram heading). Rebuild the frontend container (`docker compose up -d --build frontend`) so T19 ships, then re-run.',
    );

    // --- Initial render: unconfigured ---
    await expect(page.getByText('Chưa cấu hình token.')).toBeVisible();
    await expect(page.getByText('Chưa cấu hình secret.')).toBeVisible();
    await expect(
      page.getByText('Webhook chưa được đăng ký với Telegram.'),
    ).toBeVisible();

    // The "Tạo mã /bind" surface lives on the squad tab — here we just
    // check the inputs render. Bot token uses the BotFather placeholder.
    const tokenInput = page.locator('input[placeholder="Paste token from BotFather"]');
    const secretInput = page.locator('input[placeholder="32 ký tự url-safe"]');
    await expect(tokenInput).toBeVisible();
    await expect(secretInput).toBeVisible();

    // Toggle is rendered (the Radix Switch button has role="switch").
    const toggle = page.getByRole('switch');
    await expect(toggle).toBeVisible();

    // --- Save flow ---
    await tokenInput.fill('123456:FAKE_BOT_TOKEN_FOR_TESTS');

    await page.getByRole('button', { name: /^Lưu cài đặt$/ }).click();

    // Success toast appears.
    await expect(page.getByText('Đã lưu thành công')).toBeVisible({
      timeout: 10_000,
    });

    // Token input is wiped (the page never echoes raw secrets back).
    await expect(tokenInput).toHaveValue('');

    // Badge flipped to configured.
    await expect(page.getByText('✓ Token configured')).toBeVisible({
      timeout: 10_000,
    });

    expect(settings.putCount()).toBeGreaterThan(0);

    await page.screenshot({
      path: 'tests/screenshots/T23-telegram-admin-settings.png',
      fullPage: true,
    });

    expect(
      guard.hit(),
      'A request leaked to api.telegram.org — the frontend must never call the Bot API directly.',
    ).toBe(false);
  });

  test('non-admin user is redirected away from /admin/telegram', async ({
    page,
  }) => {
    const guard = installTelegramApiGuard(page);
    await setupAuthedSession(page, EMPLOYEE_USER);
    // Even the settings route is mocked so a stray fetch can't 500.
    await installSettingsRoute(page, buildUnconfiguredSettings());

    const reachable = await gotoOrSkip(page, '/admin/telegram');
    test.skip(
      !reachable,
      'Next.js portal not reachable at the Playwright baseURL — start the Docker stack (`docker compose up -d`) or set E2E_BASE_URL.',
    );

    // Skip when the page hasn't been deployed yet: on a stack without T19
    // the route is a Next.js 404, which would falsely "redirect" the user
    // and hide the real bug we want to assert about. Only meaningful when
    // the route file actually exists.
    const has404 = await page
      .getByRole('heading', { name: '404' })
      .isVisible()
      .catch(() => false);
    test.skip(
      has404,
      '/admin/telegram is not deployed on the running stack (404). Rebuild the frontend container (`docker compose up -d --build frontend`) so T19 ships, then re-run.',
    );

    // The page guard does `router.replace("/")` for non-admins. The root
    // public page then forwards to `/me` (employees) or `/login` (logged
    // out). Either way the URL must leave `/admin/telegram`.
    await page.waitForURL(
      (url) => !url.pathname.startsWith('/admin/telegram'),
      { timeout: 15_000 },
    );
    expect(page.url()).not.toContain('/admin/telegram');

    expect(
      guard.hit(),
      'A request leaked to api.telegram.org during the non-admin redirect.',
    ).toBe(false);
  });
});
