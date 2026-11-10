// Real trading API and engines, isolated DATA_DIR. All market rows below are explicitly artificial fixtures.
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),python=path.join(root,'.venv','Scripts','python.exe');
const runDir=path.join(root,'.runtime',`phase3-ui-${Date.now()}`),output=path.join(root,'output','playwright');
const port=Number(process.env.UI_TEST_PORT||8768),base=`http://127.0.0.1:${port}`;
assert.notEqual(port,8765,'Never use the production service');
let server,browser,log='';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function addResearchFixture(){
  const symbols=[...Array.from({length:299},(_,i)=>`${600000+i}.SH`),'300750.SZ'];
  const rows=symbols.flatMap(symbol=>[
    ['2024-01-02',10,9],['2024-01-03',10,12],['2024-01-04',12,12]
  ].map(([date,open,close])=>({date,symbol,open,close,high:Math.max(open,close),low:Math.min(open,close),volume:100000,suspended:false,gap_before:false})));
  const d={id:'phase3-ui-research-fixture',name:'测试专用沪深300人工行情',dataset_type:'research_adjusted',market:'CN_A',price_basis:'forward_adjusted',allowed_modes:['backtest'],is_demo:false,created_at:'2026-11-10T00:00:00Z',version:1,hash:'TEST-ONLY',source:'隔离测试人工构造，非真实市场',start_date:'2024-01-02',end_date:'2024-01-04',symbols,row_count:rows.length,rows,
    symbol_metadata:symbols.map((symbol,i)=>({symbol,name:symbol==='300750.SZ'?'宁德时代（测试）':`测试股票${String(i).padStart(3,'0')}`,start_date:'2024-01-02',end_date:'2024-01-04',row_count:3,missing_day_count:1,internal_gap_count:0,missing_start:false,missing_tail:true})),
    requested_start_date:'2024-01-01',requested_end_date_exclusive:'2026-11-01',expected_end_date:'2026-10-30',
    universe:{name:'沪深300测试股票池',as_of_date:'2026-10-30',source:'测试快照',survivorship_bias:true},
    coverage:{status:'partial',actual_start_date:'2024-01-02',actual_end_date:'2024-01-04',successful_symbols:symbols,failed_symbols:[{symbol:'000001.SZ',name:'测试失败股',reason:'人工缺失示例'}],missing_tail_symbols:symbols,calendar_end_date:'2026-10-30'},
    provenance:{provider:'隔离测试来源',fetched_at:'2026-11-10T00:00:00Z',manifest_hash:'TEST-ONLY-MANIFEST'},warnings:['人工构造测试数据，非真实市场结果','前复权研究，不代表可交易收益']};
  const result=spawnSync(python,['-c','import json,sys; from pathlib import Path; from app.trading.store import TradingStore; s=TradingStore(Path(sys.argv[1])); d=json.load(sys.stdin.buffer)\nwith s.transaction() as c: s.put(c,"dataset",d)',runDir],{cwd:root,windowsHide:true,input:JSON.stringify(d),encoding:'utf8'});
  assert.equal(result.status,0,result.stderr||result.error?.message);return d;
}
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  await new Promise((resolve,reject)=>{const probe=require('node:net').createServer();probe.once('error',reject);probe.listen(port,'127.0.0.1',()=>probe.close(resolve));});
  server=spawn(python,['tests/ui_server.py',runDir,String(port)],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',b=>log+=b.toString());server.stderr.on('data',b=>log+=b.toString());server.on('error',e=>log+=e.message);
  for(let i=0;i<150;i++){try{if((await fetch(base+'/api/status')).ok)break;}catch{}if(i===149)throw Error('Isolated server failed: '+log);await sleep(100);}
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.setDefaultTimeout(15000);
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const api=async url=>{const r=await page.request.get(base+'/api/trading'+url);assert.equal(r.ok(),true,await r.text());return r.json();};
  await page.goto(base+'/#backtest');
  await page.locator('#research-status').getByText('尚未导入沪深300研究数据',{exact:true}).waitFor();
  assert.equal(await page.locator('#backtest-strategy-guide').isVisible(),true);
  assert.equal(await page.locator('#run-research').isDisabled(),true);
  assert.equal((await api('/portfolios')).length,0,'Empty state must never create a strategy');
  const fixture=addResearchFixture();
  await page.locator('#refresh-research').click();
  await page.locator('[data-research-symbol]').first().waitFor();
  assert.equal(await page.locator('[data-research-symbol]').count(),24);
  assert.equal(await page.locator('#research-dataset option').count(),2,'A whole pool uses one dataset option');
  await page.locator('#research-more').click();assert.equal(await page.locator('[data-research-symbol]').count(),48);
  await page.locator('#research-stock-search').fill('宁德');
  await page.locator('[data-research-symbol="300750.SZ"]').click();
  assert.equal(await page.locator('#research-symbol').inputValue(),'300750.SZ');
  assert.match(await page.locator('#research-selection').innerText(),/尾部数据缺失/);
  assert.equal(await page.locator('#run-research').isDisabled(),true,'Selecting stock cannot manufacture strategy readiness');
  await page.locator('#research-stock-search').fill('300750');assert.equal(await page.locator('[data-research-symbol]').count(),1);
  await page.locator('#research-stock-search').fill('不存在');assert.match(await page.locator('#research-stocks').innerText(),/没有匹配股票/);
  await page.locator('#research-stock-search').fill('测试失败股');await page.locator('#research-available-only').uncheck();
  assert.equal(await page.locator('[data-research-symbol="000001.SZ"]').isDisabled(),true);
  await page.locator('#research-stock-search').fill('宁德');
  assert.match(await page.locator('#research-data-summary').innerText(),/2024-01-02 ～ 2024-01-04/);
  assert.match(await page.locator('#research-data-summary').innerText(),/存活偏差/);
  assert.match(await page.locator('#research-data-summary').innerText(),/2026-10-30/);
  await page.locator('[data-workspace="paper"]').click();await page.locator('#workspace-paper').waitFor({state:'visible'});
  for(const id of ['paper-dataset','paper-sync-dataset'])assert.equal(await page.locator(`#${id} option[value="${fixture.id}"]`).count(),0);
  await page.locator('[data-workspace="portfolio"]').click();
  await page.locator('#portfolio-name').fill('Phase3 隔离验收策略');await page.locator('#add-manual').click();
  const item=page.locator('[data-item]');
  await item.locator('[data-field="rule-type"]').selectOption('threshold');
  await item.locator('[data-field="buy_below"]').fill('10');await item.locator('[data-field="sell_above"]').fill('11');
  await item.locator('[data-field="target_pct"]').fill('100');
  await item.locator('[data-field="mapping_note"]').fill('隔离测试人工规则，非正式策略');
  await item.locator('[data-field="confirmed"]').check();await page.locator('#save-portfolio').click();
  await page.locator('#portfolio-readiness').getByText(/此版本已就绪/).waitFor();
  const p=(await api('/portfolios'))[0];
  await page.locator('[data-workspace="backtest"]').click();
  await page.locator('#research-portfolio').selectOption(p.id);assert.match(await page.locator('#research-rule-note').innerText(),/绝对价格阈值/);
  await page.locator('#research-cash').fill('1001');
  await page.locator('#research-costs summary').click();
  for(const id of ['commission','minimum','tax','slippage'])await page.locator('#research-'+id).fill('0');
  await page.locator('#run-research').click();await page.locator('#research-result h2').getByText(/复权研究回测/).waitFor();
  const research=(await api('/backtests')).find(r=>r.execution_model==='adjusted_research');
  assert.equal(research.portfolio_id,p.id);assert.equal(research.symbol,'300750.SZ');assert.equal(research.metrics.total_return_pct,20);
  assert.equal(research.fills[0].quantity,100.1);assert.equal(research.fills.length,2);
  assert.match(await page.locator('#research-result').innerText(),/虚拟份额/);
  assert.match(await page.locator('#research-result').innerText(),/未来信息局限/);
  assert.equal(await page.locator('#backtest-history option[value="'+research.id+'"]').count(),0);
  await page.reload();await page.locator('#research-history option[value="'+research.id+'"]').waitFor({state:'attached'});
  await page.locator('#research-history').selectOption(research.id);await page.locator('#research-result h2').waitFor();
  assert.match(await page.locator('#research-result').innerText(),/冻结版本 v1/);
  await page.screenshot({path:path.join(output,'phase3-mobile-research.png'),fullPage:true});
  // Retained strict CSV path and original local paper account, using only artificial test prices.
  await page.locator('#backtest-mode').selectOption('strict');
  const prices=[10.1,9.5,9.8,10,10.4,10.6,10.8,10.7],days=[6,7,8,9,10,13,14,15];
  const csv=['date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down',...prices.map((v,i)=>{const prev=i?prices[i-1]:10;return `2025-01-${String(days[i]).padStart(2,'0')},600000.SH,${v},${v},${v},${v},100000,${prev},${(prev*1.1).toFixed(2)},${(prev*.9).toFixed(2)}`;})].join('\n');
  await page.locator('#dataset-name').fill('Phase3 严格CSV人工测试');await page.locator('#dataset-source').fill('测试专用构造，不是真实行情');
  await page.locator('#dataset-file').setInputFiles({name:'fixture.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
  await page.locator('#ordinary-stock').check();await page.locator('#no-actions').check();
  await page.locator('#import-dataset').click();await page.getByText('真实 CSV 已导入',{exact:true}).waitFor();
  await page.locator('#backtest-portfolio').selectOption(p.id);await page.locator('#backtest-form button[type="submit"]').click();
  await page.locator('#backtest-result h2').getByText(/回测结果/).waitFor();
  const strict=(await api('/backtests')).find(r=>r.execution_model!=='adjusted_research');assert.ok(strict.fills.length>0);
  await page.locator('[data-workspace="paper"]').click();
  await page.locator('#paper-portfolio').selectOption(p.id);await page.locator('#paper-dataset').selectOption(strict.dataset_id);
  await page.locator('#paper-name').fill('Phase3 原模拟回归账户');await page.locator('#paper-form button[type="submit"]').click();
  await page.locator('#paper-result h2').getByText(/Phase3 原模拟回归账户/).waitFor();
  await page.locator('#paper-step').click();await page.waitForFunction(()=>document.querySelector('#paper-result').innerText.includes('2025-01-06'));
  await page.locator('#paper-start').click();await page.locator('#paper-pause:enabled').waitFor();
  await page.locator('#paper-sync').click();await page.locator('#paper-pause').click();await page.locator('#paper-start:enabled').waitFor();
  assert.equal((await api('/paper/sessions'))[0].cursor,'2025-01-07');
  // New external engine resources are embedded in this page and use their real API.
  await page.locator('#paper-external-jump').click();await page.locator('#pex-refresh').click();
  await page.locator('#pex-capability').getByText(/已安装 · 无需账号/).waitFor();
  assert.equal(await page.locator(`#pex-dataset option[value="${fixture.id}"]`).count(),0,'Research data must not enter external replay');
  await page.locator('#pex-panel .pex-create > summary').click();
  await page.locator('#pex-portfolio').selectOption(p.id);await page.locator('#pex-dataset').selectOption(strict.dataset_id);
  await page.locator('#pex-name').fill('Phase3 Backtrader 隔离验收');await page.locator('#pex-create').click();
  await page.locator('#pex-result h3').getByText(/Phase3 Backtrader 隔离验收/).waitFor();
  let external=(await api('/external-paper/sessions'))[0];assert.equal(external.fills.length,0);assert.equal(external.consumed_bars,0);
  await page.locator('[data-pex-action="step"]').click();
  await page.waitForFunction(()=>document.querySelector('#pex-result').innerText.includes('1 / 8 根'));
  await page.locator('[data-pex-action="run"]').click();
  await page.locator('#pex-result .pex-tag').getByText('回放完成',{exact:true}).waitFor();
  external=(await api('/external-paper/sessions'))[0];assert.equal(external.status,'completed');assert.equal(external.consumed_bars,8);assert.ok(external.fills.length>0);assert.equal(external.engine.name,'Backtrader BackBroker');
  assert.equal(await page.locator('[data-pex-action="run"]').isDisabled(),true);
  const downloadPromise=page.waitForEvent('download');await page.locator('[data-pex-export]').click();
  const downloaded=await downloadPromise;await downloaded.saveAs(path.join(output,'phase3-external-ledger.json'));
  const exported=JSON.parse(fs.readFileSync(path.join(output,'phase3-external-ledger.json'),'utf8'));assert.equal(exported.id,external.id);
  await page.reload();await page.locator('#pex-history option[value="'+external.id+'"]').waitFor({state:'attached'});
  await page.locator('#pex-history').selectOption(external.id);await page.locator('#pex-result .pex-tag').getByText('回放完成',{exact:true}).waitFor();
  assert.equal(new URL(page.url()).hash,'#paper');
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:width===1440?1000:844});
    for(const key of ['materials','portfolio','backtest','paper']){
      await page.locator(`[data-workspace="${key}"]`).click();await page.locator(`#workspace-${key}`).waitFor({state:'visible'});
      if(key==='backtest')await page.locator('#backtest-mode').selectOption('research');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${key} overflow at ${width}`);
      if(['backtest','paper'].includes(key))await page.screenshot({path:path.join(output,`phase3-${width}-${key}.png`),fullPage:true});
    }
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'phase3-result.json'),JSON.stringify({runDir,fixtureOnly:true,researchRun:research.id,researchReturn:research.metrics.total_return_pct,researchFills:research.fills.length,strictRun:strict.id,externalSession:external.id,externalFills:external.fills.length,engine:external.engine,errors},null,2));
  console.log('PASS: isolated real API; empty strategy guard; 300-stock catalogue; name/code search; coverage+snapshot; synthetic-unit backtest; history; strict CSV; original replay; real Backtrader create/step/run/export/reload; 320/390/1440px; zero browser errors');
})().catch(e=>{console.error(e);console.error(log.slice(-4000));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
