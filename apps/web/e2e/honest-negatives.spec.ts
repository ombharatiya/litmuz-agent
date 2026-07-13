import { expect, test } from '@playwright/test';

import { API, FIXTURE_REPORT } from './fixtures';

test.beforeEach(async ({ page }) => {
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: FIXTURE_REPORT }));
});

// The single most important UI invariant: the interface must never launder a negative
// verdict into a pass (AC-WEB-6). Asserted on the actual rendered tokens and icons.
test('a yellow or red claim never uses the green token or a success icon', async ({ page }) => {
  await page.goto('/report?id=r1');
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);

  // No non-green claim carries the success colour token.
  await expect(page.locator('.claim-card[data-light="yellow"][data-token="success"]')).toHaveCount(0);
  await expect(page.locator('.claim-card[data-light="red"][data-token="success"]')).toHaveCount(0);

  // No non-green claim shows the check icon.
  await expect(page.locator('.claim-card[data-light="yellow"] [data-icon="check"]')).toHaveCount(0);
  await expect(page.locator('.claim-card[data-light="red"] [data-icon="check"]')).toHaveCount(0);

  // The check icon appears exactly once, on the green claim.
  await expect(page.locator('[data-testid="claims"] [data-icon="check"]')).toHaveCount(1);
  await expect(page.locator('.claim-card[data-light="green"] [data-icon="check"]')).toHaveCount(1);

  // Literal, honest labels.
  await expect(page.locator('.claim-card[data-light="green"] .verdict-label')).toHaveText('Grounded');
  await expect(page.locator('.claim-card[data-light="yellow"] .verdict-label')).toHaveText('Needs review');
  await expect(page.locator('.claim-card[data-light="red"] .verdict-label')).toHaveText('Flagged');
});

test('the verdict green is a different colour from the brand accent (AC-WEB-DS-1)', async ({ page }) => {
  await page.goto('/report?id=r1');
  const accent = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),
  );
  const success = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--success').trim(),
  );
  expect(accent).not.toBe('');
  expect(success).not.toBe(accent);
});
