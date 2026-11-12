const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');

test('material handoff displays AI assumptions and verifies a manual replacement before saving', {timeout:30000}, async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH ||
    'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page = await browser.newPage({viewport:{width:320,height:844}});
    const frontend = path.resolve(__dirname, '../frontend');
    const quote = '放量时买入';
    const reason = '原文未提供成交量倍数。';
    const strategy = {title:'测试策略', rules:[], questions:[]};
    const segments = [{id:'s1',text:quote}];
    const material = {id:'one', title:'测试资料', source_type:'text', revision:2, segments, jobs:[],
      strategy, strategy_id:'source-test', strategy_revision:2};
    const source = {id:material.strategy_id, revision:2, title:strategy.title, strategy, transcript:segments};
    const clarifications = [{id:'volume',segment_id:'s1',quote,field:'volume_ratio',question:'确认放量定义',
      options:[{id:'ratio',label:'此前 20 根均量的 1.5 倍'}, {id:'strict',label:'此前 20 根均量的 2 倍'}]}];
    const decision = {question_id:'volume',segment_id:'s1',quote,field:'volume_ratio',option_id:'ratio',
      values:{period:20,multiple:1.5},label:clarifications[0].options[0].label,
      effective_clause:'日线量比(20)大于1.5时买入',basis:'assumption',reason};
    const evidence = [{field:'buy',segment_id:'s1',quote}];
    const result = {source_id:source.id,source_revision:2,timeframe:'daily',provider:'fixture',model:'fixture',
      mapping_note:'测试映射',questions:[],evidence,clarifications};
    const rules = multiple => ({type:'conditional',target_pct:20,stop_loss_pct:null,
      buy:{op:'gt',left:{indicator:'VOLUME_RATIO',params:{period:20}},right:{value:multiple}},
      sell:{op:'lt',left:{indicator:'CLOSE'},right:{value:10}}});
    const completes = [], replacements = [], errors = [];
    let mapping = null, saved;
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('http://127.0.0.1/**', async route => {
      const {pathname} = new URL(route.request().url());
      const method = route.request().method();
      if (pathname === '/api/status') return route.fulfill({json:{}});
      if (pathname === '/api/documents') return route.fulfill({json:[material]});
      if (pathname === '/api/documents/one') return route.fulfill({json:material});
      if (pathname === '/api/trading/capabilities') return route.fulfill({json:{rule_types:['conditional'],
        broker:{label:'本地模拟'},feeds:{},limitations:[],indicators:[{name:'VOLUME_RATIO',params:{period:{type:'integer'}}},{name:'CLOSE'}]}});
      if (pathname === '/api/trading/strategies') return route.fulfill({json:[{...source, ai_mapping:mapping}]});
      if (pathname === `/api/ai/strategies/${source.id}/mapping/complete`) {
        completes.push(route.request().postDataJSON());
        if (completes.length === 1) return route.fulfill({json:{...result,ready:false,rules:null,questions:['请明确其他交易条件。']}});
        mapping = {...result,ready:true,rules:rules(1.5),resolution_method:'ai',mapping_version:'ai-v1',decisions:[decision]};
        return route.fulfill({json:mapping});
      }
      if (pathname === `/api/ai/strategies/${source.id}/mapping`) {
        replacements.push(route.request().postDataJSON());
        if (replacements.length === 1) return route.fulfill({json:{...result,ready:false,rules:null,
          questions:['所选定义未通过完整规则校验。']}});
        mapping = {...result,ready:true,rules:rules(2),resolution_method:'manual',mapping_version:'manual-v2',
          decisions:[{...decision,label:clarifications[0].options[1].label,option_id:'strict',values:{period:20,multiple:2},
            effective_clause:'日线量比(20)大于2时买入',basis:undefined,reason:undefined}]};
        return route.fulfill({json:mapping});
      }
      if (pathname === '/api/trading/portfolios' && method === 'POST') {
        saved = route.request().postDataJSON();
        const items = saved.items.map(item=>({...item,source_snapshot:{...source,ai_mapping:mapping}}));
        return route.fulfill({json:{...saved,items,id:'portfolio-test',revision:1,readiness:{ready:true,errors:[],warnings:[]}}});
      }
      if (pathname.startsWith('/api/trading/')) return route.fulfill({json:[]});
      const filename = pathname === '/' ? 'index.html' : pathname.replace('/static/', '');
      const target = path.join(frontend, filename);
      if (/^\/static\/(?!(?:app|trading)\.js)[^/]+\.js$/.test(pathname)) return route.fulfill({body:'',contentType:'application/javascript'});
      if (!target.startsWith(frontend+path.sep) || !fs.existsSync(target)) return route.fulfill({status:404});
      return route.fulfill({path:target});
    });
    await page.goto('http://127.0.0.1/');
    await page.locator('[data-id="one"]').click();
    const complete = page.getByRole('button',{name:'让 AI 补全并生成执行规则',exact:true});
    await complete.waitFor({timeout:3000});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth), false);
    assert.equal(await page.locator('.strategy-footer button').evaluateAll(buttons=>buttons.every(button=>{
      const {left,right}=button.getBoundingClientRect();
      return left>=0&&right<=window.innerWidth;
    })),true);
    await complete.click();
    const item = page.locator('.portfolio-item');
    const confirm = item.locator('[data-field="confirmed"]');
    await item.getByText('请明确其他交易条件。').waitFor();
    assert.equal(await confirm.isDisabled(), true);
    assert.equal(await item.getByLabel('确认放量定义').isVisible(), true);
    await item.getByRole('button',{name:'让 AI 补全并生成执行规则',exact:true}).click();
    const decisions = item.locator('.ai-decisions');
    await decisions.getByText('AI 假设').waitFor();
    assert.match(await decisions.innerText(), /放量时买入.*此前 20 根均量的 1\.5 倍.*原文未提供成交量倍数。/s);
    assert.deepEqual(completes, [{source_revision:2},{source_revision:2}]);
    assert.equal(await confirm.isChecked(), false);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth), false);
    await confirm.check();
    await item.getByText('人工调整口径',{exact:true}).click();
    assert.equal(await item.getByLabel('确认放量定义').inputValue(),'ratio');
    await item.getByLabel('确认放量定义').selectOption('strict');
    await item.getByRole('button',{name:'应用选择并校验'}).click();
    await item.getByText('所选定义未通过完整规则校验。').waitFor();
    await decisions.getByText('AI 假设').waitFor({timeout:2000});
    assert.equal(await item.getByLabel('确认放量定义').inputValue(),'strict');
    assert.equal(await confirm.isChecked(), true);
    await item.getByRole('button',{name:'应用选择并校验'}).click();
    await decisions.getByText('人工选择').waitFor();
    assert.equal(await confirm.isChecked(), false);
    assert.deepEqual(replacements,[0,1].map(()=>({source_revision:2,mapping_version:'ai-v1',answers:[{question_id:'volume',option_id:'strict'}]})));
    await confirm.check();
    await page.locator('#save-portfolio').click();
    await page.getByText('已保存 · v1',{exact:true}).waitFor();
    await decisions.getByText('人工选择').waitFor();
    assert.equal(saved.items[0].mapping_version,'manual-v2');
    assert.deepEqual(saved.items[0].rules,rules(2));
    assert.deepEqual(errors,[]);
  } finally {
    await browser.close();
  }
});
