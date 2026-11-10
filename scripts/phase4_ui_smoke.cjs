// Real UI/API with explicit artificial quotes and holdings in an isolated server.
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),python=path.join(root,'.venv','Scripts','python.exe');
const folder=path.join(root,'.runtime',`phase4-ui-${Date.now()}`),out=path.join(root,'output','playwright');
const port=Number(process.env.UI_TEST_PORT||8898),base=`http://127.0.0.1:${port}`;
assert.notEqual(port,8765);
let server,browser,log='',expectedLocalFailure=false,expected503s=0;const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const watchdog=setTimeout(()=>{if(server)spawnSync('taskkill',['/pid',String(server.pid),'/t','/f'],{windowsHide:true});process.exit(2);},160000);
(async()=>{
  fs.mkdirSync(folder,{recursive:true});fs.mkdirSync(out,{recursive:true});
  await new Promise((resolve,reject)=>{const s=require('node:net').createServer();s.once('error',reject);s.listen(port,'127.0.0.1',()=>s.close(resolve));});
  server=spawn(python,['tests/quote_ui_server.py',folder,String(port)],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',b=>log+=b);server.stderr.on('data',b=>log+=b);
  for(let i=0;i<150;i++){try{if((await fetch(base+'/api/status')).ok)break;}catch{}if(i===149)throw Error(log);await sleep(100);}
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'){if(expectedLocalFailure&&m.text().includes('503'))expected503s++;else errors.push(m.text());}});
  page.setDefaultTimeout(15000);
  const post=async(url,body={})=>{const r=await page.request.post(base+url,{data:body});assert.equal(r.ok(),true,await r.text());return r.json();};
  const get=async(url)=>{const r=await page.request.get(base+url);assert.equal(r.ok(),true,await r.text());return r.json();};
  await page.goto(base+'/#paper');
  await page.locator('#quote-direct').waitFor({state:'visible'});
  assert.match(await page.locator('#quote-account-result').innerText(),/没有增量模拟账户/);
  await page.locator('#quote-code').fill('600000.SH');await page.locator('#quote-direct button').click();
  await page.locator('.quote-price').getByText('10.10',{exact:true}).waitFor();
  assert.equal((await get('/api/trading/portfolios')).length,0);
  assert.equal((await get('/api/trading/paper/sessions')).length,0);
  await post('/__test__/catalog');await page.reload();
  await page.locator('[data-quote-symbol="000001.SZ"]').waitFor();
  assert.match(await page.locator('#quote-universe').innerText(),/300只/);
  await page.locator('#quote-search').fill('宁德');
  assert.equal(await page.locator('[data-quote-symbol]').count(),1);
  await post('/__test__/clock',{seconds:3});
  await page.locator('[data-quote-symbol="300750.SZ"]').click();
  await page.locator('.quote-card .quote-code').getByText('300750.SZ',{exact:true}).waitFor();
  assert.notEqual(await page.locator('.quote-price').innerText(),'—');
  const cached=(await get('/__test__/state')).calls;
  await page.locator('#quote-refresh').click();await page.locator('#quote-refresh').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('#quote-refresh').disabled);
  assert.equal((await get('/__test__/state')).calls,cached,'manual read must share cache');
  // Real 45-second page timer. Provider time also advances; price is an explicit fixture.
  const old=await page.locator('.quote-price').innerText(),before=Date.now();
  await page.waitForFunction(value=>document.querySelector('.quote-price')?.textContent!==value,old,{timeout:60000});
  const automaticElapsedMs=Date.now()-before;
  assert(automaticElapsedMs>30000 && automaticElapsedMs<60000,`auto interval ${automaticElapsedMs}`);
  await post('/__test__/accounts');await post('/__test__/clock',{seconds:46});
  await page.locator('#quote-refresh').click();
  await page.locator('#quote-account option').nth(1).waitFor({state:'attached'});
  await page.locator('#quote-account').selectOption({label:'持仓账户（测试）'});
  await page.locator('.quote-position').waitFor();
  assert.match(await page.locator('#quote-account-result').innerText(),/8,000.00/);
  const result=await get('/api/trading/quotes/overview?symbols=300750.SZ');
  const held=result.accounts.find(a=>a.name.startsWith('持仓'));
  assert.equal(held.total_assets,8000+held.positions[0].quote.price*200);
  assert.equal(held.unrealized_pnl,held.market_value-1900);
  assert.match(await page.locator('#quote-historical').innerText(),/1 个历史回放/);
  const ledgerBefore=await get('/api/trading/paper/sessions');
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:1000});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
    assert.equal(overflow,false,`overflow at ${width}`);
    await page.locator('#quote-panel').screenshot({path:path.join(out,`phase4-quotes-${width}.png`)});
  }
  await page.locator('#quote-account').selectOption({label:'现金账户（测试）'});
  assert.match(await page.locator('#quote-account-result').innerText(),/当前空仓/);
  assert.match(await page.locator('#quote-account-result').innerText(),/10,000.00/);
  await post('/__test__/clock',{seconds:46,fault:true});await page.locator('#quote-refresh').click();
  await page.locator('#quote-result').getByText('源故障',{exact:true}).waitFor();
  await page.locator('#quote-account').selectOption({label:'持仓账户（测试）'});
  assert.match(await page.locator('#quote-account-result').innerText(),/暂不计算总资产/);
  await post('/__test__/clock',{seconds:300,fault:false});await page.locator('#quote-refresh').click();
  await page.locator('#quote-result').getByText('已收到快照',{exact:true}).waitFor();
  // Explicit local connection failure must not resurrect an old valuation on account selection.
  expectedLocalFailure=true;
  await page.route('**/api/trading/quotes/overview*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'explicit test-only connection outage'})}));
  await page.locator('#quote-refresh').click();
  await page.locator('#quote-feedback').getByText(/本地报价服务连接失败/).waitFor();
  await page.locator('#quote-account').selectOption({label:'现金账户（测试）'});
  assert.match(await page.locator('#quote-account-result').innerText(),/无法取得账户快照/);
  expectedLocalFailure=false;
  await page.unroute('**/api/trading/quotes/overview*');
  await page.locator('#quote-refresh').click();
  await page.locator('#quote-result').getByText('已收到快照',{exact:true}).waitFor();
  const ledgerAfter=await get('/api/trading/paper/sessions');
  assert.deepEqual(ledgerAfter,ledgerBefore,'quotes cannot modify ledgers');
  // Accelerated browser clock verifies switching workspaces pauses the page poll.
  await page.clock.install();let overviewRequests=0;
  page.on('request',r=>{if(r.url().includes('/quotes/overview'))overviewRequests++;});
  await page.locator('[data-workspace="backtest"]').click();
  await page.clock.fastForward(46000);assert.equal(overviewRequests,0);
  await page.locator('[data-workspace="paper"]').click();
  await page.waitForFunction(()=>!document.querySelector('#quote-refresh').disabled);
  assert.equal(overviewRequests,1);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await page.clock.fastForward(46000);assert.equal(overviewRequests,1,'hidden page polling pauses');
  await page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>!document.querySelector('#quote-refresh').disabled);
  assert.equal(overviewRequests,2,'visible page refreshes on return');
  assert.equal(errors.length,0,errors.join('\n'));
  const report={passed:true,artificial_market_fixture:true,automaticElapsedMs,errors,expected503s,controlledVisibilityTest:true,widths:[320,390,1440],accounts:result.accounts,runDir:folder};
  fs.writeFileSync(path.join(folder,'result.json'),JSON.stringify(report,null,2));
  fs.writeFileSync(path.join(out,'phase4-result.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({passed:true,automaticElapsedMs,errors,runDir:folder}));
})().catch(e=>{console.error(e);fs.writeFileSync(path.join(folder,'failure.txt'),e.stack);process.exitCode=1;}).finally(async()=>{
  clearTimeout(watchdog);if(browser)await browser.close();
  if(server){
    const killed=spawnSync('taskkill',['/pid',String(server.pid),'/t','/f'],{windowsHide:true,encoding:'utf8'});
    if(killed.status!==0){console.error('Isolated server cleanup failed: '+killed.stderr);server.kill();process.exitCode=1;}
    server.stdout.destroy();server.stderr.destroy();server.unref();
  }
  fs.writeFileSync(path.join(folder,'server.log'),log);
});
