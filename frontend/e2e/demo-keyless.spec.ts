import { expect, test, type Page } from '@playwright/test';

const allowedOrigins = new Set([
  new URL(process.env.E2E_BASE_URL || 'http://localhost:5173').origin,
  new URL(process.env.E2E_API_URL || 'http://localhost:8000').origin,
]);

async function installOriginDenylist(page: Page): Promise<string[]> {
  const blocked: string[] = [];
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      await route.continue();
      return;
    }
    if (!allowedOrigins.has(new URL(url).origin)) {
      blocked.push(url);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  return blocked;
}

async function loginAs(page: Page, label: 'Provider' | 'Customer' | 'Field agent'): Promise<void> {
  await page.goto('/login');
  await page.getByRole('button', { name: new RegExp(`^${label} ·`) }).click();
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

test('keyless demo uses the real API for all three roles and no third-party origin', async ({ page }) => {
  const blocked = await installOriginDenylist(page);

  await loginAs(page, 'Provider');
  await page.goto('/dashboard/team');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect.poll(() => page.locator('.maplibregl-marker').count()).toBeGreaterThan(0);

  await page.evaluate(() => localStorage.clear());
  await loginAs(page, 'Customer');

  await page.evaluate(() => localStorage.clear());
  await loginAs(page, 'Field agent');
  await page.goto('/mobile/jobs');
  await expect(page.getByRole('heading', { name: 'Axiar Field' })).toBeVisible();

  expect(blocked, `Unexpected third-party requests: ${blocked.join(', ')}`).toEqual([]);
});
