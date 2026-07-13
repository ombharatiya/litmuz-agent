import { expect, test } from '@playwright/test';

import { API, FIXTURE_REPORT } from './fixtures';

test('selecting the genomic criteria posts mode: "genomic"', async ({ page }) => {
  let submittedBody: Record<string, unknown> | null = null;
  await page.route(`${API}/me/jobs`, (route) => route.fulfill({ json: [] }));
  await page.route(`${API}/verifications`, (route) => {
    submittedBody = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { job_id: 'j1' } });
  });
  await page.route(`${API}/verifications/j1`, (route) =>
    route.fulfill({
      json: {
        job_id: 'j1',
        status: 'completed',
        stage: null,
        claims_done: 3,
        claims_total: 3,
        report_id: 'r1',
        mode: 'genomic',
      },
    }),
  );
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: FIXTURE_REPORT }));

  await page.goto('/');

  // Pick the genomic criteria, then compose and verify.
  await page.getByRole('radio', { name: /Genomic evidence/ }).click();
  await expect(page.getByRole('radio', { name: /Genomic evidence/ })).toHaveAttribute(
    'aria-checked',
    'true',
  );

  await page.getByLabel('memo').fill('HAR1 evolved rapidly in the human lineage [1].');
  await page.getByRole('button', { name: 'Verify' }).click();

  // The flow completes into the canvas, and the POST carried the selected mode.
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);
  await expect.poll(() => submittedBody).toMatchObject({ mode: 'genomic' });
});
