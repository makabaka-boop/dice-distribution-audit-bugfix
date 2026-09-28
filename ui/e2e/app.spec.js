// @ts-check
import { expect, test } from '@playwright/test';

// Minimal exact-rational arithmetic (bigint, fully reduced) so the browser
// test can recompute the service's reduced fractions without rounding.
function gcd(a, b) {
  a = a < 0n ? -a : a;
  b = b < 0n ? -b : b;
  while (b) [a, b] = [b, a % b];
  return a;
}
function parseFraction(text) {
  const parts = text.trim().split('/');
  const num = BigInt(parts[0]);
  const den = BigInt(parts.length > 1 ? parts[1] : '1');
  return [num, den];
}
function add([n1, d1], [n2, d2]) {
  const n = n1 * d2 + n2 * d1;
  const d = d1 * d2;
  const g = gcd(n, d) || 1n;
  return [n / g, d / g];
}

let apiResponse = null;

async function gotoAndCapture(page) {
  const captured = [];
  page.on('response', async (response) => {
    if (response.url().includes('/api/distribution')) {
      captured.push(await response.json());
    }
  });
  await page.goto('/');
  await expect(page.getByTestId('summary')).toBeVisible();
  return captured;
}

test('chart bars reproduce the raw reduced-fraction response and sum to 1', async ({ page }) => {
  const captured = await gotoAndCapture(page);
  expect(captured.length).toBeGreaterThan(0);
  const body = captured[captured.length - 1];

  // Exact partition: every reduced fraction from the service adds to 1.
  let total = [0n, 1n];
  for (const row of body.distribution) total = add(total, parseFraction(row.probability));
  expect(total).toEqual([1n, 1n]);
  expect(body.total_probability).toBe('1');

  // One bar row per distribution score, in score order, carrying the exact
  // fraction the service returned — the chart cannot invent probabilities.
  const barRows = page.getByTestId('bar-row');
  await expect(barRows).toHaveCount(body.distribution.length);

  for (let i = 0; i < body.distribution.length; i++) {
    const row = body.distribution[i];
    const bar = barRows.nth(i);
    await expect(bar).toHaveAttribute('data-score', String(row.score));
    await expect(bar.getByTestId('bar-fraction')).toHaveText(row.probability);
  }

  // The summary panel shows the same exact expectation and tail probability.
  await expect(page.getByTestId('expected-score')).toHaveText(body.expected_score);
  await expect(page.getByTestId('tail-probability')).toHaveText(
    body.probability_at_least
  );
  await expect(page.getByTestId('total-probability')).toHaveText('1');

  // Floating point re-sum of the chart data is 1 up to rounding; the exact
  // fraction is the source of truth.
  const decimalSum = body.distribution.reduce((s, r) => s + r.decimal, 0);
  expect(Math.abs(decimalSum - 1)).toBeLessThan(1e-9);
});

test('tail probability on the page equals the score-wise recomputation', async ({ page }) => {
  await gotoAndCapture(page);

  const thresholdInput = page.getByTestId('input-threshold');
  const tail = page.getByTestId('tail-probability');

  for (const threshold of [6, 10, 14]) {
    // Arm the waiter before interacting: we want the response the PAGE
    // itself issues for this threshold, not a test-only fetch.
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/distribution') &&
        r.url().includes(`threshold=${threshold}&`)
    );
    await thresholdInput.fill(String(threshold));
    const response = await responsePromise;
    const body = await response.json();

    let expectedTail = [0n, 1n];
    for (const row of body.distribution) {
      if (row.score >= body.params.threshold) {
        expectedTail = add(expectedTail, parseFraction(row.probability));
      }
    }
    const expectedText =
      expectedTail[1] === 1n ? String(expectedTail[0]) : `${expectedTail[0]}/${expectedTail[1]}`;
    // The page must render exactly that response's reduced tail fraction.
    await expect(tail).toHaveText(expectedText);
    await expect(tail).toHaveText(body.probability_at_least);
  }
});

