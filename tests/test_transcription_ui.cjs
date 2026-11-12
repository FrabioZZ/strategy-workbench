// Browser UI regression with explicit in-memory API fixtures; no real ASR/model.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');
const root = path.resolve(__dirname, '..');

test('transcription retry, strategy handoff and mobile layout', {timeout: 45000}, async () => {
  const executablePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  let browser;
  try {
    browser = await chromium.launch({executablePath, headless: true});
    const page = await browser.newPage({viewport: {width: 1365, height: 900}});
    await page.route('http://127.0.0.1/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      const filename = pathname === '/' ? 'index.html' : pathname.replace('/static/', '');
      const target = path.join(root, 'frontend', filename);
      if (!target.startsWith(path.join(root, 'frontend') + path.sep) || !fs.existsSync(target)) return route.fulfill({status:404});
      return route.fulfill({path:target});
    });
    await page.route(/\/static\/(?!(?:app|trading)\.js)[^/]+\.js$/, route => route.fulfill({body: '', contentType: 'application/javascript'}));
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let asrConfigured = true;
    let current = null;
    let documentReads = 0;
    let failNextRead = false;
    let portfolio = null;
    let demoDataset = null;
    let mappingRequests = 0;
    const sourceId = 'source-from-transcript';
    const rules = {type:'ma', fast:5, slow:20, target_pct:50, stop_loss_pct:null};
    const segments = [{id:'s1', start:1, end:2, text:'20日线买入'}];
    const job = (kind, status, stage) => ({id:`${kind}-job`, kind, status, stage});
    await page.addInitScript(() => Object.defineProperty(navigator, 'wakeLock', {value:{request:async()=>{throw new Error('fixture: unavailable');}}, configurable:true}));
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      let body;
      const source = () => ({id:sourceId, document_id:'fixture', title:current.strategy.title, revision:2, strategy:current.strategy, transcript:segments, stale:!!current.strategy_stale});
      if (url.pathname === '/api/status') body = {asr_configured:asrConfigured, asr_note:asrConfigured?'本地模型已找到':'未配置本地 ASR 模型', max_upload_mb:200, max_duration_minutes:120, ai_configured:true, ai_provider:'deepseek', ai_model:'test-only', ai_note:'配置已保存'};
      else if (url.pathname === '/api/documents') body = current ? [current] : [];
      else if (url.pathname === '/api/documents/url') {
        current = {id:'fixture', title:'测试课程', updated_at:'2026-11-10T12:00:00Z', source_type:'url', source_url:'https://b23.tv/test', revision:1, segments:[], jobs:[job('download','running','正在获取平台媒体')], has_media:false, media_metadata:{}, media_status:'downloading', strategy:null};
        body = current;
      } else if (url.pathname === '/api/documents/fixture/transcript' && method === 'PUT') {
        current.segments = route.request().postDataJSON().segments;
        current.revision++;
        current.strategy_stale = true;
        body = current;
      } else if (url.pathname.endsWith('/retry') || url.pathname.endsWith('/transcribe')) {
        current.jobs = [job('transcribe','running','本地语音转写中')]; current.media_status='transcribing'; body=current.jobs[0];
      } else if (url.pathname === '/api/documents/fixture') {
        documentReads++;
        if (failNextRead) {failNextRead=false;await route.abort('failed');return;}
        body=current;
      } else if (url.pathname === '/api/trading/capabilities') {
        body={rule_types:['ma'], broker:{label:'本地模拟'}, feeds:{tushare_configured:false}, limitations:[]};
      } else if (url.pathname === '/api/trading/strategies') {
        body=current?.strategy?[source()]:[];
      } else if (url.pathname === '/api/trading/portfolios') {
        if (method==='POST') {
          const input=route.request().postDataJSON();
          portfolio={...input,id:'saved-portfolio',revision:1,readiness:{ready:true,errors:[],warnings:[]}};
        }
        body=method==='POST'?portfolio:(portfolio?[portfolio]:[]);
      } else if (url.pathname === '/api/trading/datasets/demo') {
        demoDataset={id:'demo-bars',name:'演示行情',is_demo:true,allowed_modes:['backtest','replay'],symbols:['000001.SZ'],start_date:'2024-01-02',end_date:'2024-04-30',row_count:80};
        body=demoDataset;
      } else if (url.pathname === '/api/trading/datasets') {
        body=demoDataset?[demoDataset]:[];
      } else if (url.pathname.startsWith('/api/trading/')) {
        body=[];
      } else if (url.pathname === '/api/ai/strategies/'+sourceId+'/mapping') {
        mappingRequests++;
        body={source_id:sourceId,source_revision:2,ready:true,rules,questions:[],evidence:[],mapping_note:'已对照资料',provider:'test',model:'test-only'};
      } else body = {};
      await route.fulfill({json:body});
    });
    await page.goto('http://127.0.0.1/');
    await page.evaluate(()=>document.addEventListener('document-rendered',e=>window.lastRenderedDocument=e.detail));
    await page.locator('#tab-url').click();
    assert.match(await page.locator('#import-submit').innerText(), /转写/);
    await page.locator('#video-url').fill('https://b23.tv/test');
    await page.locator('#import-submit').click();
    await page.locator('#job-status [role="progressbar"]').waitFor();
    assert.equal(await page.locator('[role="progressbar"]').getAttribute('aria-valuenow'), null);
    assert.match(await page.locator('#job-status').innerText(), /保持程序打开.*设备唤醒/);
    assert.equal(await page.locator('video,audio').count(), 0);
    current.has_media=true;current.media_metadata={media_type:'audio',duration_seconds:2};
    current.jobs=[job('transcribe','running','本地语音转写中')];current.media_status='transcribing';
    await page.waitForFunction(() => document.querySelector('#job-status').textContent.includes('本地语音转写中'));
    const beforeFailure = documentReads;
    failNextRead = true;
    await page.locator('#poll-warning').waitFor();
    assert.match(await page.locator('#poll-warning').innerText(), /重连/);
    await page.waitForFunction(() => document.querySelector('#poll-warning').hidden);
    assert.ok(documentReads > beforeFailure + 1, 'poll resumes after one network failure');
    current.jobs=[{...job('transcribe','failed','转写失败（缓存已保留）'),error:'测试识别失败'}];current.media_status='transcription_failed';
    await page.locator('[data-retry]').waitFor();
    assert.match(await page.locator('[data-retry]').innerText(), /缓存转写/);
    assert.equal(await page.locator('#transcription-state').evaluate(el=>el.classList.contains('complete')),false);
    await page.locator('[data-retry]').click();
    await page.locator('[role="progressbar"]').waitFor();
    current.segments=segments;current.jobs=[job('transcribe','succeeded','处理完成')];current.media_status='transcribed';current.revision=2;
    await page.waitForFunction(() => document.querySelector('#transcript-title').textContent==='转写完成');
    assert.equal(await page.locator('#transcription-icon').innerText(),'✓');
    assert.equal(await page.locator('#transcript-review').evaluate(el=>el.open),false);
    assert.equal(await page.locator('#segments textarea').isVisible(),false);
    assert.equal(await page.evaluate(()=>window.lastRenderedDocument.media_status),'transcribed');
    assert.equal(await page.locator('video,audio').count(),0);
    assert.match(await page.locator('#ai-hint').innerText(),/deepseek/);
    assert.doesNotMatch(await page.locator('#ai-hint').innerText(),/Ollama|OpenAI兼容/);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#transcript-title').textContent==='转写完成');
    assert.equal(await page.locator('#transcript-review').evaluate(el=>el.open),false);
    // Use a strategy fixture to verify the real evidence handler and save flow.
    current.strategy={title:'测试策略',asset:null,timeframe:null,rules:[{kind:'buy',text:'20日线买入',evidence:[{segment_id:'s1',start:1,end:2,quote:'20日线买入',transcript_version:'corrected'}]}],questions:[],notice:'测试专用'};
    current.strategy_provider='test';current.strategy_model='test';current.strategy_revision=2;current.strategy_id=sourceId;
    await page.locator('[data-id="fixture"]').click();
    assert.match(await page.locator('[data-evidence]').innerText(),/校正版/);
    await page.locator('[data-evidence]').click();
    assert.equal(await page.locator('#transcript-review').evaluate(el=>el.open),true);
    await page.locator('#prepare-execution').click({timeout:2500});
    await page.waitForFunction(()=>document.querySelector('#portfolio-items [data-field="fast"]')?.value==='5');
    assert.equal(mappingRequests,1);
    assert.equal(await page.locator('#portfolio-items [data-field="confirmed"]').isChecked(),false);
    await page.locator('[data-workspace="materials"]').click();
    await page.locator('#prepare-execution').click();
    await page.locator('#portfolio-items [data-field="confirmed"]').check();
    assert.equal(mappingRequests,1, 'reopening an already mapped source does not request a second mapping');
    await page.locator('[data-add-source]').click();
    const addedItem = page.locator('#portfolio-items .portfolio-item').last();
    assert.equal(await addedItem.locator('[data-field="name"]').inputValue(), '测试策略 (2)');
    await addedItem.locator('[data-remove]').click();
    await page.locator('#save-portfolio').click();
    await page.locator('#portfolio-readiness [data-run-workspace="backtest"]').click();
    assert.equal(await page.locator('#backtest-portfolio').inputValue(),'saved-portfolio');
    assert.equal(await page.locator('#research-portfolio').inputValue(),'saved-portfolio');
    assert.equal(await page.locator('#backtest-mode').inputValue(),'strict');
    await page.locator('[data-workspace="portfolio"]').click();
    await page.locator('#portfolio-readiness [data-run-workspace="paper"]').click();
    assert.equal(await page.locator('#paper-portfolio').inputValue(),'saved-portfolio');
    await page.locator('#paper-advanced > summary').click();
    await page.locator('#paper-demo-dataset').click({timeout:2500});
    await page.waitForFunction(()=>document.querySelector('#paper-dataset').value==='demo-bars');
    assert.equal(await page.locator('#paper-symbol').inputValue(),'000001.SZ');
    assert.equal(portfolio.items[0].source_id,sourceId);
    assert.deepEqual(portfolio.items[0].rules,rules);
    assert.equal(portfolio.items[0].confirmed,true);
    await page.locator('[data-workspace="materials"]').click();
    await page.locator('#text-s1').fill('校对后：20日线买入');
    assert.equal(await page.locator('#prepare-execution').isDisabled(),true);
    assert.equal(await page.locator('#complete-execution').isDisabled(),true);
    await page.locator('#save-transcript').click();
    await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='已保存到本机');
    assert.equal(current.segments[0].text,'校对后：20日线买入');
    assert.equal(await page.locator('#prepare-execution').isVisible(),false);
    assert.equal(await page.locator('#complete-execution').isVisible(),false);
    fs.mkdirSync(path.join(root,'output/playwright'),{recursive:true});
    await page.locator('#transcript-review > summary').click();
    await page.screenshot({path:path.join(root,'output/playwright/phase5-transcription-desktop.png'),fullPage:true});
    await page.locator('#transcript-review > summary').click();
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth > window.innerWidth),false);
    await page.locator('#transcript-review > summary').click();
    await page.screenshot({path:path.join(root,'output/playwright/phase5-transcription-mobile.png'),fullPage:true});
    asrConfigured=false;current.segments=[];current.strategy=null;current.media_status='awaiting_transcription';current.jobs=[job('download','succeeded','媒体已获取，待转写')];
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#transcript-title').textContent.includes('待配置'));
    assert.equal(await page.locator('#transcribe').isDisabled(),true);
    assert.equal(await page.locator('#transcription-state').evaluate(el=>el.classList.contains('complete')),false);
    assert.match(await page.locator('#transcribe-hint').innerText(),/ASR/);
    assert.deepEqual(errors,[]);
  } finally {if(browser)await browser.close();}
});

