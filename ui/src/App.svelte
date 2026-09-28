<script>
// Editable rule.  Ranges are enforced by the inputs and re-checked server-side.
let nDice = 3;
let faces = 6;
let keep = 2;
let reroll = new Set([1]);
let threshold = 9;

let result = null;
let error = null;
let loading = false;
let requestSeq = 0;

// Plain helper instead of object literals inside reactive statements —
// the Svelte 4 parser misreads a leading brace in that context.
function makeRange(from, to) {
  const out = [];
  for (let i = from; i <= to; i++) out.push(i);
  return out;
}

$: facesOptions = makeRange(2, 8);
$: faceOptions = makeRange(1, faces);
$: maxTotal = keep * 2 * faces;
$: minTotal = keep;

// Clamp dependents whenever a rule changes.
$: if (keep > nDice) keep = nDice;
$: {
  // Only reassign when a face actually fell out of range, otherwise the
  // reactive statement would loop (every new Set is a new identity).
  const valid = new Set(faceOptions);
  const filtered = [...reroll].filter((f) => valid.has(f));
  if (filtered.length !== reroll.size) reroll = new Set(filtered);
}
$: if (threshold > maxTotal) threshold = maxTotal;
$: if (threshold < minTotal) threshold = minTotal;

function toggleFace(face) {
  const next = new Set(reroll);
  if (next.has(face)) next.delete(face);
  else next.add(face);
  reroll = next;
}

async function load() {
  const seq = ++requestSeq;
  loading = true;
  error = null;
  const params = new URLSearchParams();
  params.set('n_dice', nDice);
  params.set('faces', faces);
  params.set('keep', keep);
  params.set('threshold', threshold);
  for (const face of [...reroll].sort((a, b) => a - b)) {
    params.append('reroll', face);
  }
  try {
    const response = await fetch(`/api/distribution?${params}`);
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    // Ignore stale responses: only the latest request may update the page.
    if (seq !== requestSeq) return;
    result = body;
  } catch (err) {
    // Likewise, an error from a superseded request must not overwrite the
    // current page state.
    if (seq !== requestSeq) return;
    result = null;
    error = err.message;
  } finally {
    if (seq === requestSeq) loading = false;
  }
}

// Re-query whenever the rule changes.  The dependencies MUST be listed in
// the same reactive statement as the call — a separate `$: a, b;` line is
// just an expression list and does NOT make the following `$: load()`
// reactive to them.  The exact fractions keep the chart stable across
// refreshes — no Monte Carlo tail noise.
$: nDice, faces, keep, reroll, threshold, load();

$: rows = result ? result.distribution : [];
$: maxProbability = rows.reduce((m, r) => Math.max(m, r.decimal), 0);
$: decimalSum = rows.reduce((s, r) => s + r.decimal, 0);

function percent(x) {
  return (x * 100).toFixed(2);
}
</script>

