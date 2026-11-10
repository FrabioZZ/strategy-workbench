(() => {
  'use strict';
  const host = document.querySelector('#workspace-paper');
  if (!host) return;
  const panel = document.createElement('section');
  panel.id = 'quote-panel'; panel.className = 'quote-panel'; panel.setAttribute('aria-labelledby', 'quote-title');
  panel.innerHTML = `
    <div class="quote-heading"><div><h2 id="quote-title">最新行情与持仓估值</h2></div><button id="quote-refresh" class="secondary" type="button">刷新报价与估值</button></div>
    <p class="helper">公开行情可能延迟。刷新报价只更新持仓估值，不触发交易。</p>
    <div class="quote-picker"><label for="quote-search">搜索股票名称或代码</label><input id="quote-search" type="search" placeholder="例如：平安银行 / 000001" autocomplete="off"><p id="quote-universe" class="helper"></p><div id="quote-stocks" class="quote-stocks" aria-label="行情股票选择"></div><button id="quote-more" class="quiet" type="button" hidden>显示更多股票</button>
      <form id="quote-direct" hidden><label for="quote-code">直接输入沪深A股代码</label><div class="quote-direct-row"><input id="quote-code" placeholder="600000.SH" pattern="(6[0-9]{5}\.SH|[03][0-9]{5}\.SZ)" required><button class="secondary" type="submit">查看报价</button></div></form>
    </div>
    <p id="quote-feedback" role="status" aria-live="polite">打开模拟盘后读取最新报价。</p>
    <div id="quote-result"><p class="empty-copy">正在读取股票池…</p></div>
    <section class="quote-valuation" aria-labelledby="quote-valuation-title"><h3 id="quote-valuation-title">增量账户持仓估值</h3><label id="quote-account-label" hidden>估值账户<select id="quote-account"></select></label><div id="quote-account-result"></div><p id="quote-historical" class="helper"></p></section>
    <details class="quote-behavior"><summary>刷新方式与估值口径</summary><p>可见的模拟盘页面每 45 秒刷新；切换工作区或隐藏页面时暂停页面轮询，返回时刷新。手动刷新共用服务端缓存，不能突破限流。</p><p>本地服务运行时，独立后台每 45 秒检查增量账户的持仓（含暂停账户），以及最近 120 秒页面关注过的股票。关闭页面后持仓仍刷新；退出本地服务后停止。没有持仓时只显示账面现金。</p><p>总资产＝现金＋有效现价×股数；浮盈亏＝持仓市值−账面持仓成本，账面成本沿用已记录费用。报价缺失、过期、零成交状态未知或源故障时不提供完整估值。公开快照可能延迟，来源时间是供应商快照时间，并非逐笔成交时间。</p><p>历史回放与 Backtrader 保留历史账本，不纳入这里的最新估值。行情刷新不改写历史净值、委托、成交或组合版本；原日线模拟仍按下方说明独立运行。</p></details>`;
  host.querySelector('.work-heading').after(panel);
  const q = s => panel.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = v => v == null ? '—' : Number(v).toLocaleString('zh-CN', {minimumFractionDigits:2,maximumFractionDigits:2});
  const stamp = v => v ? new Date(v).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false}) : '尚无记录';
  const phases = {trading:'交易时段',auction:'集合竞价',lunch:'午间休市',closed:'闭市',preopen:'开盘前',calendar_unknown:'交易日历未知'};
  const freshness = {fresh:'最新快照',closed_latest:'最近有效收盘快照',break_latest:'午间最新可得',stale:'报价过期',stale_cache:'缓存过期',calendar_unknown:'日历未知，停止估值',status_unknown:'零成交，状态未知',invalid_time:'时间异常',unavailable:'尚无有效报价'};
  const state = {members:[], selected:'', accounts:[], data:null, loaded:false, disconnected:false, busy:false, timer:null, limit:8};
  const active = () => location.hash === '#paper' && !document.hidden;
  async function api(path) {
    const response = await fetch('/api/trading/quotes' + path, {signal:AbortSignal.timeout(15000)});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '报价服务暂不可用');
    return data;
  }
  function stocks() {
    const search = q('#quote-search').value.trim().toLowerCase();
    const rows = state.members.filter(m => (m.name+' '+m.symbol).toLowerCase().includes(search));
    q('#quote-stocks').innerHTML = rows.slice(0,state.limit).map(m => `<button type="button" class="stock-option" data-quote-symbol="${esc(m.symbol)}" aria-pressed="${state.selected===m.symbol}"><strong>${esc(m.name)}</strong><span>${esc(m.symbol)}</span></button>`).join('') || '<p class="helper">没有匹配股票，可直接输入完整代码查看。</p>';
    q('#quote-more').hidden = rows.length <= state.limit;
    q('#quote-direct').hidden = rows.length > 0;
  }
  function quoteCard(quote) {
    if (!quote) return '<p class="empty-copy">选择一只股票查看最新报价。</p>';
    const invalid = !quote.valid_for_valuation;
    const change = quote.change == null ? '—' : `${quote.change>0?'+':''}${money(quote.change)} / ${quote.change_pct>0?'+':''}${money(quote.change_pct)}%`;
    return `<article class="quote-card ${invalid?'quote-invalid':''}"><div class="quote-heading"><div><h3>${esc(quote.name)} <span class="quote-code">${esc(quote.symbol)}</span></h3><p class="quote-market">${esc(phases[quote.market.phase])} · ${esc(freshness[quote.freshness])}</p></div><span class="quote-badge">${quote.feed_status==='error'?'源故障':quote.feed_status==='waiting'?'等待刷新':'已收到快照'}</span></div>
      <div class="quote-price-line"><strong class="quote-price">${money(quote.price)}</strong><span class="quote-change ${quote.change>0?'quote-up':quote.change<0?'quote-down':''}">${change}<small>相对昨收 ${money(quote.previous_close)}</small></span></div>
      ${quote.error?`<p class="quote-warning">${esc(quote.error)}。保留上次报价供参考，不用于完整估值。</p>`:''}
      ${quote.security_status==='zero_volume_unknown'?'<p class="quote-warning">源端成交量为零；无法据此确认停牌，暂停有效估值。</p>':''}
      <dl class="quote-times"><div><dt>来源快照时间 · 北京时间</dt><dd>${stamp(quote.source_time)}</dd></div><div><dt>收到时间</dt><dd>${stamp(quote.received_at)}</dd></div><div><dt>最近成功取得</dt><dd>${stamp(quote.last_success_at)}</dd></div><div><dt>最近尝试</dt><dd>${stamp(quote.last_attempt_at)}</dd></div></dl>
      <p class="helper">${esc(quote.source)} · 下次可请求 ${stamp(quote.next_attempt_at)}${quote.market.phase==='calendar_unknown'?' · 日历仅核实至2026-12-31':''}</p></article>`;
  }
  function accounts() {
    const old = q('#quote-account').value;
    q('#quote-account').replaceChildren(...state.accounts.map(a => new Option(a.name, a.id)));
    if (state.accounts.some(a => a.id === old)) q('#quote-account').value = old;
    q('#quote-account-label').hidden = !state.accounts.length;
    renderAccount();
  }
  function renderAccount() {
    if (state.disconnected) {
      q('#quote-account-result').innerHTML = '<p class="quote-warning">暂时无法取得账户快照与有效报价，不显示旧的完整估值。</p>';
      return;
    }
    const a = state.accounts.find(a => a.id === q('#quote-account').value);
    if (!a) {
      q('#quote-account-result').innerHTML = '<p class="empty-copy">当前没有增量模拟账户。上方选股报价可直接使用，无需先创建策略或账户。</p>';
      return;
    }
    q('#quote-account-result').innerHTML = `<p class="helper">${esc(a.name)} · 日线模拟${a.execution_status==='running'?'运行中':'已暂停'} · 冻结组合 v${a.portfolio_revision} · 账本游标 ${esc(a.ledger_cursor||'尚未消费日线')}</p>
      <dl class="quote-metrics"><div><dt>账面现金</dt><dd>${money(a.cash)}</dd></div><div><dt>持仓市值</dt><dd>${money(a.market_value)}</dd></div><div><dt>最新总资产</dt><dd>${money(a.total_assets)}</dd></div><div><dt>持仓浮盈亏</dt><dd>${money(a.unrealized_pnl)}</dd></div></dl>
      <p class="${a.complete?'helper':'quote-warning'}">${a.status==='cash_only'?'当前空仓，总资产等于现金，不产生行情波动。':a.complete?'按有效最新快照估值，与历史净值曲线分开展示。':'持仓报价不完整或暂不可用，暂不计算总资产与浮盈亏。'}</p>
      ${a.positions.map(p => `<div class="quote-position"><strong>${esc(p.symbol)} · ${p.quantity} 股</strong><p>账面均价 ${money(p.average_cost)} · 持仓成本 ${money(p.book_cost)} · 市值 ${money(p.market_value)} · 浮盈亏 ${money(p.unrealized_pnl)}</p><p class="helper">现价 ${money(p.quote?.price)} · ${esc(p.quote?.feed_status==='error'?'源故障':freshness[p.quote?.freshness]||'缺少报价')} · 源时间 ${stamp(p.quote?.source_time)} · 收到 ${stamp(p.quote?.received_at)} · 最近成功 ${stamp(p.quote?.last_success_at)} · ${esc(p.quote?.source||'腾讯公开快照')}</p></div>`).join('')}
      <p class="helper">本次估值时间 ${stamp(a.valued_at)} · 金额单位：元</p>`;
  }
  function schedule() {
    clearTimeout(state.timer);
    if (active()) state.timer = setTimeout(refresh, 45000);
  }
  async function refresh() {
    if (state.busy || !active()) return;
    state.busy = true; q('#quote-refresh').disabled = true;
    q('#quote-feedback').textContent = '正在读取报价与持仓估值…';
    let requested = state.selected;
    try {
      if (!state.loaded) {
        const catalog = await api('/catalog'); state.members = catalog.members; state.loaded = true;
        state.selected ||= state.members[0]?.symbol || '';
        q('#quote-universe').textContent = state.members.length ? `${catalog.universe.name||'沪深300'} · ${state.members.length}只 · 成分快照 ${catalog.universe.as_of_date||'日期未知'}，不代表历史每日成分。` : catalog.message;
        stocks();
      }
      requested = state.selected;
      const data = await api('/overview?symbols=' + encodeURIComponent(requested));
      if (requested === state.selected) {
        state.data = data; state.accounts = data.accounts; state.disconnected = false;
        q('#quote-result').innerHTML = quoteCard(data.quotes[0]); accounts();
        q('#quote-historical').textContent = data.excluded_historical_accounts ? `另有 ${data.excluded_historical_accounts} 个历史回放账户，继续按历史价格展示，未纳入最新估值。` : '历史回放与 Backtrader 不纳入最新估值。';
        q('#quote-feedback').textContent = `已检查 ${stamp(data.server_time)} · 可见时每45秒自动刷新 · 各页面共用缓存`;
      }
    } catch (error) {
      state.disconnected = true;
      q('#quote-feedback').textContent = `本地报价服务连接失败：${error.message}。将在45秒后重试。`;
      q('#quote-result').innerHTML = '<p class="quote-warning">当前报价无法确认，请等待刷新或检查本地服务。</p>';
      renderAccount();
    } finally {
      state.busy = false; q('#quote-refresh').disabled = false;
      if (requested !== state.selected && active()) refresh(); else schedule();
    }
  }
  q('#quote-search').addEventListener('input', () => {state.limit=8; stocks();});
  q('#quote-more').addEventListener('click', () => {state.limit+=16; stocks();});
  q('#quote-stocks').addEventListener('click', event => {
    const button = event.target.closest('[data-quote-symbol]');
    if (!button) return;
    state.selected = button.dataset.quoteSymbol; stocks(); refresh();
  });
  q('#quote-direct').addEventListener('submit', event => {event.preventDefault(); state.selected=q('#quote-code').value.trim().toUpperCase(); refresh();});
  q('#quote-refresh').addEventListener('click', refresh);
  q('#quote-account').addEventListener('change', renderAccount);
  function visibility() {clearTimeout(state.timer); if (active()) refresh();}
  document.addEventListener('visibilitychange', visibility);
  window.addEventListener('hashchange', visibility);
  visibility();
})();
