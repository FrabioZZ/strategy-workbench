const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright-core');

test('shared chart controls preserve execution and the paper session refreshes', { timeout: 25000 }, async () => {
  const executablePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(7000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const portfolio = { id: 'combo', name: 'Momentum', revision: 2, readiness: { ready: true, errors: [], warnings: [] }, items: [{ enabled: true, timeframe: '5m' }] };
    const stamp = minute => `${new Date(Date.UTC(2026, 0, 5, 9, minute)).toISOString().slice(0, 19)}+08:00`;
    const bars = Array.from({ length: 100 }, (_, i) => ({
      date: stamp(35 + i * 5), execution_time: stamp(30 + i * 5),
      open: 12 + Math.sin(i / 10), close: 12 + Math.sin(i / 9), high: 13, low: 10.5, volume: 100000 + i * 500,
    }));
    const event = { signal_date: bars[97].date, date: bars[98].execution_time, side: 'buy', quantity: 300 };
    const run = {
      id: 'backtest-1', symbol: '600519.SH', timeframe: '5m', portfolio_snapshot: portfolio, portfolio_revision: 2,
      initial_cash: 100000, cash: 50309, metrics: { total_return_pct: 2.3, max_drawdown_pct: 1.4 },
      equity: [{ date: bars.at(-1).date, equity: 102300 }], bars, price_basis: 'raw',
      signals: [{ date: event.signal_date, target_pct: 50, conflict: false, reasons: ['MA strategy reason'], components: [] }],
      orders: [{ ...event, id: 'buy-1', status: 'filled' }],
      fills: [{ ...event, order_id: 'buy-1', price: 11.5, fee: 5 }],
      positions: [],
      indicator_series: [
        { name: 'MA', params: { period: 5 }, values: bars.map(bar => bar.close), used: true },
        { name: 'RSI', params: { period: 14 }, values: bars.map((_, i) => 50 + Math.sin(i / 3) * 20), used: false },
      ],
    };
    const frontend = path.join(__dirname, '..', 'frontend');
    const backtests = '/api/trading/workstation/backtests', paperSessions = '/api/trading/workstation/paper/sessions';
    let submitted, writes = 0, paperStatus = 'running';
    await page.route('http://127.0.0.1/**', route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      if (pathname === '/') return route.fulfill({
        path: path.join(frontend, 'index.html'), headers: { 'content-security-policy': "style-src 'self'" },
      });
      if (pathname.startsWith('/static/')) return route.fulfill({ path: path.join(frontend, path.basename(pathname)) });
      if (pathname === '/api/trading/portfolios') return route.fulfill({ json: [portfolio] });
      if (pathname === '/api/trading/capabilities') {
        return route.fulfill({ json: { broker: { label: 'fixture' }, feeds: {}, limitations: [], indicators: [], rule_types: ['conditional'] } });
      }
      if (request.method() === 'POST' && (pathname === backtests || pathname === paperSessions)) {
        submitted = request.postDataJSON();
        writes++;
        if (pathname === backtests) return route.fulfill({ json: { ...run, status: 'completed' } });
      }
      if (pathname === `${paperSessions}/session-1/pause`) paperStatus = 'paused';
      if (pathname === `${paperSessions}/session-1/start`) paperStatus = 'running';
      if (pathname.startsWith(`${paperSessions}/`) || (pathname === paperSessions && request.method() === 'POST')) {
        return route.fulfill({ json: { ...run, id: 'session-1', status: paperStatus, feed_status: 'fresh' } });
      }
      return route.fulfill({ json: [] });
    });

    async function runForm(mode, end) {
      const root = page.locator(`#market-${mode}`);
      await root.locator('[name="portfolio"]').selectOption('combo');
      await root.locator('[name="symbol"]').fill('600519');
      await root.locator('[name="start"]').fill('2026-01-05');
      if (end) await root.locator('[name="end"]').fill(end);
      await root.locator('form button').click();
      await root.locator('canvas').waitFor();
      return root;
    }

    await page.goto('http://127.0.0.1/#backtest');
    const backtest = await runForm('backtest', '2026-01-06');
    assert.deepEqual(submitted, {
      portfolio_id: 'combo', portfolio_revision: 2, symbol: '600519.SH',
      start_date: '2026-01-05', end_date: '2026-01-06', initial_cash: 100000,
    });
    const canvas = backtest.locator('canvas');
    await page.waitForFunction(() => document.querySelector('#market-backtest canvas').height > 300);
    const previousHeight = await canvas.evaluate(el => el.height);
    await backtest.locator('.market-indicators summary').click();
    await backtest.getByRole('checkbox', { name: /RSI/ }).check();
    await page.waitForFunction(height => document.querySelector('#market-backtest canvas').height > height, previousHeight);
    const swatches = await backtest.locator('.market-indicator i').evaluateAll(elements =>
      elements.map(element => getComputedStyle(element).backgroundColor));
    const readoutColors = await backtest.locator('.market-readout-series').evaluateAll(elements =>
      elements.map(element => getComputedStyle(element).color));
    assert.deepEqual(swatches, ['oklch(0.53 0.16 253)', 'oklch(0.57 0.15 54)']);
    assert.deepEqual(readoutColors, swatches);
    assert.equal(writes, 1);
    await canvas.press('ArrowLeft');
    assert.match(await backtest.locator('.market-readout').innerText(), /2026-01-05/);
    assert.match(await backtest.locator('.market-trades').innerText(), /MA strategy reason/);
    await backtest.locator('[data-older]').click();
    await backtest.locator('[data-latest]:enabled').waitFor();
    assert.equal(await page.locator('#backtest-form').isVisible(), false);

    await page.setViewportSize({ width: 390, height: 800 });
    await canvas.scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await page.locator('a[data-workspace=paper]').click();
    const paper = await runForm('paper');
    assert.equal(submitted.end_date, null);
    assert.equal(await page.locator('#pex-panel').isVisible(), false);
    await paper.locator('[data-command=pause]').click();
    const poll = page.waitForResponse(response => new URL(response.url()).pathname === `${paperSessions}/session-1`, { timeout: 8000 });
    await paper.locator('[data-command=start]').click();
    await poll;
    assert.equal(paperStatus, 'running');

    await page.locator('a[data-workspace=portfolio]').click();
    await page.locator('#add-manual').click();
    const item = page.locator('.portfolio-item');
    await item.locator('[data-field=rule-type]').selectOption('conditional');
    assert.equal(await item.locator('[data-field=conditional-preset] option[value=first_limit]').count(), 1);
    await item.locator('[data-field=timeframe]').selectOption('5m');
    assert.equal(await item.locator('[data-field=conditional-preset] option[value=first_limit]').count(), 0);
    assert.match(await item.locator('.conditional-editor').innerText(), /RSI\(14\).*5 分钟 K 线/);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
});

