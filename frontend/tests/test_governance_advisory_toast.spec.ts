import { test, expect } from '@playwright/test';

const FIXTURE_HTML = `
<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8" />
    <style>
      body { font-family: Arial, sans-serif; padding: 24px; }
      .toast {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        border: 1px solid #fbbf24;
        background: #fffbeb;
        color: #78350f;
        border-radius: 8px;
        padding: 12px 16px;
        max-width: 720px;
      }
      .hidden { display: none; }
      button { border: 0; background: transparent; color: #92400e; cursor: pointer; }
    </style>
  </head>
  <body>
    <div class="toast" role="status" data-testid="governance-advisory-toast">
      <div>
        <strong>Cảnh báo khuyến nghị</strong>
        <ul data-testid="governance-advisory-toast-list">
          <li data-testid="governance-advisory-item-agile.wip.override">
            Bạn không có quyền vượt giới hạn việc đang làm (agile.wip.override)
          </li>
          <li data-testid="governance-advisory-item-agile.dod.bypass">
            Bạn không có quyền bỏ qua điều kiện Hoàn thành (agile.dod.bypass)
          </li>
        </ul>
        <span>Đây chỉ là cảnh báo — thao tác vẫn được ghi nhận.</span>
      </div>
      <button type="button" aria-label="Đóng cảnh báo" data-testid="governance-advisory-toast-dismiss">×</button>
    </div>
    <script>
      document.querySelector('[data-testid="governance-advisory-toast-dismiss"]').addEventListener('click', () => {
        document.querySelector('[data-testid="governance-advisory-toast"]').remove();
      });
    </script>
  </body>
</html>`;

test('governance advisory toast renders Vietnamese permission guidance and dismisses', async ({ page }) => {
  await page.setContent(FIXTURE_HTML);

  await expect(page.getByTestId('governance-advisory-toast')).toBeVisible();
  await expect(page.getByTestId('governance-advisory-toast')).toHaveAttribute('role', 'status');
  await expect(page.getByTestId('governance-advisory-toast')).toContainText('Cảnh báo khuyến nghị');
  await expect(page.getByTestId('governance-advisory-item-agile.wip.override')).toContainText(
    'Bạn không có quyền vượt giới hạn việc đang làm'
  );
  await expect(page.getByTestId('governance-advisory-item-agile.dod.bypass')).toContainText(
    'Bạn không có quyền bỏ qua điều kiện Hoàn thành'
  );
  await expect(page.getByTestId('governance-advisory-toast')).toContainText(
    'Đây chỉ là cảnh báo — thao tác vẫn được ghi nhận.'
  );

  await page.getByTestId('governance-advisory-toast-dismiss').click();
  await expect(page.getByTestId('governance-advisory-toast')).toHaveCount(0);
});
