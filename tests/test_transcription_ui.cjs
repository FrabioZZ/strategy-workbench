// Browser UI regression with explicit in-memory API fixtures; no real ASR/model.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright-core');
const root = path.resolve(__dirname, '..');

test('automatic transcription states, retry, refresh, optional evidence and mobile layout', {timeout: 45000}, async () => {
  const server = http.createServer((req, res) => {
    const filename = req.url === '/' ? 'index.html' : req.url.replace('/static/', '');
    const target = path.join(root, 'frontend', filename);
    if (!target.startsWith(path.join(root, 'frontend') + path.sep) || !fs.existsSync(target)) {res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type', filename.endsWith('.js') ? 'application/javascript' : filename.endsWith('.css') ? 'text/css' : 'text/html');
    res.end(fs.readFileSync(target));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const executablePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  let browser;
  try {
    browser = await chromium.launch({executablePath, headless: true});
    const page = await browser.newPage({viewport: {width: 1365, height: 900}});
    // Other workstreams have separate probes; this probe exercises the shared
    // index + materials app and styles, without executing their parallel edits.
    await page.route(/\/static\/(?!app\.js)[^/]+\.js$/, route => route.fulfill({body: '', contentType: 'application/javascript'}));
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let asrConfigured = true;
    let current = null;
    let documentReads = 0;
    let failNextRead = false;
    const segments = [{id:'s1', start:1, end:2, text:'20日线买入'}];
    const job = (kind, status, stage) => ({id:`${kind}-job`, kind, status, stage});
    await page.addInitScript(() => Object.defineProperty(navigator, 'wakeLock', {value:{request:async()=>{throw new Error('fixture: unavailable');}}, configurable:true}));
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      let body;
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
      } else body = {};
      await route.fulfill({json:body});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
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
    current.strategy_provider='test';current.strategy_model='test';current.strategy_revision=2;
    await page.locator('[data-id="fixture"]').click();
    assert.match(await page.locator('[data-evidence]').innerText(),/校正版/);
    await page.locator('[data-evidence]').click();
    assert.equal(await page.locator('#transcript-review').evaluate(el=>el.open),true);
    await page.locator('#text-s1').fill('校对后：20日线买入');
    await page.locator('#save-transcript').click();
    await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='已保存到本机');
    assert.equal(current.segments[0].text,'校对后：20日线买入');
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
  } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
});
