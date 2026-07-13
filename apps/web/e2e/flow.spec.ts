import { expect, test } from '@playwright/test';

import { API, FIXTURE_REPORT } from './fixtures';

test('submitting a memo runs the verification in the right-hand canvas', async ({ page }) => {
  await page.route(`${API}/me/jobs`, (route) => route.fulfill({ json: [] }));
  await page.route(`${API}/verifications`, (route) =>
    route.fulfill({ status: 202, json: { job_id: 'j1' } }),
  );
  let polls = 0;
  await page.route(`${API}/verifications/j1`, (route) => {
    polls += 1;
    const body =
      polls < 2
        ? { job_id: 'j1', status: 'running', stage: 'verify', claims_done: 1, claims_total: 3, report_id: null }
        : { job_id: 'j1', status: 'completed', stage: null, claims_done: 3, claims_total: 3, report_id: 'r1' };
    return route.fulfill({ json: body });
  });
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: FIXTURE_REPORT }));

  await page.goto('/');

  // The canvas is closed until a verification is running.
  await expect(page.locator('.studio-canvas')).toHaveCount(0);

  await page.getByLabel('memo').fill('TP53 is a tumour suppressor [1].');
  await page.getByRole('button', { name: 'Verify' }).click();

  // The canvas opens in place (no navigation away from the studio) and shows live progress.
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('.studio-canvas')).toBeVisible();
  await expect(page.locator('[data-testid="job-status"]')).toBeVisible();

  // Once the job completes, the report is published into the same canvas.
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);
});

test('the canvas can be collapsed and reopened without losing the result', async ({ page }) => {
  await page.route(`${API}/me/jobs`, (route) => route.fulfill({ json: [] }));
  await page.route(`${API}/verifications`, (route) =>
    route.fulfill({ status: 202, json: { job_id: 'j1' } }),
  );
  await page.route(`${API}/verifications/j1`, (route) =>
    route.fulfill({
      json: { job_id: 'j1', status: 'completed', stage: null, claims_done: 3, claims_total: 3, report_id: 'r1' },
    }),
  );
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: FIXTURE_REPORT }));

  await page.goto('/');
  await page.getByLabel('memo').fill('TP53 is a tumour suppressor [1].');
  await page.getByRole('button', { name: 'Verify' }).click();
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);

  // Collapse the canvas.
  await page.getByRole('button', { name: 'Collapse canvas' }).click();
  await expect(page.locator('.studio-canvas')).toHaveCount(0);

  // Reopen it from the composer and the report is still there.
  await page.getByRole('button', { name: 'Show result' }).click();
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);
});

test('selecting a past session shows its memo (read-only) beside its report', async ({ page }) => {
  const memo = 'TP53 is a tumour suppressor [1].\n\nReferences\n1. Smith J. Nature. 2020. PMID: 12345.';
  await page.route(`${API}/me/jobs`, (route) =>
    route.fulfill({
      json: [
        {
          job_id: 'j9',
          status: 'completed',
          stage: null,
          report_id: 'r1',
          created_at: '2026-07-10T00:00:00Z',
          title: 'TP53 tumour suppressor',
          memo_snippet: 'TP53 is a tumour suppressor [1].',
        },
      ],
    }),
  );
  await page.route(`${API}/verifications/j9`, (route) =>
    route.fulfill({
      json: {
        job_id: 'j9',
        status: 'completed',
        stage: null,
        claims_done: 3,
        claims_total: 3,
        report_id: 'r1',
        memo,
        title: 'TP53 tumour suppressor',
      },
    }),
  );
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: FIXTURE_REPORT }));

  await page.goto('/');

  // The session is listed by its generated title, not "Untitled".
  await page.getByRole('button', { name: 'TP53 tumour suppressor' }).click();

  // The input (memo) is shown read-only, and the output (report) is in the canvas.
  await expect(page.getByLabel('memo')).toHaveValue(memo);
  await expect(page.getByLabel('memo')).not.toBeEditable();
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);
  // There is no Verify in a past session; New verification starts a fresh one.
  await expect(page.getByRole('button', { name: 'Verify', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'New verification', exact: true })).toBeVisible();
});
