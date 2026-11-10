'use strict';
// Keep phase-one DOM and state alive while moving between workspaces.
(() => {
const q=s=>document.querySelector(s), all=s=>[...document.querySelectorAll(s)];
const escape=esc;
const T={workspace:'materials',loaded:false,loading:null,strategies:[],portfolios:[],datasets:[],runs:[],sessions:[],portfolio:null,items:[],dirty:false,session:null,poll:null,busy:false};
// UI-only request state stays out of the saved portfolio schema.
const aiMappings=new Map();
const conditionalDrafts=new Map();
function cancelMappings(){for(const m of aiMappings.values())m.controller?.abort();aiMappings.clear();}
function invalidateMapping(item){const m=aiMappings.get(item.id);if(m){m.controller?.abort();aiMappings.delete(item.id);}}
const names={materials:'资料',portfolio:'策略组合',backtest:'回测',paper:'模拟盘'};
const money=n=>Number(n??0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
const pct=n=>`${Number(n??0).toFixed(2)}%`;
const stamp=v=>v?new Date(v).toLocaleString('zh-CN',{hour12:false}):'尚无记录';
const uid=()=>crypto.randomUUID();
async function request(path,body,method='POST') {
  const r=await fetch('/api/trading'+path,body===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json().catch(()=>null);
  if(!r.ok){const d=data?.detail;throw Error(typeof d==='string'?d:Array.isArray(d)?d.map(x=>`${x.loc?.slice(1).join(' / ')}：${x.msg}`).join('；'):`请求失败（${r.status}）`);}
  return data;
}
async function task(button,fn){if(button?.disabled)return; if(button){button.disabled=true;button.setAttribute('aria-busy','true');}try{await fn();}catch(e){notify(e.message||'服务连接中断，请重试。',true);}finally{if(button){button.disabled=false;button.removeAttribute('aria-busy');}updateControls();updateResearchControls();}}
function wire(id,fn){q('#'+id).addEventListener('click',e=>task(e.currentTarget,fn));}
function switchWorkspace(focus=false){
  const key=location.hash.slice(1);T.workspace=names[key]?key:'materials';
  all('[data-workspace-panel]').forEach(el=>el.hidden=el.id!==`workspace-${T.workspace}`);
  all('[data-workspace]').forEach(el=>{if(el.dataset.workspace===T.workspace)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  q('#materials-library').hidden=T.workspace!=='materials';q('#workspace-label').textContent=names[T.workspace];
  if(focus){q('#notice').hidden=true;window.scrollTo({top:0,behavior:'instant'});q(`#workspace-${T.workspace} h1`)?.focus({preventScroll:true});}
  if(T.workspace!=='materials')task(null,load);
  scheduleRefresh();
}
window.addEventListener('hashchange',()=>switchWorkspace(true));
q('.skip-link').addEventListener('click',e=>{e.preventDefault();q('#main').focus();});
function options(el,rows,empty,label,value){const prev=value??el.value;el.innerHTML=`<option value="">${escape(empty)}</option>`+rows.map(r=>`<option value="${escape(r.id)}">${escape(label(r))}</option>`).join('');el.value=prev;}
const portfolioLabel=p=>`${p.name} · v${p.revision}${p.readiness.ready?'':' · 有待处理项'}`;
const dataLabel=d=>`${d.is_demo?'演示 · ':''}${d.name} · ${d.row_count} 行 · ${d.start_date}～${d.end_date}`;
const isResearch=d=>d?.dataset_type==='research_adjusted';
const isResearchRun=r=>r.execution_model==='adjusted_research'||isResearch(r.dataset_snapshot);
let stockLimit=24,researchBusy=false;
function fillSelects(){
  options(q('#portfolio-select'),T.portfolios,'新建组合',portfolioLabel,T.portfolio?.id||'');
  for(const id of ['backtest-portfolio','paper-portfolio','research-portfolio'])options(q('#'+id),T.portfolios,'请选择已保存组合',portfolioLabel);
  for(const id of ['backtest-dataset','paper-dataset','paper-sync-dataset'])options(q('#'+id),T.datasets.filter(d=>!isResearch(d)&&(id==='backtest-dataset'||!d.allowed_modes||d.allowed_modes.some(mode=>['replay','incremental'].includes(mode)))),id==='backtest-dataset'?'请选择行情数据':'无 / 等待行情',dataLabel);
  options(q('#backtest-history'),T.runs.filter(r=>!isResearchRun(r)),'选择已完成的回测',r=>`${r.portfolio_snapshot.name} v${r.portfolio_revision} · ${r.is_demo?'演示 · ':''}${stamp(r.created_at)}`);
  options(q('#research-history'),T.runs.filter(isResearchRun),'选择已完成的研究回测',r=>`${r.portfolio_snapshot.name} v${r.portfolio_revision} · ${r.symbol} · ${stamp(r.created_at)}`);
  options(q('#paper-history'),T.sessions,'选择模拟账户',s=>`${s.name} · ${s.mode==='replay'?'历史回放':'新行情'} · ${s.status==='running'?'运行中':'已暂停'}`,T.session?.id||'');
  q('#backtest-strategy-guide').hidden=T.portfolios.some(p=>p.readiness.ready);
  researchRuleNote();
  renderResearchCatalog();
  syncDates('backtest');
}
async function load(force=false){
  if(T.loading)return T.loading;if(T.loaded&&!force)return;
  T.loading=(async()=>{const [cap,strategies,portfolios,datasets,runs,sessions]=await Promise.all(['/capabilities','/strategies','/portfolios','/datasets','/backtests','/paper/sessions'].map(p=>request(p)));
    Object.assign(T,{cap,strategies,portfolios,datasets,runs,sessions,loaded:true});fillSelects();renderCandidates();renderCapabilities();
  })();try{await T.loading;}catch(e){q('#research-status').innerHTML='<p class="result-warning">数据目录读取失败，请点击“刷新数据目录”重试。已有内容保留上次取得的状态。</p>';throw e;}finally{T.loading=null;}
}
function renderCapabilities(){q('#trading-capabilities').innerHTML=`<details><summary>行情与模拟交易状态</summary><p>${escape(T.cap.broker.label)}</p><p>日线行情：CSV / Tushare（${T.cap.feeds.tushare_configured?'已配置，待验证连接':'未配置'}）。公开报价用于查看行情和持仓估值。</p><ul>${T.cap.limitations.map(x=>`<li>${escape(x)}</li>`).join('')}</ul></details>`;renderIndicatorLibrary();}
const indicatorNames=()=>new Set((T.cap?.indicators||[]).map(i=>i.name));
const hasConditional=()=>T.cap?.rule_types?.includes('conditional');
function renderIndicatorLibrary(){
  let root=q('#indicator-library');if(!root){q('.trading-columns').insertAdjacentHTML('beforebegin','<details id="indicator-library" class="indicator-library"></details>');root=q('#indicator-library');}
  const indicators=T.cap.indicators||[];
  root.innerHTML=`<summary>支持的日线指标与参数（${indicators.length||'MA / 价格阈值'}）</summary><p class="helper">周期单位为交易日。选择指标查看参数范围与预热要求。</p>${indicators.length?`<div class="indicator-grid">${indicators.map(i=>`<details class="indicator-entry"><summary>${escape(i.label||i.name)} · ${escape(i.name)}${i.raw_only?' · 仅未复权限价数据':''}</summary><p>${escape(i.formula||i.description||i.note||'')}</p><p>参数：<code>${escape(Object.entries(i.params||i.parameters||{}).map(([key,p])=>`${key} = ${p.default}（${p.enum?p.enum.join(' / '):`${p.minimum}～${p.maximum}`}${p.type==='integer'?'，整数':''}）`).join('；')||'无需参数')}</code></p>${i.warmup?`<p>预热：${escape(typeof i.warmup==='string'?i.warmup:JSON.stringify(i.warmup))}</p>`:''}</details>`).join('')}</div>`:'<p class="helper">当前服务尚未发布扩展指标；现有快慢均线与价格阈值仍可使用。</p>'}`;
  for(const el of all('[data-field="rule-type"]'))if(hasConditional()&&!el.querySelector('option[value="conditional"]'))el.insertAdjacentHTML('beforeend','<option value="conditional">指标条件组合（预设 / 高级编辑）</option>');
}
const operand=(indicator,params={})=>({indicator,...(Object.keys(params).length?{params}:{})});
const condition=(op,left,right)=>({op,left,right:typeof right==='number'?{value:right}:right});
const rulePresets={
  rsi:{label:'RSI 超卖 / 超买',note:'RSI(14) ≤ 30 入场，≥ 70 离场。阈值是示例参数，需自行核对。',buy:condition('lte',operand('RSI',{period:14}),30),sell:condition('gte',operand('RSI',{period:14}),70)},
  macd:{label:'MACD 金叉 / 死叉',note:'DIF 上穿 DEA 入场，下穿离场。使用 12 / 26 / 9。',buy:condition('cross_above',operand('MACD_DIF',{fast:12,slow:26,signal:9}),operand('MACD_DEA',{fast:12,slow:26,signal:9})),sell:condition('cross_below',operand('MACD_DIF',{fast:12,slow:26,signal:9}),operand('MACD_DEA',{fast:12,slow:26,signal:9}))},
  boll:{label:'布林带下轨 / 中轨',note:'收盘价低于下轨入场，高于中轨离场。采用默认参数，可在高级编辑中修改。',buy:condition('lt',operand('CLOSE'),operand('BOLL_LOWER')),sell:condition('gt',operand('CLOSE'),operand('BOLL_MID'))},
  kdj:{label:'KDJ 金叉 / 死叉',note:'K 上穿 D 入场，下穿离场。采用默认参数，可在高级编辑中修改。',buy:condition('cross_above',operand('KDJ_K'),operand('KDJ_D')),sell:condition('cross_below',operand('KDJ_K'),operand('KDJ_D'))},
  ema:{label:'EMA 趋势',note:'EMA(5) 高于 EMA(20) 入场，低于或等于时离场。',buy:condition('gt',operand('EMA',{period:5}),operand('EMA',{period:20})),sell:condition('lte',operand('EMA',{period:5}),operand('EMA',{period:20}))},
  volume:{label:'均线 + 日线量比',note:'收盘高于 MA(20) 且日线量比 > 1.5 入场，收盘低于 MA(20) 离场。日线量比不是盘口量比。',buy:{op:'and',conditions:[condition('gt',operand('CLOSE'),operand('MA',{period:20})),condition('gt',operand('VOLUME_RATIO',{period:5}),1.5)]},sell:condition('lt',operand('CLOSE'),operand('MA',{period:20}))},
  first_limit:{label:'首个涨停收盘信号',note:'收盘确认首个涨停后，下一交易日开盘尝试入场；收盘跌破 MA(5) 离场。仅适用于含每日涨停价的未复权数据。',buy:condition('eq',operand('FIRST_LIMIT_UP'),1),sell:condition('lt',operand('CLOSE'),operand('MA',{period:5}))}
};
function presetRules(key){const p=rulePresets[key]||rulePresets.rsi;return {type:'conditional',target_pct:50,stop_loss_pct:null,buy:structuredClone(p.buy),sell:structuredClone(p.sell)};}
function conditionalError(r){
  const numeric=v=>typeof v==='number'&&Number.isFinite(v),object=v=>v&&typeof v==='object'&&!Array.isArray(v);
  if(!object(r)||r.type!=='conditional'||Object.keys(r).some(k=>!['type','target_pct','stop_loss_pct','buy','sell'].includes(k)))return '规则仅接受 type、target_pct、stop_loss_pct、buy 和 sell。';
  if(!numeric(r.target_pct)||r.target_pct<=0||r.target_pct>100)return '目标仓位必须大于 0 且不超过 100。';
  if(r.stop_loss_pct!=null&&(!numeric(r.stop_loss_pct)||r.stop_loss_pct<=0||r.stop_loss_pct>=100))return '止损比例必须大于 0 且小于 100，或为 null。';
  const names=indicatorNames();
  function value(v){
    if(!object(v))throw Error('比较两侧必须是指标或数值对象。');
    if('value' in v){if(Object.keys(v).length!==1||!numeric(v.value))throw Error('常量格式为 {"value": 有限数字}。');return;}
    if(Object.keys(v).some(k=>!['indicator','params','offset'].includes(k))||!names.has(v.indicator))throw Error('使用了当前服务不支持的指标或操作数字段。');
    if('offset'in v&&(!Number.isInteger(v.offset)||v.offset<0||v.offset>250))throw Error('offset 仅允许过去 0～250 根日线。');
    if('params'in v&&!object(v.params))throw Error('指标参数必须是对象。');
    const definition=(T.cap.indicators||[]).find(i=>i.name===v.indicator),specs=definition?.params||{},params=v.params||{};
    for(const [key,p] of Object.entries(params)){
      const spec=specs[key];if(!spec)throw Error(`${v.indicator} 不支持参数 ${key}。`);
      if(spec.type==='string'){if(!spec.enum?.includes(p))throw Error(`${v.indicator}.${key} 取值必须来自 ${spec.enum?.join(' / ')}。`);}
      else if(!numeric(p)||(spec.type==='integer'&&!Number.isInteger(p))||(spec.minimum!=null&&p<spec.minimum)||(spec.maximum!=null&&p>spec.maximum))throw Error(`${v.indicator}.${key} 超出允许的数值范围。`);
    }
    if(v.indicator.startsWith('MACD_')&&(params.fast??specs.fast?.default)>=(params.slow??specs.slow?.default))throw Error('MACD 的 fast 必须小于 slow。');
  }
  function tree(root){let count=0;function visit(c,depth){if(++count>64||depth>8)throw Error('每棵条件树最多 64 个节点、8 层。');if(!object(c))throw Error('买入与卖出条件都必须填写。');if(['and','or'].includes(c.op)){if(Object.keys(c).some(k=>!['op','conditions'].includes(k))||!Array.isArray(c.conditions)||(c.conditions.length<2||c.conditions.length>16))throw Error('and / or 需要包含 2～16 项的 conditions 数组。');c.conditions.forEach(x=>visit(x,depth+1));}else{if(!['gt','gte','lt','lte','eq','ne','cross_above','cross_below'].includes(c.op)||Object.keys(c).some(k=>!['op','left','right'].includes(k)))throw Error('比较条件或字段不受支持。');value(c.left);value(c.right);}}visit(root,1);}
  try{tree(r.buy);tree(r.sell);return '';}catch(e){return e.message;}
}
const opLabels={gt:'>',gte:'≥',lt:'<',lte:'≤',eq:'=',ne:'≠',cross_above:'上穿',cross_below:'下穿'};
function explainCondition(c){if(!c)return '未填写';if(['and','or'].includes(c.op))return '('+c.conditions.map(explainCondition).join(c.op==='and'?' 且 ':' 或 ')+')';const val=v=>'value'in v?String(v.value):`${v.indicator}${Object.keys(v.params||{}).length?'('+Object.entries(v.params).map(([k,n])=>k+'='+n).join(', ')+')':''}${v.offset?'（前 '+v.offset+' 根）':''}`;return `${val(c.left)} ${opLabels[c.op]||c.op} ${val(c.right)}`;}
function conditionalPreview(item){const error=conditionalDrafts.get(item.id)?.error;if(error)return `<p class="dsl-error">${escape(error)} 修正前不能确认或保存。</p>`;return `<p>入场：${escape(explainCondition(item.rules.buy))}</p><p>离场：${escape(explainCondition(item.rules.sell))}</p><p>目标仓位 ${pct(item.rules.target_pct)}；持仓时卖出优先，均不触发则保持。所有条件在收盘判断，下一日开盘执行。</p>`;}
function conditionalFields(item){const draft=conditionalDrafts.get(item.id);return `<div class="conditional-editor"><label>常用条件预设<select data-field="conditional-preset"><option value="">选择预设会替换当前条件</option>${Object.entries(rulePresets).map(([key,p])=>`<option value="${key}">${escape(p.label)}</option>`).join('')}</select></label><div class="conditional-preview" role="status">${conditionalPreview(item)}</div><p class="helper">预设仓位为 50%。在高级编辑中调整指标、周期、仓位和止损。</p><details ${draft?.error?'open':''}><summary>高级编辑 · 条件 JSON</summary><label class="sr-only" for="dsl-${escape(item.id)}">指标条件 JSON</label><textarea id="dsl-${escape(item.id)}" class="conditional-json" data-field="conditional-json" spellcheck="false">${escape(draft?.text||JSON.stringify(item.rules,null,2))}</textarea><p class="helper">比较：gt / gte / lt / lte / eq / ne / cross_above / cross_below；组合：and / or。offset 仅引用过去日线，默认 0。指标参数与预热说明见上方目录。</p></details></div>`;}
function evidenceVersion(source,e){const original=source?.original_transcript||source?.transcript;const segment=Array.isArray(original)?original.find(s=>s.id===e.segment_id):null;if(e.transcript_version==='corrected'||e.text_version==='corrected'||e.version==='corrected'||(segment&&!segment.text.includes(e.quote)))return '校正稿引文 · 请对照原始转写';return '原文依据';}
function originalMarkup(s){const rules=s?.strategy?.rules||[];return rules.map(r=>`<p>${escape(r.text)}</p>${(r.evidence||[]).map(e=>`<blockquote>“${escape(e.quote)}” · ${escape(e.segment_id)} · ${evidenceVersion(s,e)}</blockquote>`).join('')}`).join('')||'<p>无原文规则；这是你自行编写的手工策略。</p>';}
function renderCandidates(){const term=q('#candidate-search').value.trim().toLowerCase();const rows=T.strategies.filter(s=>`${s.title} ${s.source_title||''} ${JSON.stringify(s.strategy)}`.toLowerCase().includes(term));q('#candidates').innerHTML=rows.length?rows.map(s=>`<article class="candidate"><h3>${escape(s.strategy?.title||s.title)}</h3>${s.source_title?`<p>来源资料：${escape(s.source_title)}</p>`:''}<p>草案版本 ${s.revision}${s.is_demo?' · 示例资料':''}${s.stale?' · 已过期，需重新提取':''}</p><details><summary>查看原规则与证据</summary>${originalMarkup(s)}</details><button class="secondary" data-add-source="${escape(s.id)}" ${s.stale?'disabled':''}>＋ 加入组合</button></article>`).join(''):`<p class="empty-copy">${term?'没有匹配草案。':'还没有策略草案。可先在资料区提取，或添加手工策略。'}</p>`;}
function dirty(){T.dirty=true;q('#portfolio-save-state').textContent='有未保存修改';q('#portfolio-readiness').innerHTML='<p class="pending-text">修改后需保存，重新检查版本就绪状态。</p>';updateWeights();}
function field(item,name,label,value,type='number',extra=''){return `<label>${label}<input data-field="${name}" type="${type}" value="${escape(value??'')}" ${extra}></label>`;}
function ruleFields(item){const r=item.rules;if(r?.type==='conditional')return conditionalFields(item);if(!r)return '<p class="rule-note">尚未绑定执行规则。请根据原文自行选择并填写；未支持的条件不要勉强映射。</p>';return `<div class="form-grid rule-fields">${r.type==='ma'?field(item,'fast','快均线（日）',r.fast,'number','min="1" max="250" step="1"')+field(item,'slow','慢均线（日）',r.slow,'number','min="2" max="250" step="1"'):field(item,'buy_below','买入线（价格 ≤）',r.buy_below,'number','min="0.001" step="any"')+field(item,'sell_above','卖出线（价格 ≥）',r.sell_above,'number','min="0.001" step="any"')}${field(item,'target_pct','目标仓位（%）',r.target_pct,'number','min="0.01" max="100" step="any"')}${field(item,'stop_loss_pct','收盘止损（%，可留空）',r.stop_loss_pct,'number','min="0.01" max="99.99" step="any"')}</div><p class="rule-note">${r.type==='ma'?'快均线高于慢均线时持有目标仓位，否则空仓。':'收盘低于等于买入线时持有目标仓位，高于等于卖出线时空仓，中间保持上次目标。'}收盘止损基于此策略最近开仓信号价，下一根开盘执行。</p>`;}
function aiMappingMarkup(item){
  if(!item.source_id)return '';
  const m=aiMappings.get(item.id),r=m?.result,stale=T.strategies.find(s=>s.id===item.source_id)?.stale;
  return `<div class="ai-mapping"><button type="button" class="secondary" data-ai-mapping="${escape(item.id)}" ${m?.loading||stale?'disabled':''}>${m?.loading?'AI 正在生成…':'AI 生成执行参数'}</button><p>${stale?'来源草案已过期，请重新选择最新草案。':'将该草案与证据发给已配置模型。建议会替换当前参数，仍需你核对并手动确认、保存。'}</p><div class="ai-mapping-feedback" role="status" aria-live="polite">${m?.message?`<p class="${m.error?'ai-error':''}">${escape(m.message)}</p>`:''}${r?`<p class="helper">${escape(r.provider)} / ${escape(r.model)} · 来源版本 ${escape(r.source_revision)}</p>${r.questions?.length?`<ul class="ai-questions">${r.questions.map(x=>`<li>${escape(x)}</li>`).join('')}</ul>`:''}${r.evidence?.length?`<details><summary>查看参数证据（${r.evidence.length}）</summary>${r.evidence.map(e=>`<p class="helper">${escape(e.field)} · ${escape(e.segment_id)} · ${evidenceVersion(item.source_snapshot,e)}</p><blockquote>“${escape(e.quote)}”</blockquote>`).join('')}</details>`:''}`:''}</div></div>`;
}
function renderMapping(item){const el=all('[data-item]').find(el=>el.dataset.item===item.id);if(!el)return;const old=el.querySelector('.ai-mapping');if(old)old.outerHTML=aiMappingMarkup(item);const confirm=el.querySelector('[data-field="confirmed"]');confirm.disabled=!!aiMappings.get(item.id)?.blocked||!!conditionalDrafts.get(item.id)?.error;confirm.checked=item.confirmed;}
function validMappingRules(r){
  if(r?.type==='conditional')return hasConditional()&&!conditionalError(r)?structuredClone(r):null;
  if(!r||!['ma','threshold'].includes(r.type))return null;
  const allowed=['type','target_pct','stop_loss_pct',...(r.type==='ma'?['fast','slow']:['buy_below','sell_above'])];
  if(Object.keys(r).some(key=>!allowed.includes(key)))return null;
  const number=v=>typeof v==='number'&&Number.isFinite(v);
  if(!number(r.target_pct)||r.target_pct<=0||r.target_pct>100)return null;
  if(r.stop_loss_pct!=null&&(!number(r.stop_loss_pct)||r.stop_loss_pct<=0||r.stop_loss_pct>=100))return null;
  const base={type:r.type,target_pct:r.target_pct,stop_loss_pct:r.stop_loss_pct??null};
  if(r.type==='ma'){if(!Number.isInteger(r.fast)||!Number.isInteger(r.slow)||r.fast<1||r.slow>250||r.fast>=r.slow)return null;return {...base,fast:r.fast,slow:r.slow};}
  if(!number(r.buy_below)||!number(r.sell_above)||r.buy_below<=0||r.sell_above<=r.buy_below)return null;
  return {...base,buy_below:r.buy_below,sell_above:r.sell_above};
}
async function generateMapping(item){
  if(!item?.source_id||aiMappings.get(item.id)?.loading)return;
  const controller=new AbortController(),m={loading:true,controller,message:'正在核对日线买卖条件、仓位和原文证据…'};
  aiMappings.set(item.id,m);renderMapping(item);
  const current=()=>aiMappings.get(item.id)===m&&T.items.includes(item)&&!controller.signal.aborted;
  try{
    const response=await fetch(`/api/ai/strategies/${encodeURIComponent(item.source_id)}/mapping`,{method:'POST',signal:controller.signal});
    const r=await response.json().catch(()=>null);if(!current())return;
    if(!response.ok)throw Error(typeof r?.detail==='string'?r.detail:`AI 参数生成失败（HTTP ${response.status}）`);
    if(!r||r.source_id!==item.source_id||r.source_revision!==item.source_snapshot?.revision)throw Error('来源版本已变化，此建议未回填。请刷新草案后重新选择。');
    const latest=await request('/strategies');if(!current())return;
    const source=latest.find(s=>s.id===item.source_id);
    if(!source||source.stale||source.revision!==r.source_revision)throw Error('来源草案已过期，此建议未回填。请刷新后重新选择。');
    if(!Array.isArray(r.questions)||r.questions.some(x=>typeof x!=='string')||!Array.isArray(r.evidence)||r.evidence.some(e=>!e||['field','segment_id','quote'].some(k=>typeof e[k]!=='string'))||typeof r.mapping_note!=='string')throw Error('AI 返回格式不完整，当前参数已保留。');
    const rules=validMappingRules(r.rules);
    if(r.ready===true&&!rules)throw Error('AI 返回了不支持或无效的执行规则，当前参数已保留。');
    T.strategies=latest;m.result=r;m.blocked=r.ready!==true||r.questions.length>0||!rules;
    item.confirmed=false;item.rules=m.blocked?null:rules;conditionalDrafts.delete(item.id);
    item.mapping_note=(r.mapping_note+(m.blocked&&r.questions.length?' 待核对：'+r.questions.join('；'):'')).slice(0,4000);
    m.message=m.blocked?'建议尚不完整，未绑定执行规则。请先处理缺项或不支持的条件。':'参数已回填，尚未确认、未保存。请核对原文与证据后手动确认。';
    m.error=m.blocked;dirty();
    const editor=all('[data-item]').find(el=>el.dataset.item===item.id);
    if(editor){editor.querySelector('[data-field="rule-type"]').value=item.rules?.type||'';editor.querySelector('.rule-editor').innerHTML=ruleFields(item);editor.querySelector('[data-field="mapping_note"]').value=item.mapping_note;}
  }catch(e){if(current()){m.message=e.name==='AbortError'?'请求已取消。':e.message||'AI 服务连接失败，当前参数已保留。';m.error=true;}}
  finally{if(current()){m.loading=false;renderMapping(item);}}
}
function renderItems(){q('#portfolio-items').innerHTML=T.items.length?T.items.map(item=>`<article class="portfolio-item ${item.enabled?'':'item-disabled'}" data-item="${escape(item.id)}"><div class="item-heading"><label class="check"><input data-field="enabled" type="checkbox" ${item.enabled?'checked':''}>启用 · ${escape(item.name)}</label><button data-remove="${escape(item.id)}" class="quiet">移除</button></div><details class="source-rule"><summary>${item.source_id?'原草案与证据快照':'手工策略 · 自行编写'}${item.source_snapshot?.revision?` · v${item.source_snapshot.revision}`:''}</summary>${originalMarkup(item.source_snapshot)}</details>${aiMappingMarkup(item)}${field(item,'name','策略名称',item.name,'text','maxlength="100"')}<label>执行规则<select data-field="rule-type"><option value="">未绑定 · 请明确选择</option><option value="ma" ${item.rules?.type==='ma'?'selected':''}>快慢均线趋势</option><option value="threshold" ${item.rules?.type==='threshold'?'selected':''}>价格阈值</option>${hasConditional()||item.rules?.type==='conditional'?`<option value="conditional" ${item.rules?.type==='conditional'?'selected':''}>指标条件组合（预设 / 高级编辑）</option>`:''}</select></label><div class="rule-editor">${ruleFields(item)}</div><label>权重（%）<div class="weight-input"><input aria-label="${escape(item.name)}权重滑杆" type="range" min="0" max="100" step="0.1" data-field="weight-range" value="${item.weight}" ${q('#portfolio-mode').value==='equal'?'disabled':''}><input aria-label="${escape(item.name)}权重百分比" data-field="weight" type="number" min="0" max="100" step="any" value="${item.weight}" ${q('#portfolio-mode').value==='equal'?'disabled':''}></div></label><label>映射说明<input data-field="mapping_note" value="${escape(item.mapping_note)}" placeholder="说明原文如何映射；未覆盖条件需先解决"></label><label class="check"><input data-field="confirmed" type="checkbox" ${item.confirmed?'checked':''} ${aiMappings.get(item.id)?.blocked||conditionalDrafts.get(item.id)?.error?'disabled':''}>我已核对原文、全部参数与条件，确认此映射可执行</label></article>`).join(''):'<p class="empty-copy">添加草案或手工策略，开始建立组合。</p>';updateWeights();}
function updateWeights(){const enabled=T.items.filter(i=>i.enabled);const total=enabled.reduce((n,i)=>n+Number(i.weight||0),0);q('#weight-total').textContent=enabled.length?`${enabled.length} 项启用 · ${q('#portfolio-mode').value==='equal'?`各占 ${pct(100/enabled.length)}`:`合计 ${pct(total)}`}`:'尚无启用策略';}
function renderReadiness(p){const r=p.readiness;q('#portfolio-readiness').innerHTML=`<div class="readiness ${r.ready?'':'bad'}"><strong>${r.ready?'此版本已就绪':'此版本尚不能运行'} · v${p.revision}</strong>${r.errors.length?`<ul>${r.errors.map(x=>`<li>${escape(x)}</li>`).join('')}</ul>`:''}${r.warnings.map(x=>`<p>${escape(x)}</p>`).join('')}</div>`;}
function editPortfolio(p){cancelMappings();conditionalDrafts.clear();T.portfolio=p;T.items=structuredClone(p?.items||[]);q('#portfolio-name').value=p?.name||'';q('#portfolio-mode').value=p?.mode||'equal';q('#conflict-policy').value=p?.conflict_policy||'block';T.dirty=false;q('#portfolio-save-state').textContent=p?`已保存 · v${p.revision}`:'新组合 · 未保存';q('#portfolio-select').value=p?.id||'';q('#portfolio-readiness').innerHTML='';if(p)renderReadiness(p);renderItems();}
function allowPortfolioLeave(){return !T.dirty||window.confirm('当前组合有未保存修改，确定放弃并切换组合吗？');}
q('#candidate-search').addEventListener('input',renderCandidates);
q('#candidates').addEventListener('click',e=>{const b=e.target.closest('[data-add-source]');if(!b)return;const s=T.strategies.find(x=>x.id===b.dataset.addSource);addItem(s);});
function addItem(s){if(T.items.length>=20){notify('每个组合最多 20 项策略。',true);return;}T.items.push({id:uid(),name:s?.strategy?.title||s?.title||`手工策略 ${T.items.length+1}`,source_id:s?.id||null,source_snapshot:s||null,enabled:true,weight:0,confirmed:false,mapping_note:'',rules:null});dirty();renderItems();}
wire('add-manual',()=>addItem());
q('#portfolio-items').addEventListener('click',e=>{const ai=e.target.closest('[data-ai-mapping]');if(ai){generateMapping(T.items.find(x=>x.id===ai.dataset.aiMapping));return;}const b=e.target.closest('[data-remove]');if(b){const item=T.items.find(x=>x.id===b.dataset.remove);if(item)invalidateMapping(item);T.items=T.items.filter(x=>x.id!==b.dataset.remove);dirty();renderItems();}});
q('#portfolio-items').addEventListener('input',e=>{
  const f=e.target.dataset.field;if(!f)return;const el=e.target.closest('[data-item]'),item=T.items.find(x=>x.id===el.dataset.item);let v=e.target.type==='checkbox'?e.target.checked:e.target.value;
  if(!item)return;const mapping=aiMappings.get(item.id);if(mapping?.loading){invalidateMapping(item);aiMappings.set(item.id,{message:'你已修改此策略，之前的 AI 请求已取消；需要时可重新生成。'});}else if(mapping?.blocked&&['rule-type','mapping_note','fast','slow','buy_below','sell_above','target_pct','stop_loss_pct'].includes(f))invalidateMapping(item);
  if(f==='rule-type'){conditionalDrafts.delete(item.id);item.rules=v==='conditional'?presetRules('rsi'):v?{type:v,target_pct:null,stop_loss_pct:null,...(v==='ma'?{fast:null,slow:null}:{buy_below:null,sell_above:null})}:null;el.querySelector('.rule-editor').innerHTML=ruleFields(item);}
  else if(f==='conditional-preset'){if(!v)return;invalidateMapping(item);conditionalDrafts.delete(item.id);item.rules=presetRules(v);el.querySelector('.rule-editor').innerHTML=ruleFields(item);notify(rulePresets[v].note);}
  else if(f==='conditional-json'){invalidateMapping(item);let error='',parsed;try{if(v.length>24000)throw Error('条件 JSON 过长。');parsed=JSON.parse(v);error=conditionalError(parsed);}catch(e){error=e.message;}conditionalDrafts.set(item.id,{text:v,error});if(!error)item.rules=parsed;el.querySelector('.conditional-preview').innerHTML=conditionalPreview(item);}
  else if(['enabled','confirmed','name','mapping_note'].includes(f))item[f]=v;
  else if(f==='weight'||f==='weight-range'){item.weight=v===''?0:Number(v);el.querySelector('[data-field="weight"]').value=item.weight;el.querySelector('[data-field="weight-range"]').value=item.weight;}
  else if(item.rules)item.rules[f]=v===''?null:Number(v);
  if(!['enabled','confirmed','weight','weight-range'].includes(f)){item.confirmed=false;el.querySelector('[data-field="confirmed"]').checked=false;}
  if(f==='enabled')el.classList.toggle('item-disabled',!item.enabled);dirty();renderMapping(item);
});
for(const id of ['portfolio-name','conflict-policy'])q('#'+id).addEventListener('input',dirty);
q('#portfolio-mode').addEventListener('change',()=>{dirty();renderItems();});
q('#portfolio-select').addEventListener('change',e=>{if(allowPortfolioLeave())editPortfolio(T.portfolios.find(p=>p.id===e.target.value));else e.target.value=T.portfolio?.id||'';});
wire('new-portfolio',()=>{if(allowPortfolioLeave())editPortfolio(null);});
function normalize(equal){const rows=T.items.filter(i=>i.enabled);const total=rows.reduce((n,i)=>n+i.weight,0);let used=0;rows.forEach((i,k)=>{i.weight=k===rows.length-1?Number((100-used).toFixed(6)):Number((equal||!total?100/rows.length:i.weight/total*100).toFixed(6));used+=i.weight;});dirty();renderItems();}
wire('equal-weights',()=>normalize(true));wire('normalize-weights',()=>normalize(false));
wire('save-portfolio',async()=>{
  if(T.items.some(i=>conditionalDrafts.get(i.id)?.error))throw Error('请先修正条件 JSON 中的错误，再保存组合。');
  cancelMappings();renderItems();
  const name=q('#portfolio-name').value.trim();if(!name)throw Error('请填写组合名称。');
  const body={name,mode:q('#portfolio-mode').value,conflict_policy:q('#conflict-policy').value,items:T.items.map(({source_snapshot,effective_weight,...item})=>item)};
  if(T.portfolio)body.revision=T.portfolio.revision;
  const p=await request('/portfolios'+(T.portfolio?'/'+T.portfolio.id:''),body,T.portfolio?'PUT':'POST');
  editPortfolio(p);T.portfolios=await request('/portfolios');fillSelects();notify(`组合已保存为 v${p.revision}。${p.readiness.ready?'可用于回测与模拟。':'请处理就绪检查中的问题。'}`);
});
wire('refresh-trading',async()=>{await load(true);if(T.portfolio&&!T.dirty){const p=await request('/portfolios/'+T.portfolio.id);editPortfolio(p);}notify('草案与已保存组合已刷新。');});
function costsMarkup(prefix){return `<details class="cost-settings"><summary>费用与滑点假设（可调整）</summary><div class="form-grid"><label>佣金（基点 / 万分之一）<input id="${prefix}-commission" type="number" min="0" max="100" step="any" value="3" required></label><label>单笔最低佣金（${prefix==='research'?'计价单位':'元'}）<input id="${prefix}-minimum" type="number" min="0" max="1000" step="any" value="5" required></label><label>卖出税费（基点）<input id="${prefix}-tax" type="number" min="0" max="100" step="any" value="5" required></label><label>滑点（基点）<input id="${prefix}-slippage" type="number" min="0" max="100" step="any" value="0" required></label></div><p>这是本次运行的明确假设，不是自动更新的税费规则。买入按 100 股整手，T+1；限价、停牌和无量会保守阻止成交。</p></details>`;}
for(const p of ['backtest','paper','research'])q('#'+p+'-costs').innerHTML=costsMarkup(p);
const dateContexts=new Map();
for(const prefix of ['backtest','research']){
  q('#'+prefix+'-costs').insertAdjacentHTML('beforebegin',`<fieldset class="backtest-dates"><legend>回测日期（含起止日）</legend><div class="form-grid"><label>开始日期<input id="${prefix}-start-date" type="date" required></label><label>结束日期<input id="${prefix}-end-date" type="date" required></label></div><p id="${prefix}-date-help" class="helper">选择数据后，以实际覆盖范围填入日期。</p></fieldset>`);
  for(const suffix of ['start-date','end-date'])q('#'+prefix+'-'+suffix).addEventListener('input',()=>validateDates(prefix));
}
function dateCoverage(prefix){
  const d=T.datasets.find(d=>d.id===q('#'+prefix+'-dataset').value),symbol=q('#'+prefix+'-symbol').value.trim().toUpperCase();
  const s=d?.symbol_metadata?.find(s=>s.symbol===symbol);
  return {key:`${d?.id||''}:${symbol}`,start:s?.start_date||d?.start_date||'',end:s?.end_date||d?.end_date||''};
}
function syncDates(prefix){
  const range=dateCoverage(prefix),previous=dateContexts.get(prefix),start=q('#'+prefix+'-start-date'),end=q('#'+prefix+'-end-date');
  const changed=previous?.key!==range.key;
  for(const el of [start,end]){el.min=range.start;el.max=range.end;el.disabled=!range.start||!range.end;}
  if(changed||!start.value)start.value=range.start;
  if(changed||!end.value)end.value=range.end;
  dateContexts.set(prefix,range);
  q('#'+prefix+'-date-help').textContent=range.start?`可用范围：${range.start} ～ ${range.end}。`:'选择有数据的标的后，以实际覆盖范围填入日期。';
  validateDates(prefix);
}
function validateDates(prefix){
  const start=q('#'+prefix+'-start-date'),end=q('#'+prefix+'-end-date');
  end.setCustomValidity(start.value&&end.value&&start.value>end.value?'结束日期不能早于开始日期。':'');
  return start.checkValidity()&&end.checkValidity()&&!start.disabled&&!end.disabled;
}
function runDates(prefix){
  if(prefix==='paper')return {};
  if(!validateDates(prefix))throw Error('请选择数据覆盖内的有效起止日期，结束日期不能早于开始日期。');
  return {start_date:q('#'+prefix+'-start-date').value,end_date:q('#'+prefix+'-end-date').value};
}
q('#research-costs .cost-settings p').textContent='费用与滑点为本次研究假设，非自动更新的税费规则。复权价格与简化撮合不能复现真实市场执行。';
function backtestMode(){const research=q('#backtest-mode').value==='research';q('#research-workflow').hidden=!research;q('#strict-workflow').hidden=research;q('#backtest-mode-help').textContent=research?'按名称或代码从批量数据集中选择一只股票，使用你的组合研究复权历史表现。':'严格 CSV 仅接受沪深主板普通股票、未复权价格和官方每日限价；需要你核实区间内无公司行为。';}
q('#backtest-mode').addEventListener('change',backtestMode);backtestMode();
function researchRuleNote(){const p=T.portfolios.find(x=>x.id===q('#research-portfolio').value);q('#research-rule-note').textContent=p&&!p.readiness.ready?`此版本尚未就绪：${p.readiness.errors.join('；')}。请在策略组合页处理后保存。`:p?.items.some(i=>i.enabled&&i.rules?.type==='threshold')?'此组合包含绝对价格阈值。阈值将直接用于复权价格，请核对其价格口径；系统不会自动换算为真实交易价格。':'';}
q('#research-portfolio').addEventListener('change',()=>{researchRuleNote();updateResearchControls();});
function selectedResearch(){return T.datasets.find(d=>isResearch(d)&&d.id===q('#research-dataset').value);}
function countItems(value){return value==null?'未报告':Array.isArray(value)?value.length:Number(value);}
function missingList(value){return Array.isArray(value)&&value.length?`<p>${value.map(x=>escape(typeof x==='string'?x:[x.symbol,x.name,x.reason||x.error].filter(Boolean).join(' · '))).join('；')}</p>`:'';}
function researchGaps(s){return s?.missing_day_count==null?'':`<p class="${s.missing_day_count?'result-warning':'helper'}">相对已取得交易日历：缺失 ${escape(s.missing_day_count)} 日，区间内部缺口 ${escape(s.internal_gap_count??'未报告')} 日。${s.missing_start?'起点覆盖不足。':''}${s.missing_tail?'尾部数据缺失。':''}缺失行情不补价格。</p>`;}
function researchMetadata(d,symbol){
  const c=d.coverage||{},u=d.universe||{},p=d.provenance||{},s=(d.symbol_metadata||[]).find(x=>x.symbol===symbol);
  const status={complete:'覆盖完整',complete_observed_calendar:'覆盖已取得交易日历',partial:'覆盖不完整',incomplete:'覆盖不完整',unavailable:'暂无数据'}[c.status]||c.status||'尚未提供完整性结论';
  return `<dl class="research-facts"><div><dt>${s?'所选股票实际区间':'数据集实际区间'}</dt><dd>${escape(s?.start_date||c.actual_start_date||d.start_date||'未知')} ～ ${escape(s?.end_date||c.actual_end_date||d.end_date||'未知')}</dd></div><div><dt>股票池快照日期</dt><dd>${escape(u.as_of_date||'未提供')} · ${escape(u.name||'沪深300')}</dd></div><div><dt>价格口径</dt><dd>前复权 · 研究虚拟份额</dd></div><div><dt>抓取来源</dt><dd>${escape(p.provider||d.source||'未提供')}</dd></div><div><dt>抓取时间</dt><dd>${escape(stamp(p.fetched_at))}</dd></div><div><dt>完整性</dt><dd>${escape(status)}</dd></div></dl><div class="research-coverage"><span><strong>${d.symbols.length}</strong> 只股票有数据</span><span><strong>${countItems(c.failed_symbols)}</strong> 只获取失败</span><span><strong>${countItems(c.missing_tail_symbols)}</strong> 只尾部缺失</span><span>${Number(s?.row_count??d.row_count).toLocaleString('zh-CN')} 行${s?' · 所选标的':''}</span></div><p class="result-warning">${u.survivorship_bias?'按快照股票池回看历史，存在存活偏差，不能等同各历史时点的沪深300成分。':'股票池按所载元数据使用；历史成分变动未自动回溯。'}</p>${researchGaps(s)}<details class="research-provenance"><summary>查看来源、请求范围与缺失说明</summary><p>请求起点：${escape(d.requested_start_date||'未提供')}；请求截止（不含当日）：${escape(d.requested_end_date_exclusive||'未提供')}。已核实日历截止：${escape(d.expected_end_date||c.calendar_end_date||'未取得可核实日历')}。</p><p>股票池来源：${escape(u.source||'未提供')}</p>${missingList(c.failed_symbols)}${missingList(c.missing_tail_symbols)}<ul>${(d.warnings||[]).map(w=>`<li>${escape(w)}</li>`).join('')}</ul><p>数据版本：${escape(d.id)}<br>清单校验：${escape(p.manifest_hash||'未提供')}</p></details>`;
}
function renderResearchCatalog(){
  const rows=T.datasets.filter(isResearch),current=q('#research-dataset').value;
  options(q('#research-dataset'),rows,'请选择批量数据集',d=>`${d.name} · ${d.symbols.length} 只股票有数据`,rows.some(d=>d.id===current)?current:rows[0]?.id||'');
  q('#research-dataset-label').hidden=!rows.length;
  q('#research-status').innerHTML=rows.length?'':`<div class="readiness"><strong>尚未导入沪深300研究数据</strong><p>当前本机没有可用的批量研究数据。导入完成后刷新此目录即可按名称或代码选股；实际范围将在这里显示。</p><p>已有 CSV 或演示行情可在上方切换到“严格撮合”。</p></div>`;
  const d=selectedResearch();q('#research-data-summary').innerHTML=d?`<p class="dataset-overview"><strong>${d.symbols.length} 只股票可用</strong><span>${escape(d.start_date)} ～ ${escape(d.end_date)}</span><span class="pill">前复权研究数据</span></p><details class="inline-details"><summary>数据来源与覆盖详情</summary>${researchMetadata(d)}</details>`:'';
  if(!d?.symbols.includes(q('#research-symbol').value))q('#research-symbol').value='';
  q('#research-stock-picker').disabled=!d;renderStocks();syncDates('research');
}
function researchStocks(d){
  if(!d)return[];const meta=d.symbol_metadata||[],rows=meta.map(s=>({...s,available:d.symbols.includes(s.symbol)}));
  for(const symbol of d.symbols)if(!rows.some(s=>s.symbol===symbol))rows.push({symbol,name:'名称未提供',available:true});
  for(const item of Array.isArray(d.coverage?.failed_symbols)?d.coverage.failed_symbols:[]){const s=typeof item==='string'?{symbol:item}:item;if(s.symbol&&!rows.some(r=>r.symbol===s.symbol))rows.push({...s,available:false});}
  return rows;
}
function renderStocks(){
  const d=selectedResearch(),term=q('#research-stock-search').value.trim().toLowerCase(),only=q('#research-available-only').checked,selected=q('#research-symbol').value;
  const matches=researchStocks(d).filter(s=>(!only||s.available)&&`${s.name||''} ${s.symbol}`.toLowerCase().includes(term));
  q('#research-stock-count').textContent=d?`找到 ${matches.length} 只 · 当前显示 ${Math.min(stockLimit,matches.length)} 只`:'';
  q('#research-stocks').innerHTML=matches.slice(0,stockLimit).map(s=>`<button class="stock-option" type="button" data-research-symbol="${escape(s.symbol)}" aria-pressed="${s.symbol===selected}" ${s.available?'':'disabled'}><strong>${escape(s.name||'名称未提供')}</strong><span>${escape(s.symbol)}${s.available?'':' · 无可用数据'}</span></button>`).join('')||(d?'<p class="empty-copy">没有匹配股票，请换一个名称或代码。</p>':'');
  q('#research-more').hidden=matches.length<=stockLimit;
  const s=researchStocks(d).find(x=>x.symbol===selected);
  q('#research-selection').innerHTML=s?`<strong>已选 ${escape(s.name||'')} · ${escape(s.symbol)}</strong><p>实际区间：${escape(s.start_date||'未提供')} ～ ${escape(s.end_date||'未提供')} · ${s.row_count??'未知'} 行</p>${researchGaps(s)}`:'尚未选择标的。';updateResearchControls();
}
function updateResearchControls(){const p=T.portfolios.find(x=>x.id===q('#research-portfolio').value);q('#run-research').disabled=researchBusy||!selectedResearch()?.symbols.includes(q('#research-symbol').value)||!p?.readiness.ready;}
q('#research-dataset').addEventListener('change',()=>{q('#research-symbol').value='';stockLimit=24;renderResearchCatalog();});
for(const id of ['research-stock-search','research-available-only'])q('#'+id).addEventListener('input',()=>{stockLimit=24;renderStocks();});
q('#research-stocks').addEventListener('click',e=>{const b=e.target.closest('[data-research-symbol]');if(!b)return;const symbol=b.dataset.researchSymbol,scroll=q('#research-stocks').scrollTop;q('#research-symbol').value=symbol;renderStocks();syncDates('research');q('#research-stocks').scrollTop=scroll;q(`[data-research-symbol="${CSS.escape(symbol)}"]`)?.focus({preventScroll:true});});
wire('research-more',()=>{stockLimit+=24;renderStocks();});
wire('refresh-research',async()=>{await load(true);notify('已刷新本机研究数据与已保存组合。');});
q('#research-form').addEventListener('submit',e=>{e.preventDefault();task(e.submitter,async()=>{researchBusy=true;updateResearchControls();q('#research-progress').textContent='正在计算复权研究结果…';try{const r=await request('/backtests',runBody('research'));T.runs=await request('/backtests');fillSelects();q('#research-history').value=r.id;renderRun(r,'research-result');revealResult('research-result');notify('研究回测完成，盈亏与参数已保存。');}finally{researchBusy=false;q('#research-progress').textContent='';updateResearchControls();}});});
q('#research-history').addEventListener('change',e=>task(null,async()=>{if(e.target.value){renderRun(await request('/backtests/'+e.target.value),'research-result');revealResult('research-result');}else q('#research-result').innerHTML='<p class="empty-copy">选择研究运行记录，查看已保存结果。</p>';}));
function runBody(prefix){const p=T.portfolios.find(p=>p.id===q('#'+prefix+'-portfolio').value);if(!p)throw Error('请先选择已保存组合。');return{portfolio_id:p.id,portfolio_revision:p.revision,dataset_id:q('#'+prefix+'-dataset').value||null,symbol:q('#'+prefix+'-symbol').value.trim().toUpperCase(),...runDates(prefix),initial_cash:Number(q('#'+prefix+'-cash').value),costs:{commission_bps:Number(q('#'+prefix+'-commission').value),min_commission:Number(q('#'+prefix+'-minimum').value),sell_tax_bps:Number(q('#'+prefix+'-tax').value),slippage_bps:Number(q('#'+prefix+'-slippage').value)}};}
async function addedDataset(d){T.datasets=await request('/datasets');fillSelects();q('#backtest-dataset').value=d.id;q('#paper-dataset').value=d.id;q('#paper-sync-dataset').value=d.id;q('#backtest-symbol').value=d.symbols[0];syncDates('backtest');q('#dataset-feedback').innerHTML=`<div class="readiness"><strong>${d.is_demo?'演示行情已载入':'真实 CSV 已导入'}</strong><p>${escape(dataLabel(d))} · 来源：${escape(d.source)} · 未复权</p>${d.warnings.map(w=>`<p>${escape(w)}</p>`).join('')}</div>`;}
wire('demo-dataset',async()=>addedDataset(await request('/datasets/demo',{})));
wire('import-dataset',async()=>{const f=q('#dataset-file').files[0];if(!f)throw Error('请选择 CSV 文件。');if(f.size>1.5*1024*1024)throw Error('CSV 超过 1.5 MB，请缩小区间。');if(!q('#ordinary-stock').checked||!q('#no-actions').checked)throw Error('请核实并确认证券范围、未复权和公司行为条件。');await addedDataset(await request('/datasets/import',{name:q('#dataset-name').value.trim()||f.name,source:q('#dataset-source').value.trim(),csv_text:await f.text(),market:'CN_A_MAIN',price_basis:'raw',is_demo:false,ordinary_stock_confirmed:true,corporate_actions_confirmed_absent:true}));});
q('#backtest-dataset').addEventListener('change',()=>{const d=T.datasets.find(d=>d.id===q('#backtest-dataset').value);if(d)q('#backtest-symbol').value=d.symbols[0];syncDates('backtest');});
q('#backtest-symbol').addEventListener('change',()=>syncDates('backtest'));
q('#backtest-form').addEventListener('submit',e=>{e.preventDefault();task(e.submitter,async()=>{q('#backtest-progress').textContent='正在计算…';try{const r=await request('/backtests',runBody('backtest'));T.runs=await request('/backtests');fillSelects();q('#backtest-history').value=r.id;renderRun(r,'backtest-result');revealResult('backtest-result');notify('回测已完成，结果与参数已保存在本机。');}finally{q('#backtest-progress').textContent='';}});});
q('#backtest-history').addEventListener('change',e=>task(null,async()=>{if(e.target.value){renderRun(await request('/backtests/'+e.target.value),'backtest-result');revealResult('backtest-result');}else q('#backtest-result').innerHTML='<p class="empty-copy">选择已完成的回测，查看保存的盈亏与成交记录。</p>';}));
function modeHelp(){q('#paper-mode-help').textContent=q('#paper-mode').value==='replay'?'逐日回放历史行情，可单步或连续运行。':'根据新收到的已收盘日线生成信号，下一交易日开盘模拟撮合。';q('#paper-feed').disabled=q('#paper-mode').value==='replay';if(q('#paper-mode').value==='replay')q('#paper-feed').value='csv';}
q('#paper-mode').addEventListener('change',modeHelp);modeHelp();
q('#paper-external-jump').addEventListener('click',()=>{const title=q('#pex-title');if(title){title.tabIndex=-1;title.focus({preventScroll:true});title.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}});
q('#paper-form').addEventListener('submit',e=>{e.preventDefault();task(e.submitter,async()=>{const s=await request('/paper/sessions',{...runBody('paper'),name:q('#paper-name').value.trim(),mode:q('#paper-mode').value,feed:q('#paper-feed').value,max_age_days:Number(q('#paper-age').value)});T.sessions=await request('/paper/sessions');fillSelects();showSession(s);revealResult('paper-result');notify('本地模拟账户已创建，当前暂停。');});});
q('#paper-history').addEventListener('change',e=>task(null,async()=>{if(e.target.value)showSession(await request('/paper/sessions/'+e.target.value));else{T.session=null;q('#paper-controls').hidden=true;q('#paper-result').innerHTML='<p class="empty-copy">请选择模拟账户。</p>';}}));
function showSession(s){if(T.session?.id!==s.id||s.mode==='replay')q('#paper-sync-dataset').value=s.dataset_id||'';T.session=s;q('#paper-history').value=s.id;q('#paper-controls').hidden=false;renderRun(s,'paper-result');updateControls();scheduleRefresh();}
function updateControls(){if(!T.session)return;const s=T.session;q('#paper-start').disabled=T.busy||s.status==='running';q('#paper-pause').disabled=T.busy||s.status!=='running';q('#paper-step').disabled=T.busy||s.status!=='paused'||s.mode!=='replay';q('#paper-sync').disabled=T.busy||s.status!=='running';q('#paper-sync-dataset').disabled=s.mode==='replay'||s.feed==='tushare';q('#paper-sync').textContent=s.mode==='replay'?'同步下一根（数据已冻结）':'立即同步';}
async function command(cmd){if(!T.session)return;T.busy=true;updateControls();try{const body=['step','sync'].includes(cmd)?{request_id:uid(),...(cmd==='sync'?{dataset_id:T.session.mode==='replay'||T.session.feed==='tushare'?null:q('#paper-sync-dataset').value||null}:{})}:{};showSession(await request(`/paper/sessions/${T.session.id}/${cmd}`,body));}finally{T.busy=false;updateControls();}}
for(const cmd of ['start','pause','step','sync'])wire('paper-'+cmd,()=>command(cmd));
wire('refresh-paper',async()=>{T.sessions=await request('/paper/sessions');fillSelects();if(T.session)showSession(await request('/paper/sessions/'+T.session.id));});
function scheduleRefresh(){clearTimeout(T.poll);if(T.workspace!=='paper'||!T.session)return;T.poll=setTimeout(async()=>{try{if(!T.busy)showSession(await request('/paper/sessions/'+T.session.id));}catch{q('#paper-result .session-status')?.setAttribute('data-disconnected','true');notify('模拟盘状态刷新失败，请检查本地服务。当前显示上次取得的记录。',true);}finally{scheduleRefresh();}},5000);}
function table(title,headers,rows){return `<section class="result-section"><h3>${title}</h3>${rows.length?`<div class="table-wrap" tabindex="0" role="region" aria-label="${title}，可横向滚动"><table class="ledger-table"><thead><tr>${headers.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((v,i)=>`<td${i===row.length-1?' class="reason-cell"':''}>${escape(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<p class="helper">暂无记录。</p>'}</section>`;}
function chart(equity,research=false){
  if(!equity.length)return '<p class="helper">处理行情后显示净值曲线。</p>';
  if(equity.length===1)return `<figure class="equity-chart"><figcaption>${research?'研究净值（计价单位）':'账户净值（元）'}</figcaption><p class="chart-single"><strong>${money(equity[0].equity)}</strong><span>${escape(equity[0].date)} / 已处理 1 根日线</span></p></figure>`;
  const vals=equity.map(e=>e.equity),min=Math.min(...vals),max=Math.max(...vals),span=max-min||Math.max(1,max*.01),lo=min-span*.08,hi=max+span*.08;
  const x=i=>4+i/Math.max(1,vals.length-1)*792,y=v=>194-(v-lo)/(hi-lo)*188;
  const points=vals.map((v,i)=>`${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ');
  return `<figure class="equity-chart"><figcaption>${research?'研究净值（计价单位）':'账户净值（元）'}</figcaption><div class="chart-stage"><div class="chart-scale" aria-hidden="true"><span>${money(hi)}</span><span>${money(lo)}</span></div><svg viewBox="0 0 800 200" preserveAspectRatio="none" role="img" aria-label="${research?'研究':'账户'}净值从 ${money(vals[0])} 到 ${money(vals.at(-1))}，完整数据见净值明细"><line class="chart-guide" x1="0" y1="198" x2="800" y2="198"/>${vals.length===1?`<circle class="chart-point" cx="${x(0)}" cy="${y(vals[0])}" r="3"/>`:`<polyline class="chart-line" vector-effect="non-scaling-stroke" points="${points}"/>`}</svg></div><div class="chart-dates"><span>${escape(equity[0].date)}</span><span>${escape(equity.at(-1).date)}</span></div></figure>`;
}
function revealResult(target){const result=q('#'+target),heading=result.querySelector('h2');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});result.scrollIntoView({block:'start',behavior:'instant'});}}
function periodSummary(r,research){
  const known=v=>typeof v==='number'&&Number.isFinite(v),m=r.metrics||{};
  const initial=[r.initial_equity,m.initial_equity,r.initial_cash].find(known);
  const final=[r.final_equity,m.final_equity,r.equity?.at(-1)?.equity].find(known);
  const pnl=[r.pnl,m.pnl,known(final)&&known(initial)?final-initial:null].find(known);
  const totalReturn=[m.total_return_pct,known(pnl)&&initial>0?pnl/initial*100:null].find(known);
  const unit=research?'':'¥',amount=v=>known(v)?unit+money(v):'尚无估值';
  const from=r.actual_start_date||r.equity?.[0]?.date,to=r.actual_end_date||r.equity?.at(-1)?.date;
  const requested=r.requested_start_date||r.requested_end_date;
  const tone=known(pnl)?pnl>0?'positive':pnl<0?'negative':'neutral':'neutral';
  return `<section class="period-summary" aria-label="阶段回测结果"><dl class="metrics primary-metrics"><div class="metric-emphasis ${tone}"><dt>阶段盈亏${research?'（研究计价单位）':'（元）'}</dt><dd>${known(pnl)&&pnl>0?'+':''}${amount(pnl)}</dd></div><div class="metric-emphasis ${tone}"><dt>阶段收益率</dt><dd>${known(totalReturn)?`${totalReturn>0?'+':''}${pct(totalReturn)}`:'尚无估值'}</dd></div><div><dt>初始资产${research?'（研究计价单位）':'（元）'}</dt><dd>${amount(initial)}</dd></div><div><dt>${r.kind==='paper'?'当前':'结束'}资产${research?'（研究计价单位）':'（元）'}</dt><dd>${amount(final)}</dd></div></dl><p class="period-range"><strong>${r.kind==='paper'?'已处理行情区间':'实际回测区间'}</strong><span>${escape(from||'尚无行情')} ～ ${escape(to||'尚无行情')}</span></p><details class="inline-details" data-detail="calculation"><summary>盈亏计算口径</summary>${requested?`<p>所选日期：${escape(r.requested_start_date||'数据起点')} ～ ${escape(r.requested_end_date||'数据终点')}</p>`:''}<p>盈亏 = 结束资产 − 初始资产，含持仓估值和已记费用；结束日不强制平仓。${Number.isInteger(r.warmup_bars)?`起日前 ${r.warmup_bars} 根日线仅供指标预热。`:''}${research?'复权研究计价金额不代表可兑现的交易收益。':''}</p></details></section>`;
}
function renderRun(r,target){
  // Refresh only result content, preserving any open detail sections and keyboard focus.
  const container=q('#'+target),open=[...container.querySelectorAll('details[open]')].map(d=>d.dataset.detail),focused=container.contains(document.activeElement)?document.activeElement.closest('details')?.dataset.detail:null;
  const research=isResearchRun(r),replay=r.kind==='paper'&&r.mode==='replay',c=r.costs,m=r.metrics,feed={waiting:'等待行情',fresh:'行情可用',stale:'行情已过期',exhausted:'回放已结束',error:'行情错误',paused:'暂停'};
  const unit=research?'':'¥',quantity=v=>research?Number(v).toLocaleString('zh-CN',{maximumFractionDigits:6}):v;
  const status=r.kind==='paper'?`<div class="session-status" role="status"><strong>${r.status==='running'?'运行中':'已暂停'} / ${escape(feed[r.feed_status]||r.feed_status)}</strong><p>${escape(r.message)}</p><details class="inline-details" data-detail="session"><summary>行情与同步时间</summary><div class="session-meta"><span>最新行情：${escape(r.last_quote_at||'尚未取得')}</span><span>已处理至：${escape(r.cursor||'尚未开始')}</span><span>上次连接：${escape(stamp(r.heartbeat_at))}</span></div></details></div>`:'';
  const snapshot=r.portfolio_snapshot;
  container.innerHTML=`<div class="result-heading"><h2>${escape(r.name||snapshot.name)}</h2><div class="result-meta"><span>${escape(r.symbol)}</span><span>组合版本 v${r.portfolio_revision}</span><span class="pill">${research?'前复权研究 / 非可交易收益':replay?'本地历史回放':r.kind==='paper'?'本地增量模拟':'历史回测'}</span>${r.is_demo?'<span class="pill">演示行情 / 非真实市场结果</span>':''}</div></div>${periodSummary(r,research)}${status}<dl class="metrics secondary-metrics"><div><dt>最大回撤</dt><dd>${pct(m.max_drawdown_pct)}</dd></div><div><dt>${research?'研究费用':'交易费用'}</dt><dd>${unit}${money(m.fees)}</dd></div><div><dt>${research?'研究调仓笔数':'成交笔数'}</dt><dd>${m.trade_count}</dd></div><div><dt>${research?'剩余计价单位':'可用现金'}</dt><dd>${unit}${money(r.cash)}</dd></div></dl>${chart(r.equity,research)}
  <details class="result-section" data-detail="data"><summary>数据与运行说明${r.warnings.length?`（${r.warnings.length} 项提示）`:''}</summary>${r.warnings.map(w=>`<p class="result-warning">${escape(w)}</p>`).join('')}${research?`<p>使用前复权价格和虚拟份额，不代表真实股价与股数。分红送转由供应商复权序列体现，未另计股息；全样本复权和数据修订存在未来信息局限。</p>${r.dataset_snapshot?researchMetadata(r.dataset_snapshot,r.symbol):'<p class="result-warning">此记录未包含数据元信息快照。</p>'}`:'<p>按日线信号进行本地撮合，未接入券商实盘。</p>'}</details>
  ${table(research?'研究持仓':'当前持仓',['标的',research?'虚拟份额':'总数量',research?'可用虚拟份额':'可卖数量',research?'复权平均成本':'平均成本'],r.positions.map(p=>[p.symbol,quantity(p.quantity),quantity(p.available_quantity),money(p.average_cost)]))}
  ${table(research?'研究调仓记录':'成交记录',[research?'调仓日':'成交日','信号日','方向',research?'虚拟份额':'数量',research?'复权研究价':'成交价','费用'],r.fills.map(f=>[f.date,f.signal_date,f.side==='buy'?'买入':'卖出',quantity(f.quantity),money(f.price),money(f.fee)]))}
  <details class="result-section" data-detail="orders"><summary>${research?'全部研究意图与未执行原因':'全部委托与未成交原因'}（${r.orders.length}）</summary>${table(research?'研究调仓意图':'本地委托',['交易日','信号日','方向',research?'虚拟份额':'数量','状态','原因'],r.orders.map(o=>[o.date,o.signal_date,o.side==='buy'?'买入':'卖出',quantity(o.quantity),o.status==='filled'?(research?'研究已执行':'已成交'):'未执行',o.reason||(research?'已按复权研究假设执行':'已按本地撮合规则成交')]))}</details>
  <details class="result-section" data-detail="signals"><summary>策略信号与冲突（${r.signals.length}）</summary>${table('逐日信号',['日期','目标仓位','冲突','策略分项与原因'],r.signals.map(s=>[s.date,s.target_pct==null?'阻止执行':pct(s.target_pct),s.conflict?'有分歧':'无',s.components.map(c=>`${c.name}：${pct(c.target_pct)}，权重 ${pct(c.effective_weight)}；${c.reason||''}`).concat(s.reasons).join(' / ')]))}</details>
  <details class="result-section" data-detail="equity"><summary>完整净值明细（${r.equity.length}）</summary>${table('逐日净值',['日期','现金','持仓市值','净值'],r.equity.map(e=>[e.date,money(e.cash),money(e.market_value),money(e.equity)]))}</details>
  <details class="result-section" data-detail="assumptions"><summary>冻结组合、数据与费用假设</summary><p class="helper">运行 ID：${escape(r.id)}<br>数据 ID：${escape(r.dataset_id||'等待行情')}<br>数据哈希：${escape(r.dataset_hash||'等待行情')}<br>佣金 ${c.commission_bps} 基点；最低 ${money(c.min_commission)} ${research?'研究计价单位':'元'}；卖出税费 ${c.sell_tax_bps} 基点；滑点 ${c.slippage_bps} 基点。<br>冲突处理：${snapshot.conflict_policy==='block'?'阻止执行':'采用加权结果'}；权重方式：${snapshot.mode==='equal'?'启用项等权':'自定义百分比'}。</p>${snapshot.items.map(i=>`<div class="source-rule"><strong>${escape(i.name)} · ${i.enabled?'启用':'禁用'} · 权重 ${pct(i.effective_weight)}</strong><p>${escape(JSON.stringify(i.rules))}</p><p>确认说明：${escape(i.mapping_note)}</p>${originalMarkup(i.source_snapshot)}</div>`).join('')}</details>`;
  open.forEach(key=>{const d=container.querySelector(`[data-detail="${key}"]`);if(d)d.open=true;});if(focused)container.querySelector(`[data-detail="${focused}"] summary`)?.focus({preventScroll:true});
}
window.addEventListener('beforeunload',e=>{if(T.dirty){e.preventDefault();e.returnValue='';}});
switchWorkspace();
})();