test('library right-click deletes only the confirmed material and clears its open view', {timeout: 30000}, async () => {
  const executablePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const browser = await chromium.launch({executablePath, headless: true});
  try {
    const page = await browser.newPage();
    let finishDelete;
    const pendingDelete = new Promise(resolve => {finishDelete = resolve;});
    const materials = new Map(['one', 'two'].map(id => [id, {
      id, title: `资料 ${id}`, source_type: 'text', updated_at: '2026-11-11T12:00:00Z',
      revision: 1, jobs: [], segments: [{id: 's1', text: '测试原文', start: null, end: null}],
    }]));
    materials.get('two').parent_document_id = 'one';
    await page.route('http://127.0.0.1/**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === '/api/status' || pathname === '/api/asr/config') return route.fulfill({json: {}});
      if (pathname === '/api/documents') return route.fulfill({json: [...materials.values()]});
      if (pathname.startsWith('/api/documents/')) {
        const id = pathname.split('/').at(-1);
        if (route.request().method() === 'DELETE') {
          if (id === 'two') return route.fulfill({status: 409, json: {detail: '这份资料正在处理。'}});
          await pendingDelete;
          materials.delete(id);
          return route.fulfill({json: {deleted: true}});
        }
        const material = materials.get(id);
        return route.fulfill({json: {...material, parent_document_deleted: !!material.parent_document_id && !materials.has(material.parent_document_id)}});
      }
      if (pathname.endsWith('.js') && !['/static/app.js', '/static/asr.js'].includes(pathname)) {
        return route.fulfill({body: '', contentType: 'application/javascript'});
      }
      const filename = pathname === '/' ? 'index.html' : pathname.replace('/static/', '');
      const target = path.join(root, 'frontend', filename);
      if (!target.startsWith(path.join(root, 'frontend') + path.sep) || !fs.existsSync(target)) return route.fulfill({status: 404});
      return route.fulfill({path: target, headers: {'Content-Security-Policy': "default-src 'self'; style-src 'self'"}});
    });
    await page.goto('http://127.0.0.1/');
    const first = page.getByRole('button', {name: /资料 one/});
    const second = page.getByRole('button', {name: /资料 two/});
    const remove = page.getByRole('menuitem', {name: '删除资料'});
    await first.click();
    await page.getByRole('heading', {name: '资料 one'}).waitFor();

    await second.click({button: 'right'});
    await remove.waitFor({timeout: 2000});
    await page.keyboard.press('Escape');
    assert.equal(await second.evaluate(button => button === document.activeElement), true);
    await second.press('Shift+F10');
    page.once('dialog', dialog => dialog.accept());
    await remove.click();
    await page.getByText('这份资料正在处理。').waitFor();
    assert.equal(await first.getAttribute('aria-current'), 'true');
    assert.equal(await second.count(), 1);

    await page.locator('#transcript-review > summary').click();
    await page.locator('#text-s1').fill('未保存的修改');
    await first.click({button: 'right'});
    page.once('dialog', dialog => dialog.dismiss());
    await remove.click();
    assert.equal(await first.count(), 1);
    assert.equal(await page.locator('#text-s1').inputValue(), '未保存的修改');
    await first.click({button: 'right'});
    let confirmation;
    page.once('dialog', dialog => {confirmation = dialog.message(); return dialog.accept();});
    await remove.click();
    const editingDisabled = await page.locator('#text-s1').isDisabled();
    finishDelete();
    assert.equal(editingDisabled, true);
    await first.waitFor({state: 'detached'});
    assert.match(confirmation, /资料 one/);
    assert.match(confirmation, /未保存的修改/);
    assert.equal(await second.count(), 1);
    assert.equal(await page.locator('#document-count').textContent(), '1');
    assert.equal(await page.locator('#import-view').isVisible(), true);
    assert.equal(await page.evaluate(() => localStorage.getItem('quant-current-document')), null);
    await page.reload();
    await second.waitFor();
    assert.equal(await first.count(), 0);
    await second.click();
    await page.getByText('重转写副本 · 父来源资料已删除').waitFor();
    assert.equal(await page.getByRole('button', {name: '查看父来源资料'}).count(), 0);
  } finally {
    await browser.close();
  }
});
