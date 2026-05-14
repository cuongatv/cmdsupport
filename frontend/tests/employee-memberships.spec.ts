import { test, expect } from '@playwright/test';

/**
 * T13 placeholder — primary + secondary memberships in the employee dialog.
 *
 * The full scenario from `.sisyphus/plans/unit-agile-upgrade.md` T13 lives
 * here in a single skipped test so future iterations can flesh out the
 * assertions without re-discovering the flow. It is intentionally `.skip`
 * until seed data is available in CI.
 *
 * Scenario:
 *   1. Open /admin/employees
 *   2. Click "Thêm người dùng"
 *   3. Fill name / email / password
 *   4. Pick a primary department (a business_group) — "Đơn vị chính"
 *   5. Under "Các đơn vị khác" click "Thêm đơn vị", pick a squad_team
 *      department, pick a Squad-only role ("Developer"), set capacity 50
 *   6. Submit. Expect a successful create and the new row to appear.
 *   7. Re-open the new user in edit mode. Expect the secondary membership
 *      row to be pre-populated, with the role select filtered by the
 *      squad's allowed roles.
 *
 * Note: the assertions below intentionally use loose selectors so they
 * survive cosmetic markup tweaks while still pinning the behaviour the
 * task asks for. Replace `test.skip` with `test` once a seeded admin
 * account and two departments (one business_group, one squad_team) are
 * available in the e2e environment.
 */
test.skip('create employee with primary + secondary memberships', async ({ page }) => {
  await page.goto('/admin/employees');

  // Open the create dialog.
  await page.getByRole('button', { name: /thêm người dùng/i }).click();

  // Primary unit select is labelled "Đơn vị chính".
  await expect(page.getByText(/đơn vị chính/i)).toBeVisible();

  // The secondaries section is labelled "Các đơn vị khác" with an
  // "Thêm đơn vị" button below it.
  await expect(page.getByText(/các đơn vị khác/i)).toBeVisible();
  await page.getByRole('button', { name: /thêm đơn vị/i }).click();

  // After picking a squad_team department, the role select offers
  // Developer / Product Owner / Scrum Master alongside the shared roles.
  // (Full assertions deferred until the seed dataset lands.)
});
