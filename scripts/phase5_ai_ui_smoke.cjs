// Isolated browser checks. All AI responses are explicit fixtures; no provider or user data access.
const {chromium}=require('playwright-core');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'output','playwright');
const providers=[{id:'test-a',label:'测试供应商 A',base_url:'https://a.invalid/v1',models:['test-model']},{id:'custom',label:'自定义兼容接口',base_url:'',models:[]}];
const source={id:'draft-1',title:'双均线日线策略',source_title:'分享视频原题',revision:2,stale:false,document_id:'doc-1',strategy:{title:'双均线日线策略',rules:[{kind:'buy',text:'日线快均线高于慢均线时买入。',evidence:[{segment_id:'s1',quote:'五日均线'}]}],questions:[]},transcript:[{id:'s1',text:'五日均线高于二十日均线时买入，反之卖出，仓位50%。'}]};
const suggestion={source_id:source.id,source_revision:2,rules:{type:'ma',fast:5,slow:20,target_pct:50,stop_loss_pct:null},mapping_note:'按日线快慢均线与目标仓位映射。',questions:[],evidence:[{field:'fast',segment_id:'s1',quote:'五日均线',transcript_version:'corrected'}],ready:true,provider:'test-a',model:'test-model'};
const reviewDoc={id:'doc-review',title:'校正摘要测试资料',source_type:'text',updated_at:'2026-11-10T00:00:00Z',revision:2,segments:[{id:'s1',text:'五日均现',start:null,end:null}],jobs:[],has_media:false,strategy:{...source.strategy,notice:'测试草案，需核对。'},strategy_stale:false,strategy_revision:2,strategy_provider:'test-a',strategy_model:'test-model',ai_review:{status:'corrected',summary:'已校正 1 处识别错词，并按内容命名策略。',changes:[{segment_id:'s1',original:'五日均现',corrected:'五日均线',reason:'明显同音识别错误'}],questions:[]}};
const otherDoc={...reviewDoc,id:'other-doc',title:'尚未提取的资料',strategy:null,ai_review:null};
let server,browser,config={providers,provider:'test-a',base_url:'https://a.invalid/v1',model:'test-model',has_api_key:false,configured:false,storage_note:'测试专用本机存储说明'},savedBody,statusReads=0,testCalls=0,mappingMode='success',mappingGate,portfolios=[],testFails=false;
let mountedFallback=false;const errors=[];
async function run(){
  fs.mkdirSync(out,{recursive:true});
  server=http.createServer((req,res)=>{let rel=req.url.split('?')[0].replace(/^\/static\//,'/');if(rel==='/')rel='/index.html';const file=path.join(root,'frontend',rel);if(!file.startsWith(path.join(root,'frontend'))||!fs.existsSync(file)){res.writeHead(404);res.end();return;}let body=fs.readFileSync(file);if(rel==='/index.html'){body=body.toString();if(!body.includes('ai-settings-root')){body=body.replace('<div id="configuration-status"','<div id="ai-settings-root"></div><div id="configuration-status"');mountedFallback=true;}if(!/src="[^\"]*ai\.js/.test(body)){body=body.replace('</body>','<link rel="stylesheet" href="/ai.css"><script src="/ai.js"></script></body>');mountedFallback=true;}}res.setHeader('Content-Type',rel.endsWith('.js')?'application/javascript':rel.endsWith('.css')?'text/css':'text/html');res.end(body);});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(4000);page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{const u=new URL(route.request().url()),method=route.request().method();let data=[];
    if(u.pathname==='/api/ai/config'){if(method==='PUT'){savedBody=route.request().postDataJSON();config={...config,...savedBody,has_api_key:!!savedBody.api_key||config.has_api_key,configured:true};delete config.api_key;}if(method==='DELETE')config={...config,has_api_key:false,configured:false};data=config;}
    else if(u.pathname==='/api/ai/test'){testCalls++;if(testFails)return route.fulfill({status:503,json:{detail:'测试替身：网络故障'}});data={ok:true,message:'测试替身：连通成功'};}
    else if(u.pathname.includes('/api/ai/strategies/')){const mode=mappingMode;if(mode==='delay')await new Promise(resolve=>mappingGate=resolve);if(mode==='error')return route.fulfill({status:503,json:{detail:'测试替身：供应商暂不可用'}});data={...suggestion,...(mode==='stale'?{source_revision:1}:mode==='incomplete'?{rules:null,ready:false,questions:['尚缺目标仓位，且筛选条件不受支持。']}:mode==='invalid'?{rules:{...suggestion.rules,type:'code'}}:mode==='invalid-extra'?{rules:{...suggestion.rules,filter:'必须额外满足筛选条件'}}:{})};}
    else if(u.pathname==='/api/status'){statusReads++;data={asr_configured:false,asr_note:'测试 ASR 未启用',ai_configured:config.configured,ai_note:'测试 AI 配置',ai_provider:config.provider,ai_model:config.model,max_upload_mb:100,max_duration_minutes:60};}
    else if(u.pathname==='/api/documents')data=[reviewDoc,otherDoc];
    else if(u.pathname==='/api/documents/doc-review')data=reviewDoc;
    else if(u.pathname==='/api/documents/other-doc')data=otherDoc;
    else if(u.pathname==='/api/trading/capabilities')data={broker:{label:'测试本地模拟'},feeds:{tushare_configured:false},limitations:[]};
    else if(u.pathname==='/api/trading/strategies')data=[source];
    else if(u.pathname==='/api/trading/portfolios'){if(method==='POST'){const b=route.request().postDataJSON();portfolios=[{...b,id:'p1',revision:1,readiness:{ready:false,errors:['需要确认'],warnings:[]},items:b.items.map(i=>({...i,source_snapshot:source}))}];data=portfolios[0];}else data=portfolios;}
    await route.fulfill({json:data});
  });
  await page.goto(base);await page.locator('#settings-toggle').click();
  await page.locator('#ai-provider').waitFor();
  assert.equal(await page.locator('#ai-key').getAttribute('type'),'password');
  await page.locator('#ai-key').fill('fixture-secret-only');await page.locator('#ai-save').click();
  await page.waitForFunction(()=>document.querySelector('#ai-key').value===''&&!document.querySelector('#ai-save').disabled);
  assert.equal(savedBody.api_key,'fixture-secret-only');assert(statusReads>=2,'save refreshes shared config');
  assert.match(await page.locator('#ai-feedback').innerText(),/未测试|不代表/);assert.equal(testCalls,0);
  await page.locator('#ai-test').click();await page.locator('#ai-feedback').getByText(/连接测试成功/).waitFor();assert.equal(testCalls,1);
  testFails=true;await page.locator('#ai-test').click();await page.locator('#ai-feedback').getByText(/连接测试失败/).waitFor();assert.match(await page.locator('#ai-saved-state').innerText(),/本次连接测试失败/);testFails=false;
  await page.locator('#ai-model').fill('editable-model');assert.equal(await page.locator('#ai-test').isDisabled(),true);await page.locator('#ai-save').click();await page.waitForFunction(()=>!document.querySelector('#ai-save').disabled);assert.equal(savedBody.model,'editable-model');assert.equal('api_key' in savedBody,false);
  for(const width of [1440,390,320]){await page.setViewportSize({width,height:1500});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`settings overflow ${width}`);await page.locator('#ai-settings-root').screenshot({path:path.join(out,`phase5-ai-settings-${width}.png`)});}
  await page.locator('#ai-provider').selectOption('custom');await page.locator('#ai-base-url').fill('https://custom.invalid/v1');await page.locator('#ai-model').fill('custom-model');assert.equal(await page.locator('#ai-key').inputValue(),'');await page.locator('#ai-save').click();assert.match(await page.locator('#ai-feedback').innerText(),/Key|密钥/);
  await page.locator('#ai-delete').click();await page.waitForFunction(()=>!document.querySelector('#ai-delete').disabled);assert.equal(config.has_api_key,false);assert(statusReads>=4);
  await page.locator('#settings-toggle').click();await page.setViewportSize({width:1440,height:1000});await page.locator('[data-workspace="portfolio"]').click();
  await page.locator('[data-add-source]').click();assert.match(await page.locator('#candidates').innerText(),/分享视频原题/);
  const item=page.locator('.portfolio-item').first(),button=item.locator('[data-ai-mapping]');await button.click();await item.locator('[data-field="fast"]').waitFor();
  assert.equal(await item.locator('[data-field="fast"]').inputValue(),'5');assert.equal(await item.locator('[data-field="confirmed"]').isChecked(),false);await item.locator('.ai-mapping-feedback summary').click();assert.match(await item.locator('.ai-mapping-feedback').innerText(),/五日均线/);assert.match(await item.locator('.ai-mapping-feedback').innerText(),/校正稿引文/);
  await page.locator('#add-manual').click();const second=page.locator('.portfolio-item').nth(1);mappingMode='delay';await button.click();await page.waitForFunction(()=>document.querySelector('[data-ai-mapping]').disabled);await second.locator('[data-field="name"]').fill('保持正在编辑的策略');mappingGate();await page.waitForFunction(()=>!document.querySelector('[data-ai-mapping]').disabled);assert.equal(await second.locator('[data-field="name"]').inputValue(),'保持正在编辑的策略');assert.equal(await second.locator('[data-field="name"]').evaluate(el=>el===document.activeElement),true,'AI completion must preserve other item editing focus');await second.locator('[data-remove]').click();
  await item.locator('[data-field="confirmed"]').check();mappingMode='delay';await button.click();await page.waitForFunction(()=>document.querySelector('[data-ai-mapping]').disabled);
  await item.locator('[data-field="fast"]').fill('8');assert(mappingGate);mappingGate();await page.waitForFunction(()=>!document.querySelector('[data-ai-mapping]').disabled);assert.equal(await item.locator('[data-field="fast"]').inputValue(),'8');assert.equal(await item.locator('[data-field="confirmed"]').isChecked(),false);
  for(const mode of ['stale','error','invalid','invalid-extra']){mappingMode=mode;await button.click();await page.waitForFunction(()=>!document.querySelector('[data-ai-mapping]').disabled);assert.equal(await item.locator('[data-field="fast"]').inputValue(),'8',mode+' preserves edits');}
  mappingMode='incomplete';await button.click();await item.locator('.ai-mapping-feedback').getByText(/尚缺目标仓位/).waitFor();assert.equal(await item.locator('[data-field="confirmed"]').isChecked(),false);assert.equal(await item.locator('[data-field="confirmed"]').isDisabled(),true);
  mappingMode='success';await button.click();await page.waitForFunction(()=>!document.querySelector('[data-ai-mapping]').disabled);await item.locator('.ai-mapping-feedback summary').click();
  for(const width of [1440,390,320]){await page.setViewportSize({width,height:1500});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`mapping overflow ${width}`);await item.screenshot({path:path.join(out,`phase5-ai-mapping-${width}.png`)});}
  await page.locator('#portfolio-name').fill('测试 AI 组合');await page.locator('#save-portfolio').click();await page.waitForFunction(()=>document.querySelector('#portfolio-save-state').textContent.includes('已保存'));
  assert.equal(portfolios[0].items[0].confirmed,false);assert.equal(portfolios[0].items[0].rules.fast,5);assert.equal('aiMapping' in portfolios[0].items[0],false);assert.equal(await page.locator('#backtest-portfolio option[value="p1"]').count(),1);assert.equal(await page.locator('#paper-portfolio option[value="p1"]').count(),1);
  mappingMode='delay';await button.click();await page.waitForFunction(()=>document.querySelector('[data-ai-mapping]').disabled);await page.locator('#new-portfolio').click();mappingGate();await page.waitForTimeout(50);assert.equal(await page.locator('.portfolio-item').count(),0);
  await page.locator('[data-workspace="materials"]').click();
  await page.locator('#library [data-id="doc-review"]').click();await page.locator('#ai-review-root').waitFor();assert.equal(await page.locator('#segments').isVisible(),false,'original full text stays folded');
  assert.match(await page.locator('#ai-review-root').innerText(),/已校正 1/);assert.equal(await page.locator('#ai-review-root details').getAttribute('open'),null);await page.locator('#ai-review-root summary').click();assert.match(await page.locator('#ai-review-root').innerText(),/原始转写/);assert.match(await page.locator('#ai-review-root').innerText(),/校正后/);
  assert.match(await page.locator('#strategy-content').innerText(),/引用校正稿/);assert.match(await page.locator('#strategy-content [data-evidence]').innerText(),/校正稿依据/);
  await page.locator('#ai-review-root').screenshot({path:path.join(out,'phase5-ai-review.png')});
  await page.locator('#library [data-id="other-doc"]').click();await page.locator('#ai-review-root').waitFor({state:'hidden'});assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'phase5-ai-result.json'),JSON.stringify({passed:true,fixtureOnly:true,actualProviderVerified:false,mountedFallback,widths:[1440,390,320],statusReads,testCalls,errors},null,2));console.log(JSON.stringify({passed:true,fixtureOnly:true,mountedFallback,statusReads,testCalls}));
}
run().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));});
