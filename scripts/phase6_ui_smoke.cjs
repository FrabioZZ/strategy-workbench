// Real frontend + local APIs + engine; all datasets and portfolios are artificial fixtures.
// Never reads the production DATA_DIR or calls a model / market-data provider.
const {chromium}=require('playwright-core');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),python=path.join(root,'.venv','Scripts','python.exe');
const phase=process.env.UI_SMOKE_PHASE==='phase7'?'phase7':'phase6';
const folder=path.join(root,'.runtime',`${phase}-ui-${Date.now()}`),out=path.join(root,'output','playwright',...(phase==='phase7'?['phase7']:[]));
let server,browser,log='';const errors=[],sleep=ms=>new Promise(r=>setTimeout(r,ms));
function researchFixture(){
  const rows=[];let date=new Date('2024-01-02T00:00:00Z');
  for(let i=0;i<90;i++){
    while([0,6].includes(date.getUTCDay()))date.setUTCDate(date.getUTCDate()+1);
    const day=date.toISOString().slice(0,10),price=10+i*.04+Math.sin(i/3)*.3;
    for(const symbol of ['600000.SH','600001.SH'])if(symbol==='600000.SH'||i>=10)rows.push({date:day,symbol,open:price,high:price+.1,low:price-.1,close:price,volume:100000,suspended:false,gap_before:false});
    date.setUTCDate(date.getUTCDate()+1);
  }
  const symbols=['600000.SH','600001.SH'];
  const d={id:'phase6-research-fixture',name:'Phase6 人工研究行情',dataset_type:'research_adjusted',market:'CN_A',price_basis:'forward_adjusted',allowed_modes:['backtest'],is_demo:false,created_at:'2026-11-10T00:00:00Z',version:1,hash:'PHASE6-TEST-ONLY',source:'人工构造，不是真实市场',symbols,start_date:rows[0].date,end_date:rows.at(-1).date,row_count:rows.length,rows,warnings:['人工测试行情，非真实市场结果'],symbol_metadata:symbols.map((symbol,i)=>{const rr=rows.filter(r=>r.symbol===symbol);return {symbol,name:`测试股票${i+1}`,start_date:rr[0].date,end_date:rr.at(-1).date,row_count:rr.length};}),coverage:{status:'complete',successful_symbols:symbols,failed_symbols:[],missing_tail_symbols:[]},universe:{name:'测试股票池',survivorship_bias:true},provenance:{provider:'人工测试'}};
  const r=spawnSync(python,['-c','import json,sys; from pathlib import Path; from app.trading.store import TradingStore; s=TradingStore(Path(sys.argv[1])); d=json.load(sys.stdin.buffer)\nwith s.transaction() as c: s.put(c,"dataset",d)',folder],{cwd:root,windowsHide:true,input:JSON.stringify(d),encoding:'utf8'});
  assert.equal(r.status,0,r.stderr);return d;
}
async function run(){
  fs.mkdirSync(out,{recursive:true});
  const port=await new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});assert.notEqual(port,8765);
  const base=`http://127.0.0.1:${port}`;
  // Shutdown over our own stdin pipe avoids platform-wide process enumeration.
  const bootstrap=`import sys, threading\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()/'tests'))\nimport uvicorn\nfrom app.config import Settings\nfrom app.main import create_app\nfrom test_app import FakeExtractor\napp=create_app(Settings(data_dir=Path(sys.argv[1]),ai_provider='ollama',ai_base_url='http://127.0.0.1:1',ai_model='TEST-ONLY'),extractor=FakeExtractor())\nserver=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=int(sys.argv[2])))\ndef stop():\n sys.stdin.readline()\n server.should_exit=True\nthreading.Thread(target=stop,daemon=True).start()\nserver.run()`;
  server=spawn(python,['-u','-c',bootstrap,folder,String(port)],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe']});
  server.stdout.on('data',b=>log+=b);server.stderr.on('data',b=>log+=b);
  for(let i=0;i<150;i++){try{if((await fetch(base+'/api/status')).ok)break;}catch{}if(i===149)throw Error(log);await sleep(100);}
  async function api(url,body){const r=await fetch(base+'/api/trading'+url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});assert.equal(r.ok,true,await r.clone().text());return r.json();}
  const cap=await api('/capabilities');assert(cap.rule_types.includes('conditional'),'Phase 6 engine is required');assert(cap.indicators.length>20);
  const fixture=researchFixture(),demo=await api('/datasets/demo',{});
  browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(8000);page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  // Quote UI receives an explicit empty fixture: this smoke never calls a market provider.
  await page.route('**/api/trading/quotes/**',route=>{const u=new URL(route.request().url());return route.fulfill({json:u.pathname.endsWith('/catalog')?{members:[],universe:{name:'人工测试股票池'},message:'隔离测试未加载公开行情'}:{quotes:[],accounts:[],excluded_historical_accounts:0,server_time:'2026-11-10T00:00:00Z'}});});
  await page.goto(base+'/#portfolio');await page.locator('#indicator-library').waitFor();await page.locator('#indicator-library>summary').click();
  assert.match(await page.locator('#indicator-library').innerText(),/RSI/);assert.match(await page.locator('#indicator-library').innerText(),/MACD/);assert.doesNotMatch(await page.locator('#indicator-library').innerText(),/一进二|打板/);
  await page.locator('#indicator-library').screenshot({path:path.join(out,phase+'-indicators-1440.png')});
  await page.locator('#indicator-library>summary').click();await page.locator('#portfolio-name').fill('Phase6 人工条件组合');await page.locator('#add-manual').click();
  const item=page.locator('[data-item]').first();await item.locator('[data-field="rule-type"]').selectOption('conditional');
  for(const preset of ['macd','boll','kdj','ema','volume','first_limit']){
    await item.locator('[data-field="conditional-preset"]').selectOption(preset);
    assert.match(await item.locator('.conditional-preview').innerText(),/入场/);
    if(preset==='first_limit')assert.match(await page.locator('#notice').innerText(),/每日涨停价|未复权数据/);
  }
  await item.locator('[data-field="conditional-preset"]').selectOption('ema');
  await item.locator('.conditional-editor details>summary').click();
  const editor=item.locator('[data-field="conditional-json"]');const initialRule=JSON.parse(await editor.inputValue());
  assert.equal(initialRule.type,'conditional');await item.locator('[data-field="confirmed"]').check();await editor.fill('{broken');
  assert.equal(await item.locator('[data-field="confirmed"]').isChecked(),false);assert.equal(await item.locator('[data-field="confirmed"]').isDisabled(),true);
  await page.locator('#save-portfolio').click();assert.equal((await api('/portfolios')).length,0);assert.match(await page.locator('#notice').innerText(),/JSON/);
  await page.locator('#normalize-weights').click();assert.equal(await item.locator('[data-field="confirmed"]').isDisabled(),true,'invalid JSON remains blocked after redraw');
  const bad={...initialRule,buy:{op:'gt',left:{indicator:'CLOSE',offset:-1},right:{value:0}}};await editor.fill(JSON.stringify(bad));assert.match(await item.locator('.dsl-error').innerText(),/过去/);
  await editor.fill(JSON.stringify(initialRule,null,2));await item.locator('[data-field="mapping_note"]').fill('隔离人工验证；EMA(5)>EMA(20) 入场，非视频自动映射。');await item.locator('[data-field="confirmed"]').check();
  for(const width of [390,320,1440]){await page.setViewportSize({width,height:1800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`editor overflow ${width}`);await item.evaluate(el=>el.scrollIntoView({block:'center'}));await item.screenshot({path:path.join(out,`${phase}-conditions-${width}.png`)});}
  await page.locator('#save-portfolio').click();await page.locator('#portfolio-readiness').getByText(/此版本已就绪/).waitFor();
  const portfolio=(await api('/portfolios'))[0];assert.equal(portfolio.items[0].rules.buy.op,initialRule.buy.op);assert.equal(portfolio.items[0].rules.buy.left.params.period,5);assert.equal(portfolio.items[0].rules.buy.right.params.period,20);assert.equal(portfolio.items[0].rules.buy.left.params.field,'close');
  await page.locator('[data-workspace="backtest"]').click();await page.locator('[data-research-symbol="600000.SH"]').click();await page.locator('#research-portfolio').selectOption(portfolio.id);
  assert.equal(await page.locator('#research-start-date').inputValue(),fixture.start_date);assert.equal(await page.locator('#research-end-date').inputValue(),fixture.end_date);
  await page.locator('[data-research-symbol="600001.SH"]').click();assert.equal(await page.locator('#research-start-date').inputValue(),fixture.symbol_metadata[1].start_date);
  await page.locator('[data-research-symbol="600000.SH"]').click();
  const rows=fixture.rows.filter(r=>r.symbol==='600000.SH'),start=rows[30].date,end=rows[65].date;
  await page.locator('#research-start-date').fill(end);await page.locator('#research-end-date').fill(start);await page.locator('#run-research').click();assert.equal((await api('/backtests')).length,0);assert.equal(await page.locator('#research-end-date').evaluate(el=>el.validity.valid),false);
  await page.locator('#research-start-date').fill(start);await page.locator('#research-end-date').fill(end);
  await page.locator('#refresh-research').click();await page.waitForFunction(()=>!document.querySelector('#refresh-research').disabled);assert.equal(await page.locator('#research-start-date').inputValue(),start,'refresh preserves date selection');
  await page.locator('#research-form .backtest-dates').evaluate(el=>el.scrollIntoView({block:'center'}));await page.locator('#research-form .backtest-dates').screenshot({path:path.join(out,phase+'-dates-1440.png')});
  await page.locator('#research-costs summary').click();for(const k of ['commission','minimum','tax','slippage'])await page.locator('#research-'+k).fill('0');await page.locator('#research-cash').fill('10000');
  await page.locator('#run-research').click();await page.locator('#research-result h2').waitFor();
  const result=(await api('/backtests'))[0];assert.equal(result.requested_start_date,start);assert.equal(result.requested_end_date,end);assert.equal(result.actual_start_date,start);assert.equal(result.actual_end_date,end);assert(result.warmup_bars>=20);assert.equal(result.initial_equity,10000);assert.equal(Math.round((result.final_equity-result.initial_equity)*100)/100,result.pnl);
  const display=await page.locator('#research-result .period-summary').innerText();assert.match(display,/初始资产/);assert.match(display,/结束资产/);assert.match(display,/阶段盈亏/);assert.match(display,/阶段收益率/);assert(display.includes(result.pnl.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})));assert(display.includes(start));assert(display.includes(end));
  assert(result.equity.every(x=>x.date>=start&&x.date<=end));
  for(const width of [1440,390,320]){await page.setViewportSize({width,height:1200});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`result overflow ${width}`);await page.locator('#research-result .period-summary').evaluate(el=>el.scrollIntoView({block:'center'}));await page.locator('#research-result .period-summary').screenshot({path:path.join(out,`${phase}-results-${width}.png`)});}
  await page.reload();await page.locator('#research-history option[value="'+result.id+'"]').waitFor({state:'attached'});await page.locator('#research-history').selectOption(result.id);await page.locator('#research-result .period-summary').waitFor();assert.match(await page.locator('#research-result .period-summary').innerText(),/10,000.00/);
  await page.locator('#backtest-mode').selectOption('strict');await page.locator('#backtest-dataset').selectOption(demo.id);await page.locator('#backtest-portfolio').selectOption(portfolio.id);assert.equal(await page.locator('#backtest-start-date').inputValue(),demo.start_date);assert.equal(await page.locator('#backtest-end-date').inputValue(),demo.end_date);
  await page.locator('#backtest-form button[type="submit"]').click();await page.locator('#backtest-result h2').waitFor();assert.match(await page.locator('#backtest-result .period-summary').innerText(),/阶段盈亏（元）/);assert.match(await page.locator('#backtest-result .period-summary').innerText(),/¥/);
  // AI response is explicitly mocked; portfolio APIs above and engine results are real.
  const source={id:'phase6-ai-fixture',revision:1,title:'人工日线条件草案',source_title:'人工测试资料',stale:false,strategy:{title:'人工日线条件草案',rules:[],questions:[]}};
  let aiRules=portfolio.items[0].rules;
  await page.route('**/api/trading/strategies',route=>route.fulfill({json:[source]}));
  await page.route('**/api/ai/strategies/phase6-ai-fixture/mapping',route=>route.fulfill({json:{source_id:source.id,source_revision:1,rules:aiRules,ready:true,questions:[],evidence:[],mapping_note:'人工 AI 响应替身，用于确认 normalized params 兼容。',provider:'TEST-ONLY',model:'fixture'}}));
  await page.locator('[data-workspace="portfolio"]').click();await page.locator('#refresh-trading').click();await page.locator('[data-add-source="'+source.id+'"]').click();
  const mapped=page.locator('[data-item]').last();await mapped.locator('[data-ai-mapping]').click();await mapped.locator('.conditional-preview').waitFor();assert.equal(await mapped.locator('[data-field="confirmed"]').isChecked(),false);assert.match(await mapped.locator('.conditional-preview').innerText(),/field=close/);
  aiRules={...aiRules,buy:{...aiRules.buy,unsupported_intraday_filter:'排板'}};await mapped.locator('[data-ai-mapping]').click();await mapped.locator('.ai-mapping-feedback').getByText(/不支持或无效/).waitFor();assert.match(await mapped.locator('.conditional-preview').innerText(),/field=close/);
  await mapped.locator('[data-remove]').click();
  await page.locator('[data-workspace="paper"]').click();await page.locator('#paper-portfolio').selectOption(portfolio.id);await page.locator('#paper-mode').selectOption('replay');await page.locator('#paper-dataset').selectOption(demo.id);await page.locator('#paper-name').fill('Phase6 人工日线回放');await page.locator('#paper-symbol').fill(demo.symbols[0]);
  const paperRequest=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/trading/paper/sessions'&&r.method()==='POST');await page.locator('#paper-form button[type="submit"]').click();const paperBody=(await paperRequest).postDataJSON();assert.equal('start_date'in paperBody,false);assert.equal('end_date'in paperBody,false);
  await page.locator('#paper-result h2').getByText(/Phase6 人工日线回放/).waitFor();await page.locator('#paper-step').click();await page.waitForFunction(()=>!document.querySelector('#paper-step').disabled);assert.equal((await api('/paper/sessions'))[0].cursor,demo.start_date);assert.match(await page.locator('#paper-result .period-summary').innerText(),/已处理行情区间/);
  let externalVerified=false;
  if(phase==='phase7'){
    await page.locator('#pex-refresh').click();await page.waitForFunction(()=>!document.querySelector('#pex-refresh').disabled);
    assert.equal((await api('/external-paper/capabilities')).installed,true,'Backtrader engine installed');
    await page.locator('.pex-create>summary').click();await page.locator('#pex-portfolio').selectOption(portfolio.id);await page.locator('#pex-dataset').selectOption(demo.id);await page.locator('#pex-name').fill('Phase7 人工独立引擎回放');
    await page.locator('#pex-create').click();await page.locator('#pex-result h3').getByText('Phase7 人工独立引擎回放',{exact:false}).waitFor();
    await page.locator('[data-pex-action="run"]').click();await page.locator('#pex-result h3').getByText(/回放完成/).waitFor();
    const external=(await api('/external-paper/sessions'))[0];
    assert.equal(external.consumed_bars,external.total_bars);
    const epnl=external.equity.at(-1).equity-external.initial_cash;
    assert.match(await page.locator('#pex-result .pex-metrics').innerText(),/阶段盈亏/);
    assert((await page.locator('#pex-result .pex-metrics').innerText()).includes(epnl.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})));
    externalVerified=true;await page.locator('.pex-create>summary').click();

    assert.deepEqual(await page.locator('#research-result .primary-metrics dt').allTextContents(),['阶段盈亏（研究计价单位）','阶段收益率','初始资产（研究计价单位）','结束资产（研究计价单位）']);
    for(const target of ['research-result','backtest-result','paper-result']){
      assert.equal(await page.locator('#'+target+' [data-detail="data"]').getAttribute('open'),null,'data details initially collapsed');
      assert.equal(await page.locator('#'+target+' [data-detail="calculation"]').getAttribute('open'),null,'calculation initially collapsed');
    }
    await page.locator('#paper-result [data-detail="calculation"] summary').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#paper-result [data-detail="calculation"]').evaluate(el=>el.open),true);
    await page.locator('#refresh-paper').click();await page.waitForFunction(()=>!document.querySelector('#refresh-paper').disabled);
    assert.equal(await page.locator('#paper-result [data-detail="calculation"]').evaluate(el=>el.open),true,'polling preserves expanded details');
    await page.locator('#paper-result [data-detail="calculation"] summary').click();
    await page.emulateMedia({reducedMotion:'reduce'});
    for(const width of [1440,1024,768,390,320]){
      await page.setViewportSize({width,height:1000});
      for(const workspace of ['materials','portfolio','backtest','paper']){
        await page.locator('[data-workspace="'+workspace+'"]').click();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,workspace+' overflow '+width);
        assert.equal(await page.locator('[data-workspace="'+workspace+'"]').getAttribute('aria-current'),'page');
        const outside=await page.locator('#workspace-'+workspace+' input:visible, #workspace-'+workspace+' select:visible, #workspace-'+workspace+' textarea:visible, #workspace-'+workspace+' button:visible').evaluateAll(els=>els.filter(el=>{const r=el.getBoundingClientRect();return r.left < -1 || r.right > innerWidth+1;}).map(el=>el.id||el.tagName));
        assert.deepEqual(outside,[],'controls not clipped '+workspace+' '+width);

        const controls=await page.locator('#workspace-'+workspace+' button:visible').evaluateAll(els=>els.filter(el=>!el.disabled&&el.getBoundingClientRect().height<43).map(el=>el.id||el.textContent));
        assert.deepEqual(controls,[],'touch targets '+workspace+' '+width);
        await page.screenshot({path:path.join(out,`${phase}-${workspace}-${width}.png`),fullPage:true});
      }
      await page.locator('#pex-result').screenshot({path:path.join(out,`${phase}-external-result-${width}.png`)});
      await page.locator('#paper-result').scrollIntoViewIfNeeded();await page.locator('#paper-result').screenshot({path:path.join(out,`${phase}-paper-result-${width}.png`)});
    }
    await page.setViewportSize({width:390,height:844});
    await page.locator('[data-workspace="materials"]').focus();await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'welcome-title','workspace keyboard activation focuses heading');
    await page.locator('#tab-upload').focus();await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#tab-url').getAttribute('aria-selected'),'true','import tabs keyboard selection');
    await page.locator('#tab-text').click();await page.locator('#import-name').fill('Phase7 人工文本资料');await page.locator('#source-text').fill('价格高于二十日均线时考虑买入，跌破均线时卖出。');
    await page.locator('#import-submit').click();await page.locator('#document-title').getByText('Phase7 人工文本资料',{exact:true}).waitFor();
    assert.equal(await page.locator('#transcript-review').getAttribute('open'),null,'original text stays folded');
    await page.screenshot({path:path.join(out,`${phase}-imported-material-390.png`),fullPage:true});
    await page.locator('[data-workspace="backtest"]').click();
    await page.locator('#backtest-history').selectOption('');
    assert.match(await page.locator('#backtest-result').innerText(),/选择.*回测/,'cleared history does not leave previous results');
    await page.locator('#backtest-mode').selectOption('research');
    await page.route('**/api/trading/datasets',route=>route.fulfill({status:503,json:{detail:'人工模拟数据服务不可用，请稍后重试。'}}));
    await page.locator('#refresh-research').click();
    await page.locator('#notice').getByText(/人工模拟数据服务不可用/).waitFor();
    assert.match(await page.locator('#research-status').innerText(),/读取失败/);
    await page.screenshot({path:path.join(out,`${phase}-data-error-390.png`),fullPage:true});
  }
  assert.deepEqual(errors,[]);
  const report={passed:true,realLocalApiAndEngine:true,artificialMarketData:true,actualVideoOrProviderVerified:false,isolatedDataDir:folder,indicatorCount:cap.indicators.length,portfolio:portfolio.id,run:result.id,requestedStart:start,requestedEnd:end,warmupBars:result.warmup_bars,initialEquity:result.initial_equity,finalEquity:result.final_equity,pnl:result.pnl,widths:phase==='phase7'?[1440,1024,768,390,320]:[1440,390,320],externalEngineVerified:externalVerified,errors};
  fs.writeFileSync(path.join(out,phase+'-ui-result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
run().catch(e=>{console.error(e);console.error(log.slice(-3000));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server&&!server.stdin.destroyed){server.stdin.end('shutdown\n');await new Promise(resolve=>server.once('close',resolve));}});