<main class="page">
  <header>
    <h1>重掷 · 追加骰 · 保留最高颗</h1>
    <p class="subtitle">
      每颗骰先掷一次，命中重掷集合则恰好重掷一次；最终面为最大面时追加一颗同面骰相加
      （追加骰不重掷、不再追加）。从所有最终点数中保留最高 K 颗求和 —— 服务端返回
      <strong>约分分数</strong>的精确分布，概率总和恒为 1。
    </p>
  </header>

  <section class="panel controls" aria-label="规则编辑">
    <label class="field">
      <span>原骰数（1～6）</span>
      <input
        data-testid="input-n-dice"
        type="number"
        min="1"
        max="6"
        bind:value={nDice}
      />
    </label>

    <label class="field">
      <span>面数（2～8）</span>
      <select data-testid="input-faces" bind:value={faces}>
        {#each facesOptions as f}
          <option value={f}>{f} 面骰</option>
        {/each}
      </select>
    </label>

    <label class="field">
      <span>保留颗数 K（1～{nDice}）</span>
      <input
        data-testid="input-keep"
        type="range"
        min="1"
        max={nDice}
        step="1"
        bind:value={keep}
      />
      <strong data-testid="keep-value" class="keep-value">K = {keep}</strong>
    </label>

    <fieldset class="field reroll-field">
      <legend>重掷面集合（命中则恰好重掷一次）</legend>
      <div class="chips">
        {#each faceOptions as face}
          <button
            type="button"
            data-testid="reroll-chip"
            data-face={face}
            class="chip"
            class:on={reroll.has(face)}
            aria-pressed={reroll.has(face)}
            on:click={() => toggleFace(face)}
          >
            {face}
          </button>
        {/each}
      </div>
    </fieldset>

    <label class="field">
      <span>阈值 T：求 P(总分 ≥ T)</span>
      <input
        data-testid="input-threshold"
        type="number"
        min={minTotal}
        max={maxTotal}
        bind:value={threshold}
      />
    </label>
  </section>

  {#if error}
    <section class="panel error" data-testid="error" role="alert">
      请求失败：{error}
    </section>
  {/if}

  {#if loading && !result}
    <section class="panel">计算中…</section>
  {/if}

  {#if result}
    <section class="panel summary" data-testid="summary">
      <div class="summary-item">
        <span class="label">期望总分</span>
        <span class="fraction" data-testid="expected-score">
          {result.expected_score}
        </span>
        <span class="decimal">≈ {result.expected_score_decimal.toFixed(6)}</span>
      </div>
      <div class="summary-item">
        <span class="label">P(总分 ≥ {result.params.threshold})</span>
        <span class="fraction tail" data-testid="tail-probability">
          {result.probability_at_least}
        </span>
        <span class="decimal">≈ {percent(result.probability_at_least_decimal)}%</span>
      </div>
      <div class="summary-item">
        <span class="label">概率总和（精确）</span>
        <span class="fraction" data-testid="total-probability">
          {result.total_probability}
        </span>
        <span class="decimal" data-testid="decimal-sum"
          >浮点求和 ≈ {decimalSum.toFixed(12)}</span
        >
      </div>
    </section>

    <section class="panel chart" aria-label="总分概率柱图">
      <h2>总分概率分布（悬停查看约分分数）</h2>
      <div class="bars" data-testid="chart">
        {#each rows as row (row.score)}
          {@const widthPct = maxProbability === 0 ? 0 : (row.decimal / maxProbability) * 100}
          <div class="bar-row" data-testid="bar-row" data-score={row.score}>
            <span class="bar-score">{row.score}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                class:zero={row.decimal === 0}
                style="width: {widthPct}%"
                title="总分 {row.score}：P = {row.probability}（≈ {percent(row.decimal)}%）"
              ></div>
            </div>
            <span class="bar-fraction" data-testid="bar-fraction">{row.probability}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background: #f4f5f7;
    color: #1f2430;
  }
  .page {
    max-width: 880px;
    margin: 0 auto;
    padding: 24px 16px 64px;
  }
  h1 {
    font-size: 1.5rem;
    margin: 0 0 8px;
  }
  .subtitle {
    color: #55606e;
    font-size: 0.9rem;
    line-height: 1.6;
  }
  .panel {
    background: #fff;
    border: 1px solid #e2e5ea;
    border-radius: 10px;
    padding: 16px 20px;
    margin-top: 16px;
  }
  .controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.85rem;
    color: #444d5c;
  }
  .field input[type='number'],
  .field select {
    padding: 6px 8px;
    border: 1px solid #c6cbd4;
    border-radius: 6px;
    font-size: 1rem;
  }
  .keep-value {
    font-size: 0.95rem;
  }
  .reroll-field {
    border: none;
    padding: 0;
    margin: 0;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    width: 38px;
    height: 34px;
    border-radius: 8px;
    border: 1px solid #b9c0cc;
    background: #f7f8fa;
    cursor: pointer;
    font-size: 0.95rem;
  }
  .chip.on {
    background: #2f6fed;
    border-color: #2f6fed;
    color: #fff;
    font-weight: 700;
  }
  .summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
  }
  .summary-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .summary-item .label {
    font-size: 0.8rem;
    color: #748094;
  }
  .fraction {
    font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
    font-size: 1.25rem;
    font-weight: 700;
  }
  .fraction.tail {
    color: #1d7a46;
  }
  .decimal {
    font-size: 0.78rem;
    color: #8a93a2;
  }
  .error {
    background: #fdecec;
    border-color: #f0b4b4;
    color: #9b1c1c;
  }
  h2 {
    font-size: 1rem;
    margin: 0 0 12px;
  }
  .bars {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: 44px 1fr 120px;
    align-items: center;
    gap: 8px;
    font-size: 0.78rem;
  }
  .bar-score {
    text-align: right;
    color: #55606e;
    font-variant-numeric: tabular-nums;
  }
  .bar-track {
    background: #eef0f3;
    border-radius: 4px;
    height: 18px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #3f7df1, #2f6fed);
    border-radius: 4px;
    min-width: 1px;
    transition: width 0.18s ease;
  }
  .bar-fill.zero {
    background: transparent;
    min-width: 0;
  }
  .bar-fraction {
    font-family: ui-monospace, Menlo, monospace;
    color: #444d5c;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
</style>
