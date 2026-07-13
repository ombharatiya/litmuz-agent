import { expect, test } from '@playwright/test';

import { API } from './fixtures';

test('the queue lists a flagged claim and resolves it on accept', async ({ page }) => {
  const item = {
    claim_id: 'c3',
    report_id: 'r1',
    text: 'A result cited to a fabricated reference.',
    category: 'citation',
    diagnostic: 'D5',
    traffic_light: 'red',
  };
  let reviewed = false;
  let lastBody: Record<string, unknown> | null = null;
  await page.route(`${API}/queue`, (route) => route.fulfill({ json: reviewed ? [] : [item] }));
  await page.route(`${API}/queue/c3/review`, (route) => {
    reviewed = true;
    lastBody = route.request().postDataJSON();
    return route.fulfill({ status: 204, body: '' });
  });

  await page.goto('/queue');
  await expect(page.locator('[data-testid="queue"] .claim-card')).toHaveCount(1);
  // The flagged claim renders honestly.
  await expect(page.locator('.claim-card[data-light="red"] .verdict-label')).toHaveText('Flagged');

  await page.getByRole('button', { name: 'Confirm as shown' }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();

  await expect(page.locator('[data-testid="queue"] .claim-card')).toHaveCount(0);
  expect(lastBody).toMatchObject({ action: 'accept' });
});

test('an override requires a rationale and posts the chosen label', async ({ page }) => {
  const item = {
    claim_id: 'c3',
    report_id: 'r1',
    text: 'A result cited to a fabricated reference.',
    category: 'citation',
    diagnostic: 'D5',
    traffic_light: 'red',
  };
  let lastBody: Record<string, unknown> | null = null;
  await page.route(`${API}/queue`, (route) => route.fulfill({ json: [item] }));
  await page.route(`${API}/queue/c3/review`, (route) => {
    lastBody = route.request().postDataJSON();
    return route.fulfill({ status: 204, body: '' });
  });

  await page.goto('/queue');
  await page.getByRole('button', { name: 'Mark grounded' }).click();

  // No rationale yet: the submit button stays disabled.
  const submit = page.getByRole('button', { name: 'Submit review' });
  await expect(submit).toBeDisabled();

  await page.getByPlaceholder('Why is this the final call? What did you check?').fill('Checked the source directly.');
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect.poll(() => lastBody).toMatchObject({
    action: 'override_verdict',
    new_verdict: { label: 'supported', rationale: 'Checked the source directly.' },
  });
});

test('adding a note does not resolve the claim', async ({ page }) => {
  const item = {
    claim_id: 'c3',
    report_id: 'r1',
    text: 'A result cited to a fabricated reference.',
    category: 'citation',
    diagnostic: 'D5',
    traffic_light: 'red',
  };
  let noteBody: Record<string, unknown> | null = null;
  await page.route(`${API}/queue`, (route) => route.fulfill({ json: [item] }));
  await page.route(`${API}/queue/c3/review`, (route) => {
    noteBody = route.request().postDataJSON();
    return route.fulfill({ status: 204, body: '' });
  });

  await page.goto('/queue');
  await page.getByRole('button', { name: '+ Add a note without resolving' }).click();
  await page.getByPlaceholder('Add a note without resolving this claim...').fill('Still checking.');
  await page.getByRole('button', { name: 'Save note' }).click();

  await expect.poll(() => noteBody).toMatchObject({ action: 'add_note', note: 'Still checking.' });
  // The claim is still listed: the mocked /queue route never changes what it returns for a note.
  await expect(page.locator('[data-testid="queue"] .claim-card')).toHaveCount(1);
});
