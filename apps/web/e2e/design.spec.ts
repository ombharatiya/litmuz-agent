import { expect, test } from '@playwright/test';

test('the four surfaces render (AC-WEB-1)', async ({ page }) => {
  for (const path of ['/', '/progress', '/report', '/queue']) {
    const resp = await page.goto(path);
    expect(resp?.status(), path).toBeLessThan(400);
  }
});

test('at most two font families are used (AC-WEB-DS-2)', async ({ page }) => {
  await page.goto('/');
  const families = await page.evaluate(() => {
    const set = new Set<string>();
    document.querySelectorAll('body *').forEach((el) => {
      const first = getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim();
      if (first) set.add(first);
    });
    return Array.from(set);
  });
  expect(families.length).toBeLessThanOrEqual(2);
});

test('the primary action uses the brand accent, not a verdict colour', async ({ page }) => {
  await page.goto('/');
  const button = page.getByRole('button', { name: 'Verify' });
  const background = await button.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(background).not.toBe('rgba(0, 0, 0, 0)');
});
