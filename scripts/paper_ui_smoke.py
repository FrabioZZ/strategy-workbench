"""Bounded real-browser acceptance. Creates isolated data; never uses formal data/."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JS = r'''
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=process.cwd(), port=Number(process.env.PAPER_UI_PORT||8894), base=`http://127.0.0.1:${port}`;
const dataDir=path.join(root,'.runtime',`paper-ui-${Date.now()}`);
const output=path.join(root,'output','playwright');
let server,browser,logs='';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function post(url,body){const r=await fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});assert.ok(r.ok,await r.clone().text());return r.json();}
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  await new Promise((resolve,reject)=>{const s=require('node:net').createServer();s.once('error',reject);s.listen(port,'127.0.0.1',()=>s.close(resolve));});
  server=spawn(path.join(root,'.venv','Scripts','python.exe'),['scripts/paper_ui_smoke.py','--serve',dataDir,String(port)],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  server.stderr.on('data',b=>logs+=b.toString());server.stdout.on('data',b=>logs+=b.toString());
  for(let i=0;i<100;i++){try{if((await fetch(base+'/api/status')).ok)break;}catch{}if(i===99)throw Error(logs);await pause(100);}
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(base+'/#paper');
  await page.locator('#pex-capability').getByText(/已安装/).waitFor();
  assert.equal(await page.locator('#pex-portfolio option').count(),1);
  const p=await post('/api/trading/portfolios',{name:'浏览器隔离策略',items:[{id:'a',name:'价格规则',enabled:true,confirmed:true,mapping_note:'测试中显式确认规则',rules:{type:'threshold',buy_below:10,sell_above:11,target_pct:90}}]});
  const ds=await post('/api/trading/datasets/import',{name:'浏览器演示行情',source:'隔离人工测试夹具',is_demo:true,ordinary_stock_confirmed:true,corporate_actions_confirmed_absent:true,csv_text:
    'date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'+
    '2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n'+
    '2026-01-06,600000.SH,10,10.4,10,10.4,100000,9.5,10.45,8.55\n'+
    '2026-01-07,600000.SH,10.5,11.4,10.5,11.4,100000,10.4,11.44,9.36\n'+
    '2026-01-08,600000.SH,12,12,11,11.5,100000,11.4,12.54,10.26\n'});
  await page.locator('#pex-refresh').click();await page.locator(`#pex-portfolio option[value="${p.id}"]`).waitFor({state:'attached'});
  await page.locator('.pex-create > summary').click();
  await page.locator('#pex-name').fill('外部引擎浏览器验收');await page.locator('#pex-portfolio').selectOption(p.id);await page.locator('#pex-dataset').selectOption(ds.id);
  await page.locator('#pex-cash').fill('10000');await page.locator('#pex-create').click();
  await page.locator('[data-pex-action="step"]').waitFor();
  await page.locator('[data-pex-action="step"]').click();await page.locator('#pex-result').getByText(/1 \/ 4 根/).waitFor();
  assert.equal(await page.locator('#pex-result').getByText(/0 笔成交/).count(),1);
  await page.locator('[data-pex-action="run"]').click();await page.locator('#pex-result').getByText('演示 · 回放完成',{exact:true}).waitFor();
  assert.equal(await page.locator('[data-pex-action="run"]').isDisabled(),true);
  await page.locator('#pex-result').getByText(/3 笔成交/).waitFor();
  const sessions=await (await fetch(base+'/api/trading/external-paper/sessions')).json();assert.equal(sessions.length,1);assert.equal(sessions[0].fills.length,3);
  assert.equal((await (await fetch(base+'/api/trading/paper/sessions')).json()).length,0);
  assert.ok(!Object.keys(sessions[0]).some(k=>k.startsWith('_')));
  const downloadPromise=page.waitForEvent('download');await page.locator('[data-pex-export]').click();const download=await downloadPromise;
  await download.saveAs(path.join(output,'paper-external-export.json'));
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:900});await page.locator('#pex-panel').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow at ${width}`);
    await page.screenshot({path:path.join(output,`paper-external-${width}.png`),fullPage:true});
  }
  await page.reload();await page.locator('#pex-history option[value="'+sessions[0].id+'"]').waitFor({state:'attached'});
  await page.locator('#pex-history').selectOption(sessions[0].id);await page.locator('#pex-result').getByText('演示 · 回放完成',{exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'paper-external-result.json'),JSON.stringify({passed:true,browser_errors:errors,session:sessions[0],isolated_data_dir:dataDir},null,2));
  console.log(JSON.stringify({passed:true,browser_errors:errors,widths:[320,390,1440],fills:sessions[0].fills.length,cash:sessions[0].cash}));
})().catch(e=>{console.error(e.stack);console.error(logs);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
'''


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--serve':
        import uvicorn
        from app.config import Settings
        from app.main import create_app
        uvicorn.run(create_app(Settings(data_dir=Path(sys.argv[2]))), host='127.0.0.1', port=int(sys.argv[3]))
    else:
        node = shutil.which('node')
        if not node:
            raise SystemExit('Node.js is required for browser verification')
        process = subprocess.Popen([node, '-e', JS], cwd=ROOT, env=os.environ.copy(),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output, _ = process.communicate(timeout=150)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], capture_output=True, timeout=10)
            output, _ = process.communicate(timeout=10)
            print(output.decode('utf-8', errors='replace'))
            raise SystemExit('Browser check exceeded 150 seconds; own process tree stopped')
        evidence = ROOT / '.runtime' / 'paper-evidence'
        evidence.mkdir(exist_ok=True, parents=True)
        evidence.joinpath('browser.log').write_bytes(output)
        print(output.decode('utf-8', errors='replace'))
        raise SystemExit(process.returncode)
