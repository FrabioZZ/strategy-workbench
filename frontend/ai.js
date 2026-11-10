'use strict';
(() => {
  const root=document.querySelector('#ai-settings-root');
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let saved=null,busy=false,dirty=false,version=0;
  const q=s=>root?.querySelector(s);
  async function request(path,options={}) {
    let response;
    try {response=await fetch('/api/ai'+path,{...options,headers:options.body?{'Content-Type':'application/json'}:{}});}
    catch {throw Error('无法连接本地服务，请确认程序仍在运行后重试。');}
    const data=await response.json().catch(()=>null);
    if(!response.ok)throw Error(typeof data?.detail==='string'?data.detail:`请求失败（HTTP ${response.status}）`);
    if(!data||typeof data!=='object')throw Error('服务返回格式不正确，请重试。');
    return data;
  }
  function feedback(text,error=false){q('#ai-feedback').textContent=text;q('#ai-feedback').classList.toggle('ai-error',error);}
  function destinationMatches(){return saved&&q('#ai-provider').value===saved.provider&&q('#ai-base-url').value.trim()===saved.base_url;}
  function controls(){
    q('#ai-fields').disabled=busy||!saved;
    q('#ai-save').disabled=busy||!saved;
    q('#ai-test').disabled=busy||dirty||!saved?.configured;
    q('#ai-delete').disabled=busy||!saved;
    q('#ai-reload').disabled=busy;
    q('#ai-key-hint').textContent=!destinationMatches()?'供应商或地址已改变，请填写该地址使用的新 Key。':saved?.has_api_key?'已在本机保存 Key；留空保留，填写则替换。已保存的 Key 不会返回浏览器。':'尚未保存 Key；本机 Ollama 等无需认证的服务可留空。';
  }
  function models(){const p=saved?.providers?.find(p=>p.id===q('#ai-provider').value);q('#ai-model-options').innerHTML=(p?.models||[]).map(m=>`<option value="${escape(m)}"></option>`).join('');}
  function render(config){
    saved=config;dirty=false;
    const providers=[...(config.providers||[])];
    if(config.provider&&!providers.some(p=>p.id===config.provider))providers.push({id:config.provider,label:config.provider});
    q('#ai-provider').innerHTML=providers.map(p=>`<option value="${escape(p.id)}">${escape(p.label)}</option>`).join('');
    q('#ai-provider').value=config.provider||providers[0]?.id||'';
    const preset=providers.find(p=>p.id===q('#ai-provider').value);
    q('#ai-base-url').value=config.base_url||(!config.provider?preset?.base_url:'')||'';q('#ai-model').value=config.model||(!config.provider?preset?.models?.[0]:'')||'';q('#ai-key').value='';
    q('#ai-storage-note').textContent=config.storage_note||'';
    q('#ai-saved-state').textContent=config.configured?`已配置 · ${config.provider} / ${config.model} · 连通性未测试`:'尚未完成 AI 配置';
    models();controls();
  }
  async function refreshShared(){
    try{if(typeof refreshConfig==='function')await refreshConfig();}
    catch{feedback('AI 设置已更新，但页面运行状态刷新失败；请点击“刷新状态”重试。',true);}
  }
  async function load(){
    if(busy)return;
    if(dirty){feedback('有未保存的设置，请先保存；重新打开页面可放弃这些修改。');return;}
    const token=++version;busy=true;controls();
    try{const config=await request('/config');if(token===version){render(config);feedback('保存只更新本机配置；请点击“测试已保存连接”验证供应商连通性。');}}
    catch(e){if(token===version)feedback(e.message,true);}
    finally{busy=false;controls();}
  }
  if(root){
    root.innerHTML=`<section class="ai-settings" aria-labelledby="ai-settings-title"><h3 id="ai-settings-title">AI 模型设置</h3><p class="helper">Key 仅在本机加密保存。调用时，认证凭据及待处理的转写、策略内容会发给你选择的供应商地址，不经过产品云端。</p><p id="ai-saved-state" class="helper">正在读取本机配置…</p><form id="ai-config-form"><fieldset id="ai-fields" disabled><legend class="ai-sr-only">供应商与模型</legend><div class="form-grid"><label>供应商<select id="ai-provider" required></select></label><label>模型 ID（可编辑）<input id="ai-model" list="ai-model-options" autocomplete="off" required maxlength="200"><datalist id="ai-model-options"></datalist></label></div><label>API 基础地址<input id="ai-base-url" type="url" placeholder="https://…/v1" autocomplete="off" required maxlength="2000"></label><label>API Key<input id="ai-key" type="password" autocomplete="new-password" spellcheck="false" autocapitalize="none" aria-describedby="ai-key-hint" placeholder="填写或替换 Key"></label><p id="ai-key-hint" class="helper"></p></fieldset><div class="action-row"><button id="ai-save" type="submit" class="primary" disabled>保存到本机</button><button id="ai-test" type="button" class="secondary" disabled>测试已保存连接</button><button id="ai-delete" type="button" class="quiet" disabled>删除本机 AI 配置</button><button id="ai-reload" type="button" class="quiet">重新读取</button></div></form><p id="ai-feedback" role="status" aria-live="polite"></p><p id="ai-storage-note" class="helper"></p></section>`;
    q('#ai-provider').addEventListener('change',()=>{const p=saved?.providers?.find(p=>p.id===q('#ai-provider').value);q('#ai-base-url').value=p?.base_url||'';q('#ai-model').value=p?.models?.[0]||'';q('#ai-key').value='';models();});
    q('#ai-fields').addEventListener('input',e=>{if(e.target.id==='ai-base-url')q('#ai-key').value='';dirty=true;version++;feedback('有未保存的设置。保存后再测试连接。');controls();});
    q('#ai-fields').addEventListener('change',()=>{dirty=true;version++;controls();});
    q('#ai-config-form').addEventListener('submit',async e=>{
      e.preventDefault();if(busy||!saved)return;
      const body={provider:q('#ai-provider').value,base_url:q('#ai-base-url').value.trim(),model:q('#ai-model').value.trim()};
      let secret=q('#ai-key').value.trim();
      if(!destinationMatches()&&!secret&&body.provider!=='ollama'){feedback('供应商或地址已改变，请填写新地址的 API Key 后保存。',true);return;}
      if(secret)body.api_key=secret;
      const token=++version;busy=true;q('#ai-key').value='';controls();feedback('正在加密保存到本机…');
      try{const config=await request('/config',{method:'PUT',body:JSON.stringify(body)});if(token===version){render(config);feedback('已保存到本机；保存不代表连通，连接尚未测试。');}await refreshShared();}
      catch(e){if(token===version)feedback(secret?e.message.split(secret).join('[已隐藏 Key]'):e.message,true);}
      finally{delete body.api_key;secret='';busy=false;controls();}
    });
    q('#ai-test').addEventListener('click',async()=>{
      if(busy||dirty||!saved?.configured)return;
      const token=++version;busy=true;controls();feedback('正在请求已保存的供应商地址测试连接…');
      try{const result=await request('/test',{method:'POST'});if(token===version){feedback(result.ok?'连接测试成功：已收到供应商响应。':'连接测试失败：'+(result.message||'供应商未返回有效响应。'),!result.ok);q('#ai-saved-state').textContent=`已配置 · ${saved.provider} / ${saved.model} · ${result.ok?'本次连接测试成功':'本次连接测试失败'}`;}}
      catch(e){if(token===version){feedback('连接测试失败：'+e.message,true);q('#ai-saved-state').textContent=`已配置 · ${saved.provider} / ${saved.model} · 本次连接测试失败`;}}
      finally{busy=false;controls();}
    });
    q('#ai-delete').addEventListener('click',async()=>{
      if(busy)return;
      const token=++version;busy=true;q('#ai-key').value='';controls();feedback('正在删除本机 AI 配置…');
      try{const config=await request('/config',{method:'DELETE'});if(token===version){render(config);feedback(config.configured?'用户保存的配置已删除；当前仍有本机默认配置生效，连通性未测试。':'本机 AI 配置和保存的 Key 已删除。');}await refreshShared();}
      catch(e){if(token===version)feedback(e.message,true);}
      finally{busy=false;controls();}
    });
    q('#ai-reload').addEventListener('click',load);
    document.querySelector('#refresh-status')?.addEventListener('click',load);
    load();
  }

  // Each render gets the corresponding document snapshot; never replace original transcript text.
  let lastDocument=null;
  function reviewDocument(d){
    if(!d)return;
    let panel=document.querySelector('#ai-review-root');
    if(!panel){const anchor=document.querySelector('#strategy-content');if(!anchor)return;panel=document.createElement('section');panel.id='ai-review-root';panel.className='ai-review';anchor.before(panel);}
    const review=d.ai_review,previousOpen=lastDocument===d.id&&panel.querySelector('details')?.open;lastDocument=d.id;
    panel.hidden=!review;
    if(!review){panel.innerHTML='';return;}
    const changes=Array.isArray(review.changes)?review.changes:[],questions=Array.isArray(review.questions)?review.questions:[];
    panel.innerHTML=`<h3>AI 校正与命名</h3><p>${escape(review.summary||'AI 校正结果待核对。')}</p>${d.strategy_stale?'<p class="ai-error">原始转写已修改；此校正结果属于旧版本，请重新提取。</p>':''}${questions.length?`<div class="ai-questions"><strong>需要你核对</strong><ul>${questions.map(x=>`<li>${escape(x)}</li>`).join('')}</ul></div>`:''}${changes.length?`<details ${previousOpen?'open':''}><summary>查看 ${changes.length} 处校正详情</summary>${changes.map(c=>`<article class="ai-change"><p class="helper">段落 ${escape(c.segment_id)} · ${escape(c.reason)}</p><dl><dt>原始转写</dt><dd>${escape(c.original)}</dd><dt>校正后</dt><dd>${escape(c.corrected)}</dd></dl></article>`).join('')}</details>`:'<p class="helper">没有记录文字修正；原始转写仍保留。</p>'}`;
    document.querySelectorAll('#strategy-content .evidence').forEach(el=>{
      const button=el.querySelector('[data-evidence]'),quote=el.querySelector('blockquote');if(!button||!quote)return;
      const id=button.dataset.evidence,text=quote.textContent.replace(/^“|”$/g,''),original=d.segments?.find(s=>s.id===id)?.text||'';
      if(original.includes(text))return;
      const change=changes.find(c=>c.segment_id===id&&String(c.corrected||'').includes(text));
      const note=document.createElement('p');note.className='ai-evidence-note';note.textContent=change?'此处引用校正稿，与原始识别文字不同。':'此处引文与当前原始段落不一致，请核对版本。';
      el.querySelector('.ai-evidence-note')?.remove();el.prepend(note);
      button.textContent=change?`↗ 校正稿依据 · 查看原始段落 ${id}`:`↗ 查看原始段落 ${id}，核对引文版本`;
    });
  }
  document.addEventListener('document-rendered',e=>reviewDocument(e.detail));
})();
