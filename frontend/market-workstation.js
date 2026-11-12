'use strict';
(() => {
  const priceFormat = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
  const compactFormat = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 });
  const cashFormat = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' });
  const chinaTime = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const number = value => finite(value) ? priceFormat.format(value) : '—';
  const cash = value => finite(value) ? cashFormat.format(value) : '—';
  const percent = value => finite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '—';
  const interval = value => value === '5m' ? '5 分钟线' : '日线';
  const statusLabels = { running: '运行中', paused: '已暂停', completed: '已结束' };
  const feedLabels = { waiting: '等待行情', fresh: '行情可用', error: '行情异常', exhausted: '区间结束', paused: '已暂停', stale: '行情已过期' };
  const quoteLabels = { fresh: '实时', break_latest: '休市前最新报价', closed_latest: '收盘报价', stale: '报价已过期', unavailable: '报价不可用', invalid: '报价异常' };
  const seriesColorCount = 6;
  const rise = 'oklch(.51 .19 26)', fall = 'oklch(.44 .13 153)';
  const overlays = new Set(['MA', 'EMA', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'PREV_CLOSE', 'LIMIT_UP', 'LIMIT_DOWN']);
  const indicatorsByPrice = series => (overlays.has(series.name) && series.params?.field !== 'volume') || series.name.startsWith('BOLL_');
  const indicatorKey = series => JSON.stringify([series.name, Object.entries(series.params || {}).sort()]);
  const indicatorFamily = ({ name, params }) => name.startsWith('MACD_') || name.startsWith('KDJ_')
    ? JSON.stringify([name.split('_')[0], Object.entries(params || {}).sort()]) : indicatorKey({ name, params });
  const indicatorLabel = ({ name, params }) => {
    const values = Object.entries(params || {}).filter(([key, value]) => key !== 'field' || value !== 'close').map(([, value]) => value);
    return values.length ? `${name} (${values.join(', ')})` : name;
  };

  function time(value) {
    const raw = String(value || '');
    if (!/[T ].*(?:Z|[+-]\d\d:\d\d)$/.test(raw)) return raw.replace('T', ' ');
    const date = new Date(raw);
    const fraction = raw.match(/\.\d+(?=Z|[+-]\d\d:\d\d$)/)?.[0] || '';
    return Number.isNaN(date.valueOf()) ? raw : chinaTime.format(date) + fraction;
  }

  function normalizeSymbol(value) {
    const code = value.trim().toUpperCase();
    const prefix = /^(SH|SZ)(\d{6})$/.exec(code);
    if (prefix) return `${prefix[2]}.${prefix[1]}`;
    if (/^6\d{5}$/.test(code)) return `${code}.SH`;
    if (/^[03]\d{5}$/.test(code)) return `${code}.SZ`;
    return code;
  }

  function table(title, headings, rows) {
    if (!rows.length) return '<p class="market-muted">暂无记录。</p>';
    return `<div class="table-wrap" tabindex="0" role="region" aria-label="${title}"><table class="ledger-table"><thead><tr>
      ${headings.map(label => `<th scope="col">${label}</th>`).join('')}
      </tr></thead><tbody>${rows.map(row => `<tr>${row.map((value, index) => `<td${index === row.length - 1 ? ' class="reason-cell"' : ''}>${esc(value ?? '—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function trades(run) {
    const fills = new Map((run.fills || []).map(fill => [fill.order_id, fill]));
    const orders = run.orders || [];
    const orderIds = new Set(orders.map(order => order.id));
    const signalReasons = new Map((run.signals || []).map(signal => [
      time(signal.date),
      [...new Set([...(signal.reasons || []), ...(signal.components || []).map(part => part.reason && `${part.name}：${part.reason}`)].filter(Boolean))].join(' / '),
    ]));
    const events = orders.map(order => ({ order, fill: fills.get(order.id) }));
    for (const fill of run.fills || []) {
      if (!orderIds.has(fill.order_id)) events.push({ order: fill, fill });
    }
    return events.map(({ order, fill }) => ({
      side: order.side, signal: time(order.signal_date || fill?.signal_date), filled: time(fill?.date),
      price: fill?.price, quantity: fill?.quantity ?? order.quantity, fee: fill?.fee,
      status: fill ? '已成交' : ({ pending: '待撮合', blocked: '未成交', rejected: '已拒绝', cancelled: '已取消' })[order.status] || '未成交',
      reason: [...new Set([signalReasons.get(time(order.signal_date || fill?.signal_date)), order.reason, fill?.reason].filter(Boolean))].join(' / '),
    }));
  }

  function chart(root) {
    const q = selector => root.querySelector(selector);
    const canvas = q('canvas'), readout = q('.market-readout'), choices = q('.market-indicator-options');
    const earlier = q('[data-older]'), newer = q('[data-newer]'), latest = q('[data-latest]'), count = q('[data-bars]');
    const ctx = canvas.getContext('2d');
    let runId, signature, viewStart = null, activeIndex = null, span = 90;
    let bars = [], series = [], marks = new Map(), enabled = new Set();
    let frame = 0, plot = null;

    function setRun(run, events) {
      const reset = run.id !== runId;
      runId = run.id;
      bars = run.bars || [];
      series = (run.indicator_series || []).map((item, index) => ({
        ...item, key: indicatorKey(item), colorSlot: (index % seriesColorCount) + 1,
      }));
      const identity = JSON.stringify(series.map(item => [item.key, item.label, item.used]));
      if (reset) {
        enabled = new Set(series.filter(item => item.used).map(item => item.key));
        viewStart = activeIndex = null;
      } else {
        for (const item of series) {
          if (!choices.querySelector(`[value="${CSS.escape(item.key)}"]`) && item.used) enabled.add(item.key);
        }
      }
      if (reset || identity !== signature) {
        choices.innerHTML = series.length ? series.map(item => `<label class="market-indicator">
          <input type="checkbox" value="${esc(item.key)}" ${enabled.has(item.key) ? 'checked' : ''}>
          <i class="market-series-${item.colorSlot}" aria-hidden="true"></i>
          <span>${esc(indicatorLabel(item))}<small>${esc(item.label || '')}${item.used ? ' · 策略使用' : ''}</small></span>
          </label>`).join('') : '<p class="market-muted">当前记录没有指标值。</p>';
        signature = identity;
      }
      const barTimes = new Map(), openTimes = new Map();
      bars.forEach((bar, index) => {
        barTimes.set(time(bar.date), index);
        if (bar.execution_time) openTimes.set(time(bar.execution_time), index);
      });
      marks = new Map();
      function mark(index, event, filled) {
        if (index == null || !['buy', 'sell'].includes(event.side)) return;
        if (!marks.has(index)) marks.set(index, new Map());
        const row = marks.get(index);
        row.set(event.side, Boolean(row.get(event.side) || filled));
      }
      const coveredTimes = bars.map(bar => time(bar.date));
      function containingBar(timestamp) {
        if (!timestamp || run.timeframe !== '5m') return undefined;
        const marketTime = value => Date.parse(value.replace(' ', 'T') + (value.length === 16 ? ':00' : '') + '+08:00');
        const minute = marketTime(timestamp);
        if (!finite(minute)) return undefined;
        let low = 0, high = coveredTimes.length;
        while (low < high) {
          const middle = (low + high) >>> 1;
          if (coveredTimes[middle] < timestamp) low = middle + 1;
          else high = middle;
        }
        const bar = bars[low];
        if (!bar) return undefined;
        const close = marketTime(time(bar.date));
        const open = bar.execution_time ? marketTime(time(bar.execution_time)) : close - 5 * 60 * 1000;
        return minute >= open && minute <= close ? low : undefined;
      }
      for (const event of events) {
        mark(barTimes.get(event.signal), event, false);
        const dailyBar = run.timeframe === '5m' ? undefined : barTimes.get(event.filled.slice(0, 10));
        mark(openTimes.get(event.filled) ?? barTimes.get(event.filled) ?? dailyBar ?? containingBar(event.filled), event, true);
      }
      q('.market-chart-empty').hidden = Boolean(bars.length);
      canvas.hidden = !bars.length;
      q('.market-chart-nav').hidden = !bars.length;
      readout.hidden = !bars.length;
      scheduleDraw();
    }

    function scheduleDraw() {
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; draw(); });
    }

    function updateReadout(index, selected) {
      const bar = bars[index];
      if (!bar) return;
      const fields = [['开', number(bar.open)], ['高', number(bar.high)], ['低', number(bar.low)], ['收', number(bar.close)], ['量', finite(bar.volume) ? compactFormat.format(bar.volume) : '—']];
      const markup = `<strong>${esc(time(bar.date))}</strong>` +
        fields.map(([name, value]) => `<span>${name} <b>${value}</b></span>`).join('') +
        selected.filter(item => finite(item.values?.[index])).map(item => `<span class="market-readout-series market-series-${item.colorSlot}">${esc(indicatorLabel(item))} <b>${number(item.values[index])}</b></span>`).join('');
      if (readout.innerHTML !== markup) readout.innerHTML = markup;
    }

    function draw() {
      if (!bars.length || !ctx) return;
      const width = root.clientWidth;
      if (width < 80) return;
      const selected = series.filter(item => enabled.has(item.key));
      const lines = selected.filter(indicatorsByPrice), panels = new Map();
      for (const item of selected.filter(item => !indicatorsByPrice(item) && item.name !== 'VOLUME')) {
        const key = indicatorFamily(item);
        if (!panels.has(key)) panels.set(key, []);
        panels.get(key).push(item);
      }
      const volumeLine = selected.filter(item => item.name === 'VOLUME');
      const style = getComputedStyle(root);
      const ink = style.getPropertyValue('--muted').trim(), grid = style.getPropertyValue('--line').trim();
      const main = width < 480 ? 214 : 310, volume = 58, subplot = 82, top = 16, left = 9;
      const height = top + main + volume + panels.size * subplot + 24;
      const right = width - 57, dpr = window.devicePixelRatio || 1;
      canvas.style.height = `${height}px`;
      if (canvas.width !== Math.round(width * dpr)) canvas.width = Math.round(width * dpr);
      if (canvas.height !== Math.round(height * dpr)) canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.font = '11px system-ui, sans-serif';
      ctx.textBaseline = 'middle';
      const lastStart = Math.max(0, bars.length - span);
      const start = Math.min(viewStart ?? lastStart, lastStart), end = Math.min(bars.length, start + span);
      const visible = bars.slice(start, end), step = (right - left) / visible.length;
      const x = i => left + (i - start + .5) * step;
      plot = { start, end, left, right, step };
      earlier.disabled = start === 0;
      latest.disabled = newer.disabled = end === bars.length;
      updateReadout(activeIndex ?? end - 1, selected);

      function stroke(x1, y1, x2, y2, color) {
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      function text(value, xPos, yPos, color = ink, align = 'left') {
        ctx.fillStyle = color;
        ctx.textAlign = align;
        ctx.fillText(value, xPos, yPos);
      }
      function axis(low, high, yTop, yBottom, divisions, format) {
        const y = v => yBottom - (v - low) / (high - low) * (yBottom - yTop);
        for (let i = 0; i <= divisions; i++) {
          const p = yTop + (yBottom - yTop) * i / divisions;
          stroke(left, p, right, p, grid);
          text(format(high - (high - low) * i / divisions), right + 5, p);
        }
        return y;
      }
      function extents(values, padding) {
        if (!values.length) return [0, 1];
        const low = Math.min(...values), high = Math.max(...values);
        const pad = (high - low || Math.abs(high) * .015 || 1) * padding;
        return [low - pad, high + pad];
      }
      function seriesValues(items) {
        return items.flatMap(item => (item.values || []).slice(start, end).filter(finite));
      }
      function plotLines(items, y) {
        for (const item of items) {
          ctx.strokeStyle = ctx.fillStyle = style.getPropertyValue(`--market-series-${item.colorSlot}`).trim();
          ctx.beginPath();
          let connected = false;
          for (let i = start; i < end; i++) {
            const value = item.values?.[i];
            if (!finite(value)) { connected = false; continue; }
            if (item.name === 'MACD_HIST') {
              ctx.fillRect(x(i) - step * .22, Math.min(y(value), y(0)), Math.max(1, step * .44), Math.max(1, Math.abs(y(value) - y(0))));
            } else if (connected) {
              ctx.lineTo(x(i), y(value));
            } else {
              ctx.moveTo(x(i), y(value));
              ctx.fillRect(x(i) - .5, y(value) - .5, 1, 1);
            }
            connected = true;
          }
          ctx.stroke();
        }
      }

      const prices = visible.flatMap(bar => [bar.low, bar.high]).filter(finite);
      const y = axis(...extents(prices.concat(seriesValues(lines)), .11), top, top + main - 4, 4, number);
      const maxVolume = Math.max(1, ...visible.map(bar => finite(bar.volume) ? bar.volume : 0));
      const volumeY = axis(0, maxVolume, top + main + 12, top + main + volume, 1, value => compactFormat.format(value));
      const body = Math.max(1, Math.min(12, step * .62));
      visible.forEach((bar, i) => {
        const index = start + i, pos = x(index), color = bar.close < bar.open ? fall : rise;
        if ([bar.open, bar.close, bar.low, bar.high].every(finite)) {
          stroke(pos, y(bar.low), pos, y(bar.high), color);
          ctx.fillStyle = color;
          ctx.fillRect(pos - body / 2, Math.min(y(bar.open), y(bar.close)), body, Math.max(1, Math.abs(y(bar.open) - y(bar.close))));
        }
        if (finite(bar.volume)) {
          ctx.fillStyle = color;
          ctx.globalAlpha = .55;
          ctx.fillRect(pos - body / 2, volumeY(bar.volume), body, volumeY(0) - volumeY(bar.volume));
          ctx.globalAlpha = 1;
        }
      });
      plotLines(lines, y);
      plotLines(volumeLine, volumeY);
      visible.forEach((bar, i) => {
        const index = start + i;
        for (const [side, filled] of marks.get(index) || []) {
          const buy = side === 'buy', pos = x(index), at = buy ? y(bar.low) + 9 : y(bar.high) - 9;
          const color = buy ? rise : fall;
          if (!finite(at)) continue;
          if (filled) {
            ctx.fillStyle = color;
            ctx.fillRect(pos - 7, at - 7, 14, 14);
          } else {
            ctx.fillStyle = 'oklch(1 0 0)';
            ctx.fillRect(pos - 7, at - 7, 14, 14);
            ctx.strokeStyle = color;
            ctx.strokeRect(pos - 7, at - 7, 14, 14);
          }
          text(buy ? 'B' : 'S', pos, at, filled ? 'oklch(1 0 0)' : color, 'center');
        }
      });
      text('成交量', left + 3, top + main + 5);
      let sectionTop = top + main + volume;
      for (const items of panels.values()) {
        const values = seriesValues(items);
        if (items.some(item => item.name === 'MACD_HIST')) values.push(0);
        const ySeries = axis(...extents(values, .08), sectionTop + 25, sectionTop + subplot, 1, value => compactFormat.format(value));
        text(items.map(indicatorLabel).join(' / '), left + 3, sectionTop + 12);
        plotLines(items, ySeries);
        sectionTop += subplot;
      }
      const axisLabels = width < 480 ? 2 : 4;
      const ticks = new Set(Array.from({ length: axisLabels }, (_, i) => start + Math.round((end - start - 1) * i / (axisLabels - 1))));
      for (const index of ticks) {
        const align = index === start ? 'left' : index === end - 1 ? 'right' : 'center';
        const label = time(bars[index].date);
        text(runTimeLabel(label, width), align === 'left' ? left : align === 'right' ? right : x(index), height - 11, ink, align);
      }
      if (activeIndex != null && activeIndex >= start && activeIndex < end) {
        ctx.setLineDash([4, 3]);
        stroke(x(activeIndex), top, x(activeIndex), height - 23, ink);
        ctx.setLineDash([]);
      }
    }

    function runTimeLabel(value, width) {
      return width < 480 && value.length > 10 ? value.slice(5, 16) : value.slice(0, 16);
    }

    function go(to) {
      viewStart = to;
      activeIndex = null;
      scheduleDraw();
    }
    earlier.addEventListener('click', () => go(Math.max(0, plot.start - Math.floor(span * .75))));
    newer.addEventListener('click', () => go(plot.start + Math.floor(span * .75)));
    latest.addEventListener('click', () => go(null));
    count.addEventListener('change', () => { span = Number(count.value); go(viewStart); });
    choices.addEventListener('change', event => {
      const box = event.target;
      if (box.type !== 'checkbox') return;
      if (box.checked) enabled.add(box.value);
      else enabled.delete(box.value);
      scheduleDraw();
    });
    canvas.addEventListener('pointermove', selectPointer);
    canvas.addEventListener('pointerdown', selectPointer);
    function selectPointer(event) {
      if (!plot || event.offsetX < plot.left || event.offsetX > plot.right) return;
      activeIndex = Math.min(plot.end - 1, plot.start + Math.floor((event.offsetX - plot.left) / plot.step));
      scheduleDraw();
    }
    canvas.addEventListener('pointerleave', () => { if (document.activeElement !== canvas) { activeIndex = null; scheduleDraw(); } });
    canvas.addEventListener('keydown', event => {
      if (!plot || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const prior = activeIndex ?? plot.end - 1;
      const next = { ArrowLeft: prior - 1, ArrowRight: prior + 1, Home: plot.start, End: plot.end - 1 }[event.key];
      activeIndex = Math.max(plot.start, Math.min(plot.end - 1, next));
      updateReadout(activeIndex, series.filter(item => enabled.has(item.key)));
      q('.market-chart-announcement').textContent = readout.textContent;
      scheduleDraw();
    });
    new ResizeObserver(scheduleDraw).observe(root);
    return { setRun, redraw: scheduleDraw };
  }

  function mountWorkspace(root, mode, request) {
    const isPaper = mode === 'paper';
    const demo = window.dailyDemo;
    const replay = isPaper && demo?.replay;
    const dateRange = replay || demo;
    const endOptional = isPaper && (!demo || replay);
    const prefix = `market-${mode}`;
    const resource = isPaper ? '/workstation/paper/sessions' : '/workstation/backtests';
    const verb = isPaper ? '启动模拟' : '运行回测';
    root.classList.add('market-workspace');
    root.innerHTML = `
      <form class="market-setup">
        <div class="market-inputs">
          <label>已保存策略组合<select name="portfolio" required><option value="">选择组合</option></select></label>
          <label>股票代码<input name="symbol" type="text" placeholder="例如 600519.SH" maxlength="16" list="${prefix}-symbols" autocapitalize="characters" autocomplete="off" spellcheck="false" required></label>
          <datalist id="${prefix}-symbols"></datalist>
          <label>${replay ? '模拟' : ''}开始日期<input name="start" type="date" required></label>
          <label>${replay ? '模拟' : ''}结束日期${endOptional ? '（选填）' : ''}<input name="end" type="date" ${endOptional ? '' : 'required'}></label>
          <label>初始资金（元）<input name="cash" type="number" min="0.01" max="1000000000" step="0.01" value="100000" required></label>
        </div>
        <div class="market-submit">
          <button class="primary" type="submit" disabled>${verb}</button>
          <a href="#portfolio" class="market-portfolio-link" hidden>前往策略组合</a>
          <p class="market-setup-note">日期包含起止日${isPaper ? '。结束日期可留空，持续接收行情。' : '。'}</p>
        </div>
        <p class="market-progress" role="status"></p>
      </form>
      <div class="market-history">
        <label>${isPaper ? '模拟记录' : '回测记录'}<select aria-label="${isPaper ? '模拟记录' : '回测记录'}"><option value="">选择历史记录</option></select></label>
        <button type="button" class="secondary market-refresh">${isPaper ? '刷新状态' : '刷新记录'}</button>
      </div>
      <p class="market-history-note market-muted" role="status"></p>
      <section class="market-result" hidden aria-labelledby="${prefix}-heading">
        <header class="market-result-heading">
          <div><h2 id="${prefix}-heading" tabindex="-1"></h2><p class="market-result-meta"></p>
            ${isPaper ? '<p class="market-replay-time market-muted" hidden></p>' : ''}
          </div>
          ${isPaper ? '<div class="market-session-controls"><button type="button" class="secondary" data-command="pause">暂停</button><button type="button" class="primary" data-command="start">继续运行</button></div>' : ''}
        </header>
        <dl class="market-metrics"></dl>
        ${isPaper ? '<p class="market-session-status" role="status"></p><p class="market-command-status market-progress" role="status"></p>' : ''}
        <section class="market-chart" aria-label="行情图">
          <div class="market-chart-heading">
            <div><h3>K 线</h3><p class="market-quote market-muted"></p></div>
            <div class="market-chart-nav" hidden>
              <label><span class="market-visually-hidden">可见 K 线数量</span><select data-bars><option value="45">45 根</option><option value="90" selected>90 根</option><option value="180">180 根</option></select></label>
              <button type="button" class="secondary" data-older aria-label="前一段 K 线" title="前一段 K 线">‹</button>
              <button type="button" class="secondary" data-newer aria-label="后一段 K 线" title="后一段 K 线">›</button>
              <button type="button" class="secondary" data-latest>最新</button>
            </div>
          </div>
          <div class="market-readout" hidden></div>
          <div class="market-visually-hidden market-chart-announcement" role="status"></div>
          <canvas tabindex="0" aria-label="K 线与成交量图。使用左右方向键查看价格和成交量。" hidden></canvas>
          <p class="market-chart-empty market-muted">取得行情后显示 K 线和成交量。</p>
          <div class="market-chart-footer">
            <p class="market-legend">B 买入 · S 卖出 · 空心为信号 · 实心为成交</p>
            <details class="market-indicators"><summary>图表指标</summary><div class="market-indicator-options"></div></details>
          </div>
        </section>
        <details class="market-result-details" open><summary>买卖记录</summary><div class="market-trades"></div></details>
        <details class="market-result-details"><summary>策略信号</summary><div class="market-signals"></div></details>
        <details class="market-result-details"><summary>持仓与数据</summary><div class="market-details"></div></details>
      </section>`;
    const q = selector => root.querySelector(selector);
    const form = q('form'), fields = form.elements, submit = q('[type="submit"]');
    const result = q('.market-result'), chartView = chart(q('.market-chart'));
    const history = q('.market-history select'), refresh = q('.market-refresh'), progress = q('.market-progress');
    const historyNote = q('.market-history-note'), setupNote = q('.market-setup-note'), commands = [...root.querySelectorAll('[data-command]')];
    const signalsDetails = q('.market-signals').parentElement;
    const dateNote = dateRange ? `${dateRange.market_source} · ${dateRange.start_date} 至 ${dateRange.end_date}。` +
      (replay ? '模拟交易时间为北京时间减去两年，随时间推进。只显示模拟时间点已收盘的日线。结束日期可留空。' : '') : setupNote.textContent;
    if (dateRange) {
      fields.symbol.value = demo.symbol;
      fields.symbol.readOnly = !demo.replay;
      for (const field of [fields.start, fields.end]) {
        field.min = dateRange.start_date;
        field.max = dateRange.end_date;
      }
      fields.start.value = dateRange.start_date;
      if (!endOptional) fields.end.value = dateRange.end_date;
    }
    let portfolios = [], catalog = [], selected = null, active = false;
    let pollTimer, busy = false, readVersion = 0, historyVersion = 0, tradesHTML = '', signalsSource = null, renderedSignals = null;

    function setProgress(message, failed = false, element = progress) {
      element.textContent = message;
      element.classList.toggle('market-error', failed);
    }

    function updateForm() {
      const current = portfolios.find(portfolio => portfolio.id === fields.portfolio.value);
      const ready = Boolean(current?.readiness?.ready);
      submit.disabled = busy || !ready;
      q('.market-portfolio-link').hidden = ready;
      const timeframes = [...new Set((current?.items || []).filter(item => item.enabled).map(item => item.timeframe || 'daily'))];
      const periodLabel = timeframes.length === 1 ? `策略周期 · ${interval(timeframes[0])}。 ` : '';
      setupNote.textContent = current && !ready ? (current.readiness?.errors || []).join('；') || '请先确认策略组合。' :
        (portfolios.length ? periodLabel : '保存可运行的策略组合后即可开始。') +
          (portfolios.length || demo ? dateNote : '');
      history.disabled = busy;
      refresh.disabled = busy;
      commands.forEach(button => {
        button.hidden = selected?.status === 'completed' || (button.dataset.command === 'pause') !== (selected?.status === 'running');
        button.disabled = busy;
      });
    }

    function setCatalog(rows, datasets) {
      portfolios = rows;
      const current = fields.portfolio.value;
      fields.portfolio.innerHTML = '<option value="">选择组合</option>' + rows.map(item => `<option value="${esc(item.id)}">${esc(item.name)} · v${item.revision}${item.readiness?.ready ? '' : ' · 待确认'}</option>`).join('');
      fields.portfolio.value = rows.some(row => row.id === current) ? current : '';
      const symbols = new Map();
      for (const dataset of datasets) {
        if (dataset.is_demo) continue;
        const names = new Map((dataset.symbol_metadata || []).map(row => [row.symbol, row.name]));
        for (const symbol of dataset.symbols || []) {
          symbols.set(symbol, names.get(symbol) || symbols.get(symbol) || '');
        }
      }
      q('datalist').innerHTML = [...symbols].sort(([a], [b]) => a.localeCompare(b)).map(([symbol, name]) => `<option value="${esc(symbol)}" label="${esc(name)}"></option>`).join('');
      updateForm();
    }

    function showHistory() {
      const current = history.value;
      history.innerHTML = '<option value="">选择历史记录</option>' + catalog.map(run => {
        const created = time(run.created_at || run.requested_start_date || run.start_date);
        const label = [run.symbol, run.name || run.portfolio_snapshot?.name, interval(run.timeframe),
          run.mode === 'market_replay' && run.created_at ? `创建于 ${created}` : created,
          isPaper ? statusLabels[run.status] : null].filter(Boolean).join(' · ');
        return `<option value="${esc(run.id)}">${esc(label)}</option>`;
      }).join('');
      history.value = selected?.id || current;
    }

    async function loadHistory() {
      const version = ++historyVersion;
      try {
        const runs = await request(resource);
        if (version !== historyVersion) return;
        catalog = runs;
        if (selected && !catalog.some(run => run.id === selected.id)) catalog = [selected, ...catalog];
        showHistory();
        historyNote.textContent = '';
      } catch (error) {
        if (version === historyVersion) historyNote.textContent = error.message || '记录读取失败，请刷新重试。';
      }
    }

    function setStatus(run) {
      if (!isPaper) return;
      const clock = q('.market-replay-time');
      const simulated = time(run.simulated_at);
      clock.hidden = !simulated;
      clock.textContent = simulated ? `模拟交易时间 ${simulated}（北京时间）` : '';
      const status = [statusLabels[run.status], feedLabels[run.feed_status], run.message].filter(Boolean).join(' · ');
      const element = q('.market-session-status');
      if (element.textContent !== status) element.textContent = status;
    }

    function display(run) {
      selected = run;
      result.hidden = false;
      const quote = run.quote, latestBar = run.bars?.at(-1);
      const isReplay = run.mode === 'market_replay';
      const quantity = run.quantity_unit === 'synthetic_unit' ? (isReplay ? '模拟份额' : '研究份额') : '';
      q('h2').textContent = [run.symbol, quote?.name].filter(Boolean).join(' ');
      q('.market-result-meta').textContent = [
        run.portfolio_snapshot?.name || run.name,
        run.portfolio_revision ? `v${run.portfolio_revision}` : '',
        interval(run.timeframe),
        isReplay ? '历史行情回放' : run.mode === 'replay' ? '历史回放' : run.mode === 'incremental' ? '跟踪行情' : '',
        run.price_basis === 'forward_adjusted' ? '前复权研究' : run.price_basis === 'raw' ? '未复权' : '',
        quantity,
        run.is_demo ? '合成演示行情' : '',
      ].filter(Boolean).join(' · ');
      const metrics = run.metrics || {}, equity = run.equity?.at(-1)?.equity ?? run.final_equity ?? metrics.final_equity;
      const initial = run.initial_cash ?? metrics.initial_equity;
      const pnl = run.pnl ?? metrics.pnl ?? (finite(equity) && finite(initial) ? equity - initial : null);
      const rate = metrics.total_return_pct ?? (finite(pnl) && initial > 0 ? pnl / initial * 100 : null);
      const tone = pnl > 0 ? 'market-rise' : pnl < 0 ? 'market-fall' : '';
      const metricRows = [
        ['阶段盈亏', `${pnl > 0 ? '+' : ''}${cash(pnl)}`, tone],
        ['阶段收益率', percent(rate), tone],
        [isPaper ? '当前资产' : '结束资产', cash(equity)], ['可用现金', cash(run.cash)],
      ];
      q('.market-metrics').innerHTML = metricRows.map(([label, value, color]) => `<div><dt>${label}</dt><dd class="${color || ''}">${esc(value)}</dd></div>`).join('');
      q('.market-quote').textContent = quote ? [
        `最新报价 ${number(quote.price)}`, finite(quote.change_pct) ? percent(quote.change_pct) : '',
        time(quote.source_time), quoteLabels[quote.freshness] || '',
      ].filter(Boolean).join(' · ') : latestBar ? `${isReplay ? '最新可见 K 线' : '最新 K 线'} ${time(latestBar.date)}` : '';
      setStatus(run);
      const events = trades(run);
      chartView.setRun(run, events);
      const renderedTrades = table('买卖记录', ['方向', isReplay ? '模拟信号日期' : '信号时间', isReplay ? '模拟成交日期' : '成交时间',
        quantity || '数量', '成交价', '费用', '状态与原因'], events.slice().reverse().map(event => [
        event.side === 'buy' ? 'B 买入' : event.side === 'sell' ? 'S 卖出' : '—', event.signal || '—', event.filled || '—',
        event.quantity, number(event.price), cash(event.fee), [event.status, event.reason].filter(Boolean).join(' · '),
      ]));
      if (tradesHTML !== renderedTrades) {
        tradesHTML = renderedTrades;
        q('.market-trades').innerHTML = renderedTrades;
      }
      signalsSource = run.signals || [];
      if (signalsDetails.open) renderSignals();
      const covered = latestBar ? `${isReplay ? '已显示行情区间' : '行情区间'} ${time(run.bars[0].date)} ～ ${time(latestBar.date)}` : '';
      const requested = run.start_date ? `${isReplay ? '模拟区间' : '所选日期'} ${run.start_date} ～ ${run.end_date || (isReplay ? '数据区间结束' : '持续跟踪')}` : '';
      q('.market-details').innerHTML = [
        requested ? `<p>${esc(requested)}</p>` : '',
        covered ? `<p>${esc(covered)}</p>` : '',
        run.data_source ? `<p>行情来源 ${esc(run.data_source)}</p>` : '',
        `<p>初始资金 ${esc(cash(initial))} · 最大回撤 ${esc(percent(metrics.max_drawdown_pct))}</p>`,
        ...(run.warnings || []).map(warning => `<p class="market-muted">${esc(warning)}</p>`),
        table('当前持仓', ['股票', quantity || '数量', quantity ? '可卖份额' : '可卖数量', '平均成本'], (run.positions || []).map(position => [
          position.symbol, position.quantity, position.available_quantity, number(position.average_cost),
        ])),
      ].join('');
      updateForm();
    }

    function renderSignals() {
      const rows = (signalsSource || []).slice().reverse().map(signal => [
        time(signal.date), signal.target_pct == null ? '—' : percent(signal.target_pct).replace(/^\+/, ''), signal.conflict ? '有分歧' : '无',
        [...(signal.reasons || []), ...(signal.components || []).map(part => [part.name, part.reason].filter(Boolean).join(' · '))].join(' / '),
      ]);
      const markup = table('策略信号', [selected?.mode === 'market_replay' ? '模拟信号日期' : '时间', '目标仓位', '冲突', '规则与原因'], rows);
      if (markup !== renderedSignals) {
        renderedSignals = markup;
        q('.market-signals').innerHTML = markup;
      }
    }
    signalsDetails.addEventListener('toggle', () => { if (signalsDetails.open) renderSignals(); });

    function schedulePoll() {
      clearTimeout(pollTimer);
      if (!isPaper || !active || busy || selected?.status !== 'running') return;
      pollTimer = setTimeout(async () => {
        try {
          await readRun(selected.id);
        } finally {
          schedulePoll();
        }
      }, 5000);
    }

    async function readRun(id) {
      const version = ++readVersion;
      try {
        const run = await request(`${resource}/${encodeURIComponent(id)}`);
        if (version === readVersion) display(run);
      } catch {
        if (version === readVersion && active) q('.market-session-status').textContent = '状态刷新失败，仍显示上次取得的行情和记录。';
      }
    }

    async function action(runAction, pending, focusResult = false, element = progress) {
      if (busy) return;
      busy = true;
      readVersion++;
      clearTimeout(pollTimer);
      updateForm();
      setProgress(pending, false, element);
      try {
        const run = await runAction();
        if (run) {
          display(run);
          catalog = [run, ...catalog.filter(item => item.id !== run.id)];
          showHistory();
          if (focusResult && active) q('h2').focus();
        }
        setProgress('', false, element);
      } catch (error) {
        setProgress(error.message || '连接失败，请重试。', true, element);
      } finally {
        busy = false;
        updateForm();
        schedulePoll();
      }
    }

    fields.portfolio.addEventListener('change', updateForm);
    fields.start.addEventListener('change', () => { fields.end.min = fields.start.value || dateRange?.start_date || ''; });
    form.addEventListener('submit', event => {
      event.preventDefault();
      const portfolio = portfolios.find(row => row.id === fields.portfolio.value);
      if (!portfolio?.readiness?.ready) return;
      const symbol = normalizeSymbol(fields.symbol.value);
      if (!/^(?:6\d{5}\.SH|[03]\d{5}\.SZ)$/.test(symbol)) {
        setProgress('请输入沪深股票代码，例如 600519 或 600519.SH。', true);
        fields.symbol.focus();
        return;
      }
      const body = {
        portfolio_id: portfolio.id, portfolio_revision: portfolio.revision, symbol,
        start_date: fields.start.value, end_date: fields.end.value || null,
        initial_cash: fields.cash.valueAsNumber,
      };
      action(() => request(resource, body), isPaper ? '正在准备模拟盘…' : '正在获取行情并计算…', true);
    });
    history.addEventListener('change', () => {
      readVersion++;
      const id = history.value;
      if (!id) {
        selected = null;
        result.hidden = true;
        schedulePoll();
        return;
      }
      action(() => request(`${resource}/${encodeURIComponent(id)}`), '正在读取记录…').finally(showHistory);
    });
    refresh.addEventListener('click', () => {
      loadHistory();
      if (selected) action(() => request(`${resource}/${encodeURIComponent(selected.id)}`), '正在刷新状态…');
    });
    commands.forEach(button => {
      button.addEventListener('click', () => {
        if (selected) action(() => request(`${resource}/${encodeURIComponent(selected.id)}/${button.dataset.command}`, {}),
          '正在更新运行状态…', true, q('.market-command-status'));
      });
    });
    updateForm();

    return {
      setCatalog,
      selectPortfolio(id) { fields.portfolio.value = id; updateForm(); },
      activate(next) {
        const wasActive = active;
        active = next;
        if (active && !wasActive) {
          loadHistory();
          chartView.redraw();
        }
        schedulePoll();
      },
    };
  }

  window.marketWorkstation = {
    mount(request) {
      const workspaces = {};
      for (const mode of ['backtest', 'paper']) {
        const root = document.querySelector(`#market-${mode}`);
        if (root) workspaces[mode] = mountWorkspace(root, mode, request);
      }
      return {
        setCatalog(rows, datasets) { Object.values(workspaces).forEach(workspace => workspace.setCatalog(rows, datasets)); },
        selectPortfolio(mode, id) { workspaces[mode]?.selectPortfolio(id); },
        activate(current) { Object.entries(workspaces).forEach(([mode, workspace]) => workspace.activate(mode === current)); },
      };
    },
  };
})();
