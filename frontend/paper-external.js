(() => {
  'use strict';
  const host = document.querySelector('#workspace-paper');
  if (!host || document.querySelector('#pex-panel')) return;
  const panel = document.createElement('section');
  panel.id = 'pex-panel'; panel.className = 'pex-panel'; panel.setAttribute('aria-labelledby', 'pex-title');
  panel.innerHTML = `
    <div class="pex-heading"><div><p class="pex-eyebrow">BACKTRADER · 本机独立账本</p><h2 id="pex-title">免账号历史模拟</h2></div><span class="pex-tag">历史回放 · 非实时</span></div>
    <p>使用已确认的策略组合，由 Backtrader 计算模拟订单、现金与持仓。无需注册或登录第三方账号。</p>
    <p class="pex-notice">仅使用未复权普通主板行情。沪深300复权研究数据请在回测工作区使用；本模块不提供实时跟盘或券商交易。</p>
    <p id="pex-capability">正在检查本机引擎…</p>
    <details class="pex-create"><summary>新建外部引擎回放</summary>
      <form id="pex-form"><div class="pex-grid">
        <label>回放名称<input id="pex-name" required maxlength="120" value="我的历史模拟"></label>
        <label>已保存组合 / 版本<select id="pex-portfolio" required></select></label>
        <label>未复权行情数据<select id="pex-dataset" required></select></label>
        <label>标的代码<select id="pex-symbol" required></select></label>
        <label>初始资金（元）<input id="pex-cash" type="number" min="0.01" max="1000000000" step="0.01" value="100000" required></label>
      </div><p id="pex-data-help" class="pex-muted"></p>
      <details><summary>费用与滑点假设</summary><div class="pex-grid">
        <label>佣金（基点）<input id="pex-commission" type="number" min="0" max="100" step="any" value="3" required></label>
        <label>最低佣金（元）<input id="pex-minimum" type="number" min="0" max="1000" step="any" value="5" required></label>
        <label>卖出税费（基点）<input id="pex-tax" type="number" min="0" max="100" step="any" value="5" required></label>
        <label>滑点（基点）<input id="pex-slip" type="number" min="0" max="100" step="any" value="0" required></label>
      </div></details><button class="primary" id="pex-create" type="submit">创建历史回放</button></form>
    </details>
    <div class="pex-select"><label>已保存的外部回放<select id="pex-history"><option value="">选择历史回放</option></select></label><button type="button" id="pex-refresh" class="secondary">刷新外部回放</button></div>
    <p id="pex-feedback" role="status" aria-live="polite"></p>
    <div id="pex-result"><p class="pex-muted">选择或创建回放后，查看真实引擎计算的资金、信号和订单。</p></div>
    <p class="pex-license">开源引擎：Backtrader 1.9.78.123 · GPL-3.0-or-later。费用仅为假设；开盘停牌或触及限价保守不成交。</p>`;
  host.append(panel);
  const q = s => panel.querySelector(s);
  const state = {portfolios: [], datasets: [], sessions: [], current: null, busy: false, installed: false};
  const escaped = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = v => Number(v || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const status = s => ({submitted:'待下一根',accepted:'已接受',filled:'已成交',rejected:'拒单',cancelled:'已撤销'}[s] || s);
  async function api(path, body) {
    const r = await fetch('/api/trading' + path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await r.json();
    if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : '请求未成功，请检查输入或刷新后重试。');
    return data;
  }
  function options(select, rows, title, label) {
    const old = select.value;
    select.replaceChildren(new Option(title, ''));
    rows.forEach(row => select.add(new Option(label(row), row.id)));
    if (rows.some(row => row.id === old)) select.value = old;
  }
  function symbols() {
    const ds = state.datasets.find(d => d.id === q('#pex-dataset').value);
    options(q('#pex-symbol'), (ds?.symbols || []).map(id => ({id})), '请选择标的', r => r.id);
    if (ds?.symbols.length === 1) q('#pex-symbol').value = ds.symbols[0];
    q('#pex-data-help').textContent = ds ? `${ds.is_demo ? '演示合成数据 · ' : ''}${ds.source} · ${ds.start_date} 至 ${ds.end_date}` : '请先在回测工作区导入未复权 CSV 或显式加载演示数据，再刷新此处。';
  }
  function history() {
    options(q('#pex-history'), state.sessions, '选择历史回放', s => `${s.is_demo ? '演示 · ' : ''}${s.name} · ${s.consumed_bars}/${s.total_bars} 根`);
    q('#pex-history').value = state.current?.id || '';
  }
  function render(s) {
    state.current = s;
    const currentEquity = s.equity.at(-1)?.equity ?? s.initial_cash;
    const complete = s.status === 'completed';
    q('#pex-result').innerHTML = `
      <h3>${escaped(s.name)} <span class="pex-tag">${s.is_demo ? '演示 · ' : ''}${complete ? '回放完成' : '已暂停'}</span></h3>
      <p>${escaped(s.portfolio_snapshot.name)} v${s.portfolio_revision} · ${escaped(s.symbol)} · ${s.consumed_bars} / ${s.total_bars} 根 · 游标 ${escaped(s.cursor || '尚未开始')}</p>
      <div class="pex-metrics"><div><span>现金</span><strong>${money(s.cash)}</strong></div><div><span>账户权益</span><strong>${money(currentEquity)}</strong></div><div><span>累计收益</span><strong>${money(s.metrics.total_return_pct)}%</strong></div><div><span>最大回撤</span><strong>${money(s.metrics.max_drawdown_pct)}%</strong></div></div>
      <p>${escaped(s.message)}</p><div class="pex-actions"><button type="button" data-pex-action="step" class="secondary" ${complete?'disabled':''}>单步一根</button><button type="button" data-pex-action="run" class="primary" ${complete?'disabled':''}>运行至末尾</button><button type="button" data-pex-export class="secondary">导出回放 JSON</button></div>
      <p class="pex-muted">按收盘决定股数，下一根开盘撮合；跳空可能因资金不足拒单。运行期间请等待结果，页面不会后台自动推进。</p>
      <h4>持仓</h4>${s.positions.length ? s.positions.map(p => `<p>${escaped(p.symbol)} · ${p.quantity} 股 · 可卖 ${p.available_quantity} 股 · 成本 ${money(p.average_cost)}</p>`).join('') : '<p class="pex-muted">当前空仓</p>'}
      <details open><summary>订单与成交 · ${s.fills.length} 笔成交 · 费用 ${money(s.metrics.fees)} 元</summary>
      <div class="pex-table-wrap" tabindex="0" aria-label="外部模拟订单表"><table><thead><tr><th>信号日</th><th>执行日</th><th>方向 / 股数</th><th>成交价</th><th>状态 / 原因</th></tr></thead><tbody>${s.orders.length ? s.orders.map(o => `<tr><td>${escaped(o.signal_date)}</td><td>${escaped(o.date || '—')}</td><td>${o.side==='buy'?'买入':'卖出'} ${o.quantity}</td><td>${o.price == null ? '—' : money(o.price)}</td><td>${status(o.status)}${o.reason?` · ${escaped(o.reason)}`:''}</td></tr>`).join('') : '<tr><td colspan="5">尚无委托；无信号或全现金也可能是有效结果。</td></tr>'}</tbody></table></div></details>
      <details><summary>信号与组合决策 · ${s.signals.length} 根</summary><div class="pex-table-wrap" tabindex="0" aria-label="外部模拟信号表"><table><thead><tr><th>日期</th><th>目标仓位</th><th>策略依据</th></tr></thead><tbody>${s.signals.map(x => `<tr><td>${escaped(x.date)}</td><td>${x.target_pct == null ? '冲突阻止' : money(x.target_pct)+'%'}</td><td>${escaped(x.components.map(c => c.name+'：'+c.reason).join('；'))}</td></tr>`).join('')}</tbody></table></div></details>
      <details><summary>数据来源与使用边界</summary><p>${escaped(s.dataset_snapshot?.source || '')}</p><ul>${s.warnings.map(w => `<li>${escaped(w)}</li>`).join('')}</ul></details>`;
    history();
  }
  async function perform(fn) {
    if (state.busy) return;
    state.busy = true; panel.setAttribute('aria-busy', 'true');
    const buttons = [...panel.querySelectorAll('button')].map(b => [b, b.disabled]);
    buttons.forEach(([b]) => b.disabled = true);
    q('#pex-feedback').textContent = '正在处理历史回放…';
    try { await fn(); q('#pex-feedback').textContent = '已更新。'; }
    catch (e) { q('#pex-feedback').textContent = e.message; }
    finally { state.busy = false; panel.removeAttribute('aria-busy'); buttons.forEach(([b,d]) => b.disabled = d); q('#pex-create').disabled = !state.installed; }
  }
  async function load() {
    const [cap, ps, ds, ss] = await Promise.all(['/external-paper/capabilities','/portfolios','/datasets','/external-paper/sessions'].map(p => api(p)));
    state.installed = cap.installed; state.portfolios = ps; state.sessions = ss;
    state.datasets = ds.filter(d => d.price_basis === 'raw' && d.market === 'CN_A_MAIN' && d.dataset_type !== 'research_adjusted' && (!d.allowed_modes || d.allowed_modes.includes('replay')));
    q('#pex-capability').textContent = cap.installed ? `${cap.name} ${cap.version} 已安装 · 无需账号 · 本机计算` : '可选引擎未安装或版本不匹配；请按项目说明安装 requirements-paper.txt。';
    options(q('#pex-portfolio'), ps, '请选择已保存组合', p => `${p.name} v${p.revision}${p.readiness.ready ? '' : ' · 尚未就绪'}`);
    options(q('#pex-dataset'), state.datasets, '请选择未复权数据', d => `${d.is_demo?'演示 · ':''}${d.name} · ${d.row_count} 行`);
    symbols(); history();
    if (state.current) { const s = ss.find(s => s.id === state.current.id); if (s) render(s); }
  }
  q('#pex-refresh').addEventListener('click', () => perform(load));
  q('#pex-dataset').addEventListener('change', symbols);
  q('#pex-history').addEventListener('change', () => {
    const id = q('#pex-history').value;
    if (id) perform(async () => render(await api('/external-paper/sessions/' + encodeURIComponent(id))));
  });
  q('#pex-form').addEventListener('submit', e => {
    e.preventDefault(); perform(async () => {
      const p = state.portfolios.find(x => x.id === q('#pex-portfolio').value);
      if (!p?.readiness.ready) throw Error('请先在策略组合工作区保存并确认一个已就绪版本。');
      const s = await api('/external-paper/sessions', {name:q('#pex-name').value, mode:'replay', portfolio_id:p.id, portfolio_revision:p.revision,
        dataset_id:q('#pex-dataset').value, symbol:q('#pex-symbol').value, initial_cash:Number(q('#pex-cash').value),
        costs:{commission_bps:Number(q('#pex-commission').value), min_commission:Number(q('#pex-minimum').value), sell_tax_bps:Number(q('#pex-tax').value), slippage_bps:Number(q('#pex-slip').value)}});
      state.sessions.unshift(s); render(s);
    });
  });
  q('#pex-result').addEventListener('click', e => {
    const exportButton = e.target.closest('[data-pex-export]');
    if (exportButton && state.current) {
      const url = URL.createObjectURL(new Blob([JSON.stringify(state.current,null,2)],{type:'application/json'}));
      const a = document.createElement('a'); a.href=url; a.download=`backtrader-${state.current.id}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); return;
    }
    const b = e.target.closest('[data-pex-action]'); if (!b || !state.current) return;
    perform(async () => {
      const s = await api(`/external-paper/sessions/${encodeURIComponent(state.current.id)}/${b.dataset.pexAction}`, {request_id:crypto.randomUUID()});
      state.sessions = state.sessions.map(x => x.id === s.id ? s : x); render(s);
    });
  });
  perform(load);
})();
