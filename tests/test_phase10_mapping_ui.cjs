// Exercise the portfolio editor with fixture responses. No server or model is called.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');

test('strategy clarifications can be retried and still require portfolio confirmation', {timeout:30000}, async () => {
  const browser = await chromium.launch({
    executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless:true,
  });
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const frontend = path.resolve(__dirname,'../frontend');
    const segment = {id:'s1',start:2,end:6,text:'放量时买入，RSI 在 20 以下钝化时清仓。'};
    const source = {id:'source-test',revision:2,title:'术语示例',transcript:[segment],strategy:{title:'术语示例',rules:[]}};
    const result = {source_id:source.id,source_revision:2,provider:'fixture',model:'fixture',timeframe:'daily',mapping_note:'测试映射',questions:[],evidence:[]};
    const clarifications = [
      {id:'volume',segment_id:'s1',quote:'放量时买入',field:'buy',question:'确认放量定义',options:[{id:'ratio',label:'成交量 > 20 日均量 × 1.5'}],custom_fields:[{name:'period',label:'均量周期',min:1,max:250,step:1},{name:'ratio',label:'放量倍数',min:0.01,max:100,step:'any'}]},
      {id:'rsi',segment_id:'s1',quote:'RSI 在 20 以下钝化时清仓',field:'sell',question:'确认钝化定义',options:[{id:'three',label:'连续 3 根低于 20'}]},
    ];
    const rules = {type:'threshold',target_pct:20,stop_loss_pct:null,buy_below:10,sell_above:20};
    const submissions = [];
    let saved;
    const errors = [];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('http://127.0.0.1/**', async route => {
      const {pathname} = new URL(route.request().url());
      if (pathname === '/api/status') return route.fulfill({json:{}});
      if (pathname === '/api/trading/strategies') return route.fulfill({json:[source]});
      if (pathname === '/api/trading/capabilities') return route.fulfill({json:{rule_types:['threshold'],broker:{label:'本地模拟'},feeds:{},limitations:[]}});
      if (pathname === '/api/trading/portfolios' && route.request().method()==='POST') {
        saved = route.request().postDataJSON();
        return route.fulfill({json:{...saved,id:'portfolio-test',revision:1,readiness:{ready:true,errors:[],warnings:[]}}});
      }
      if (pathname.startsWith('/api/trading/') || pathname === '/api/documents') return route.fulfill({json:[]});
      if (pathname === `/api/ai/strategies/${source.id}/mapping`) {
        const input = route.request().postDataJSON();
        if (!input) return route.fulfill({json:{...result,ready:false,rules:null,clarifications}});
        submissions.push(input);
        if (submissions.length === 1) return route.fulfill({status:409,json:{detail:'测试：请重试提交'}});
        return route.fulfill({json:{...result,ready:true,rules,clarifications:[]}});
      }
      const filename = pathname === '/' ? 'index.html' : pathname.replace('/static/', '');
      const target = path.join(frontend, filename);
      if (/^\/static\/(?!(?:app|trading)\.js)[^/]+\.js$/.test(pathname)) return route.fulfill({body:'',contentType:'application/javascript'});
      if (!target.startsWith(frontend+path.sep) || !fs.existsSync(target)) return route.fulfill({status:404});
      return route.fulfill({path:target});
    });
    await page.goto('http://127.0.0.1/#portfolio');
    await page.locator('[data-add-source]').click();
    await page.locator('#portfolio-name').fill('策略口径测试');
    const item = page.locator('.portfolio-item');
    await item.locator('[data-field="timeframe"]').selectOption('5m');
    await item.getByRole('button',{name:'AI 生成执行参数'}).click();
    await item.getByText('放量时买入',{exact:false}).waitFor({timeout:4000});
    assert.equal(await item.locator('[data-field="confirmed"]').isDisabled(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
    await item.getByLabel('确认放量定义',{exact:true}).selectOption('custom');
    await item.getByLabel('均量周期',{exact:true}).fill('15');
    await item.getByLabel('放量倍数',{exact:true}).fill('1.8');
    await item.getByLabel('确认钝化定义',{exact:true}).selectOption('three');
    await item.getByRole('button',{name:'应用选择并校验'}).click();
    await item.getByText('测试：请重试提交').waitFor();
    assert.equal(await item.getByLabel('均量周期',{exact:true}).inputValue(),'15');
    assert.equal(await item.getByLabel('确认钝化定义',{exact:true}).inputValue(),'three');
    assert.equal(await item.locator('[data-field="confirmed"]').isDisabled(),true);
    await item.getByRole('button',{name:'应用选择并校验'}).click();
    await item.getByText('参数已回填', {exact:false}).waitFor();
    assert.deepEqual(submissions,[0,1].map(()=>({source_revision:2,answers:[
      {question_id:'volume',option_id:'custom',values:{period:15,ratio:1.8}},
      {question_id:'rsi',option_id:'three'},
    ]})));
    assert.equal(await item.locator('[data-field="timeframe"]').inputValue(),'daily');
    assert.equal(await item.locator('[data-field="confirmed"]').isChecked(),false);
    await item.locator('[data-field="confirmed"]').check();
    await page.locator('#save-portfolio').click();
    await page.getByText('已保存 · v1').waitFor();
    assert.deepEqual(saved.items[0].rules,rules);
    assert.equal(saved.items[0].timeframe,'daily');
    assert.equal(saved.items[0].confirmed,true);
    assert.deepEqual(errors,[]);
  } finally {
    await browser.close();
  }
});