test('editing reroll faces updates the chart consistently with the raw response', async ({ page }) => {
  await gotoAndCapture(page);

  // Wait for the page's own {1,6} request after toggling chip 6.
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().includes('/api/distribution') &&
      r.url().includes('reroll=1&reroll=6')
  );
  const chip6 = page.getByTestId('reroll-chip').filter({ hasText: '6' });
  await chip6.click();
  const response = await responsePromise;
  const body = await response.json();
  expect(body.params.reroll).toEqual([1, 6]);

  // Every bar renders the exact reduced fraction from that response.
  const barRows = page.getByTestId('bar-row');
  await expect(barRows).toHaveCount(body.distribution.length);
  for (let i = 0; i < body.distribution.length; i++) {
    await expect(barRows.nth(i)).toHaveAttribute(
      'data-score',
      String(body.distribution[i].score)
    );
    await expect(barRows.nth(i).getByTestId('bar-fraction')).toHaveText(
      body.distribution[i].probability
    );
  }
});

test('changing faces resets the reroll chips and keeps the distribution exact', async ({ page }) => {
  await gotoAndCapture(page);

  // d2 can only have faces 1 and 2; the previously selected face 6 drops.
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes('/api/distribution') && r.url().includes('faces=2')
  );
  await page.getByTestId('input-faces').selectOption('2');
  const chips = page.getByTestId('reroll-chip');
  await expect(chips).toHaveCount(2);

  const body = await (await responsePromise).json();
  expect(body.params.faces).toBe(2);
  await expect(page.getByTestId('total-probability')).toHaveText(
    body.total_probability
  );
  expect(body.total_probability).toBe('1');
});

test('UI requests the odds service over real HTTP through the UI origin', async ({ request }) => {
  // Directly exercise the proxied HTTP endpoint that the page uses.
  const res = await request.get(
    '/api/distribution?n_dice=4&faces=8&keep=3&reroll=1&reroll=8'
  );
  expect(res.ok()).toBe(true);
  const body = await res.json();
  expect(body.params).toMatchObject({ n_dice: 4, faces: 8, keep: 3 });
  expect(body.params.reroll).toEqual([1, 8]);

  let total = [0n, 1n];
  for (const row of body.distribution) total = add(total, parseFraction(row.probability));
  expect(total).toEqual([1n, 1n]);
});

test('a slow earlier response cannot overwrite a newer rule result', async ({ page }) => {
  // Hold any faces=2 response until the test releases it, so a later
  // faces=3 request resolves first while the faces=2 one is still in flight.
  let releaseStale = () => {};
  const staleGate = new Promise((resolve) => (releaseStale = resolve));
  await page.route('**/api/distribution**', async (route) => {
    if (route.request().url().includes('faces=2')) {
      const response = await route.fetch();
      await staleGate;
      await route.fulfill({ response });
    } else {
      await route.continue();
    }
  });

  await page.goto('/');
  await expect(page.getByTestId('summary')).toBeVisible();

  // Switch to faces=2: that request gets held open by the route gate.
  const faces2Requested = page.waitForRequest((r) =>
    r.url().includes('/api/distribution') && r.url().includes('faces=2')
  );
  await page.getByTestId('input-faces').selectOption('2');
  await faces2Requested;

  // Immediately switch to faces=3; this response arrives first.
  const faces3Promise = page.waitForResponse(
    (r) => r.url().includes('/api/distribution') && r.url().includes('faces=3')
  );
  await page.getByTestId('input-faces').selectOption('3');
  const faces3Body = await (await faces3Promise).json();
  expect(faces3Body.params.faces).toBe(3);

  // The settled page renders the faces=3 result while faces=2 is pending.
  await expect(page.getByTestId('bar-row')).toHaveCount(
    faces3Body.distribution.length
  );
  await expect(page.getByTestId('total-probability')).toHaveText(
    faces3Body.total_probability
  );

  // Release the stale faces=2 response and let it land.
  releaseStale();
  await page.waitForTimeout(500);

  // The page must still show faces=3: stale data (and only 2 reroll chips)
  // must not overwrite the current rule.
  await expect(page.getByTestId('input-faces')).toHaveValue('3');
  await expect(page.getByTestId('reroll-chip')).toHaveCount(3);
  await expect(page.getByTestId('bar-row')).toHaveCount(
    faces3Body.distribution.length
  );
  await expect(page.getByTestId('total-probability')).toHaveText(
    faces3Body.total_probability
  );
});