test('the daily demo submits independent backtest and replay windows and shows the replay clock', { timeout: 25000 }, async () => {
  const executablePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 800 } });
    page.setDefaultTimeout(7000);
    const frontend = path.join(__dirname, '..', 'frontend');
    const demo = {
      symbol: '600000.SH', start_date: '2024-01-01', end_date: '2026-11-01',
      market_source: '沪深300复权研究日线',
      replay: { start_date: '2024-01-01', end_date: '2026-01-01', market_source: '沪深300未复权日线' },
    };
    const portfolio = { id: 'combo', name: '均线', revision: 1, readiness: { ready: true, errors: [], warnings: [] }, items: [{ enabled: true, timeframe: 'daily' }] };
    const run = {
      id: 'result', timeframe: 'daily', portfolio_snapshot: portfolio, portfolio_revision: 1,
      quantity_unit: 'synthetic_unit', initial_cash: 100000, cash: 100000,
      orders: [], fills: [], positions: [], signals: [], equity: [], bars: [],
    };
    const backtests = '/api/trading/workstation/backtests';
    const paperSessions = '/api/trading/workstation/paper/sessions';
    const submissions = [];
    let oldRuntime = false, replayRun;
    await page.route('http://127.0.0.1/**', route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      if (pathname === '/') return route.fulfill({ path: path.join(frontend, 'index.html') });
      if (pathname === '/runtime-mode.js') {
        const config = oldRuntime ? { symbol: '600000.SH', start_date: '2025-11-03', end_date: '2025-11-28', market_source: 'Phase 11 合成样本日线' } : demo;
        return route.fulfill({
          contentType: 'application/javascript',
          body: `window.dailyDemo = ${JSON.stringify(config)}; document.documentElement.dataset.dailyDemo = 'true';`,
        });
      }
      if (pathname.startsWith('/static/')) return route.fulfill({ path: path.join(frontend, path.basename(pathname)) });
      if (pathname === '/api/trading/portfolios') return route.fulfill({ json: [portfolio] });
      if (pathname === '/api/trading/capabilities') return route.fulfill({ json: { broker: { label: 'fixture' }, feeds: {}, limitations: [] } });
      if (request.method() === 'POST' && (pathname === backtests || pathname === paperSessions)) {
        const input = request.postDataJSON();
        submissions.push(input);
        if (pathname === backtests) return route.fulfill({ json: { ...run, ...input,
          status: 'completed', price_basis: 'forward_adjusted', execution_model: 'adjusted_research', data_source: demo.market_source,
        } });
        replayRun = { ...run, ...input,
          status: 'running', price_basis: 'raw', execution_model: 'raw_replay', data_source: demo.replay.market_source,
          mode: 'market_replay', simulated_at: '2024-11-11T14:52:00+08:00', feed_status: 'waiting',
        };
        return route.fulfill({ json: replayRun });
      }
      if (pathname === `${paperSessions}/result`) return route.fulfill({ json: replayRun });
      return route.fulfill({ json: [] });
    });
    await page.goto('http://127.0.0.1/#backtest');
    assert.match(await page.locator('#daily-demo-banner').innerText(), /沪深300真实日线/);
    const backtest = page.locator('#market-backtest');
    await backtest.locator('[name=portfolio]').selectOption('combo');
    assert.equal(await backtest.locator('[name=symbol]').inputValue(), '600000.SH');
    await backtest.locator('[name=symbol]').fill('600519');
    await backtest.getByRole('button', { name: '运行回测' }).click();
    await backtest.locator('.market-result').waitFor();
    assert.deepEqual(submissions[0], {
      portfolio_id: 'combo', portfolio_revision: 1, symbol: '600519.SH',
      start_date: '2024-01-01', end_date: '2026-11-01', initial_cash: 100000,
    });
    assert.match(await backtest.locator('.market-result-meta').innerText(), /前复权研究.*研究份额/);

    await page.locator('a[data-workspace=paper]').click();
    const paper = page.locator('#market-paper');
    await paper.locator('[name=portfolio]').selectOption('combo');
    assert.equal(await paper.locator('[name=end]').inputValue(), '');
    assert.equal(await paper.locator('[name=end]').getAttribute('max'), '2026-01-01');
    assert.match(await paper.locator('.market-setup-note').innerText(), /减去两年.*已收盘/);
    await paper.getByRole('button', { name: '启动模拟' }).click();
    await paper.locator('.market-result').waitFor();
    assert.equal(submissions[1].start_date, '2024-01-01');
    assert.equal(submissions[1].end_date, null);
    assert.match(await paper.locator('.market-result-meta').innerText(), /历史行情回放.*未复权.*模拟份额/);
    assert.match(await paper.locator('.market-replay-time').innerText(), /模拟交易时间.*2024-11-11 14:52:00.*北京时间/);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);

    replayRun = { ...replayRun, simulated_at: '2024-11-11T15:00:00+08:00', feed_status: 'fresh',
      bars: [{ date: '2024-11-11', open: 12.1, high: 12.4, low: 12, close: 12.3, volume: 9000 }] };
    await paper.getByRole('button', { name: '刷新状态' }).click();
    await paper.getByText('最新可见 K 线 2024-11-11', { exact: true }).waitFor();
    assert.match(await paper.locator('.market-replay-time').innerText(), /2024-11-11 15:00:00/);

    oldRuntime = true;
    await page.reload();
    assert.match(await page.locator('#daily-demo-banner').innerText(), /合成样本行情/);
    assert.equal(await paper.locator('[name=end]').inputValue(), '2025-11-28');
    assert.equal(await paper.locator('[name=end]').getAttribute('required'), '');
  } finally {
    await browser.close();
  }
});
