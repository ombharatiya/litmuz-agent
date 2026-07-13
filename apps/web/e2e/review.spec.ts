import { expect, test } from '@playwright/test';

import { API, FIXTURE_REPORT } from './fixtures';

// FIXTURE_REPORT has one routed-and-unreviewed claim (c3, red, fabricated) and one already-green
// claim (c1). We drive the session's "Review queue" button and the human decision through to the
// report showing a final, audited assessment.

test('the session review panel is active only when the report has open review items, and resolving a claim updates the report', async ({
  page,
}) => {
  let report = structuredClone(FIXTURE_REPORT);
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: report }));
  await page.route(`${API}/queue/c3/review`, (route) => {
    const claim = report.claims.find((c) => c.id === 'c3')!;
    Object.assign(claim, {
      reviewed: true,
      reviewed_by: 'anonymous',
      reviewed_at: '2026-07-13T00:00:00Z',
      review_action: 'override_verdict',
      effective_traffic_light: 'yellow',
      effective_verdict: { label: 'unsupported', confidence: null, rationale: 'Needs a fresh source.' },
    });
    return route.fulfill({ status: 204, body: '' });
  });

  await page.goto('/report?id=r1');
  await expect(page.locator('[data-testid="claims"] .claim-card')).toHaveCount(3);

  // Two claims are routed to review (c2 yellow, c3 red) and neither is reviewed yet.
  const toggle = page.getByRole('button', { name: 'Review queue (2)' });
  await expect(toggle).toBeEnabled();
  await toggle.click();

  const sessionReview = page.locator('[data-testid="session-review"]');
  await expect(sessionReview.locator('.review-panel-item')).toHaveCount(2);

  // Resolve the fabricated-citation claim as "still unsupported" with a rationale.
  const item = sessionReview.locator('[data-claim-id="c3"]');
  await item.getByRole('button', { name: 'Mark still unsupported' }).click();
  await item.getByPlaceholder('Why is this the final call? What did you check?').fill('Needs a fresh source.');
  await item.getByRole('button', { name: 'Submit review' }).click();

  // The report re-fetches and the claim now carries the final, audited assessment.
  await expect(page.locator('.claim-card[data-claim-id="c3"] .claim-reviewed')).toHaveText(
    'Reviewed - verdict changed',
  );
  await expect(page.locator('.claim-card[data-claim-id="c3"]')).toHaveAttribute('data-light', 'yellow');
  const audit = page.locator('.claim-card[data-claim-id="c3"] [data-testid="claim-audit"]');
  await expect(audit).toContainText('Reviewed by human: unsupported.');
  await expect(audit).toContainText('anonymous');
  await expect(audit).toContainText('Needs a fresh source.');
  await expect(audit).toContainText('Original machine verdict: not judged (D5)');

  // Only the still-open safety/yellow claim remains in the session review panel now.
  await expect(sessionReview.locator('.review-panel-item')).toHaveCount(1);
});

test('the review toggle is disabled when nothing in the session needs review', async ({ page }) => {
  const clean = structuredClone(FIXTURE_REPORT);
  clean.claims = [clean.claims[0]]; // only the green, non-routed claim
  clean.summary_counts = { total: 1, by_traffic_light: { green: 1, yellow: 0, red: 0 }, routed_to_review: 0 };
  await page.route(`${API}/reports/r1`, (route) => route.fulfill({ json: clean }));

  await page.goto('/report?id=r1');
  await expect(page.getByRole('button', { name: 'Review queue (0)' })).toBeDisabled();
});
