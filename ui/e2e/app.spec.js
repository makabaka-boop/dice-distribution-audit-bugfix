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

test('a slow earlier response never overwrites the newest rule result', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByTestId('summary')).toBeVisible();

  // Capture the two real responses up front (APIRequestContext is not
  // affected by page.route), so they can later be delivered out of order.
  const urlFor = (threshold) =>
    `/api/distribution?n_dice=3&faces=6&keep=2&threshold=${threshold}&reroll=1`;
  const [res10, res11] = await Promise.all([
    request.get(urlFor('10')),
    request.get(urlFor('11'))
  ]);
  const body10 = await res10.text();
  const body11 = await res11.text();
  expect(body10).not.toBe(body11);

  // Gate every distribution request by its threshold; matched responses are
  // fulfilled locally and held until the test releases them.
  const gates = new Map();
  await page.route(/\/api\/distribution\?/, async (route) => {
    const threshold = new URL(route.request().url()).searchParams.get('threshold');
    if (gates.has(threshold)) {
      await gates.get(threshold);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: threshold === '10' ? body10 : body11
      });
    }
    await route.continue();
  });

  let releaseTen;
  gates.set('10', new Promise((resolve) => (releaseTen = resolve)));
  let releaseEleven;
  gates.set('11', new Promise((resolve) => (releaseEleven = resolve)));

  // Arm each waiter BEFORE the interaction, and don't change the rule again
  // until the first request is confirmed in flight.
  const waitTen = page.waitForRequest((r) => r.url().includes('threshold=10'));
  await page.getByTestId('input-threshold').fill('10');
  await waitTen;
  const waitEleven = page.waitForRequest((r) => r.url().includes('threshold=11'));
  await page.getByTestId('input-threshold').fill('11');
  await waitEleven;

  // NEWEST response arrives first; the older threshold=10 response last.
  releaseEleven();
  await expect(page.getByText('P(总分 ≥ 11)')).toBeVisible();
  const newestTail = await page.getByTestId('tail-probability').textContent();
  releaseTen();

  // The stale threshold=10 response must be ignored, not painted.
  await page.waitForTimeout(200);
  expect(await page.getByTestId('tail-probability').textContent()).toBe(newestTail);
  await expect(page.getByText('P(总分 ≥ 10)')).toHaveCount(0);
});

test('a late error from an earlier request never wipes the current result', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByTestId('summary')).toBeVisible();

  // A real success body for the newest rule (threshold 12).
  const res12 = await request.get(
    '/api/distribution?n_dice=3&faces=6&keep=2&threshold=12&reroll=1'
  );
  const body12 = await res12.text();

  const gates = new Map();
  await page.route(/\/api\/distribution\?/, async (route) => {
    const threshold = new URL(route.request().url()).searchParams.get('threshold');
    if (threshold === '10') {
      await gates.get('10');
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ error: '迟到的错误' })
      });
    }
    if (threshold === '12') {
      await gates.get('12');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: body12
      });
    }
    await route.continue();
  });

  let releaseTen;
  gates.set('10', new Promise((resolve) => (releaseTen = resolve)));
  let releaseTwelve;
  gates.set('12', new Promise((resolve) => (releaseTwelve = resolve)));

  const waitTen = page.waitForRequest((r) => r.url().includes('threshold=10'));
  await page.getByTestId('input-threshold').fill('10');
  await waitTen;
  const waitTwelve = page.waitForRequest((r) => r.url().includes('threshold=12'));
  await page.getByTestId('input-threshold').fill('12');
  await waitTwelve;

  // The newest request succeeds first.
  releaseTwelve();
  await expect(page.getByText('P(总分 ≥ 12)')).toBeVisible();
  const newestTail = await page.getByTestId('tail-probability').textContent();

  // The older request then fails; its late error must not replace the page.
  releaseTen();
  await page.waitForTimeout(200);
  await expect(page.getByTestId('error')).toHaveCount(0);
  expect(await page.getByTestId('tail-probability').textContent()).toBe(newestTail);
});

