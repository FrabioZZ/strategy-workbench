'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const state = {documents: [], current: null, config: null, tab: 'upload', dirty: false, working: false, timer: null, wakeLock: null, wakePending: false};
const labels = {upload:'本地媒体',url:'平台资料',text:'文本',subtitle:'字幕',buy:'买入条件',sell:'卖出条件',position:'仓位管理',stop_loss:'止损条件',filter:'筛选条件',other:'其他规则'};
const mediaLabels = {downloading:'正在获取媒体',transcribing:'正在转写',transcribed:'转写已完成',awaiting_transcription:'已获取，待转写',transcription_failed:'转写失败，缓存已保留',download_failed:'媒体获取失败',not_acquired:'尚未获取媒体'};
const activeJob = d => d?.jobs?.find(j => ['queued','running'].includes(j.status));
function rememberDocument(id) {try {if(id)localStorage.setItem('quant-current-document',id);else localStorage.removeItem('quant-current-document');} catch { /* Storage is optional. */ }}
function rememberedDocument() {try {return localStorage.getItem('quant-current-document');} catch {return null;}}
async function syncWakeLock() {
  const needed=!!activeJob(state.current) && document.visibilityState==='visible';
  if(!needed && state.wakeLock){const lock=state.wakeLock;state.wakeLock=null;try{await lock.release();}catch{}return;}
  if(!needed || state.wakeLock || state.wakePending || !navigator.wakeLock?.request)return;
  state.wakePending=true;
  try {
    const lock=await navigator.wakeLock.request('screen');
    if(!activeJob(state.current) || document.visibilityState!=='visible'){await lock.release();return;}
    state.wakeLock=lock;
    lock.addEventListener('release',()=>{if(state.wakeLock===lock)state.wakeLock=null;});
  } catch { /* Browser/OS may refuse the wake lock. */ }
  finally {state.wakePending=false;}
}
function timeLabel(value) {if (value == null) return '无时间戳'; const n = Math.floor(value); return `${String(Math.floor(n / 60)).padStart(2,'0')}:${String(n % 60).padStart(2,'0')}`;}
function notify(message, error=false) {const el = $('#notice'); el.hidden=false; el.className=error?'error':''; el.textContent=message; if(error) el.scrollIntoView({block:'nearest'});}
async function api(path, options={}) {
  let response;
  try {response = await fetch(path, {...options, headers: {...(options.body && !(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {}), ...options.headers}});}
  catch {throw new Error('无法连接本地服务，请确认服务仍在运行后重试。');}
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || `请求失败（HTTP ${response.status}）`);
  return data;
}
async function action(fn) {try {await fn();} catch (error) {notify(error.message, true);}}
async function refreshConfig() {
  state.config = await api('/api/status'); const c=state.config;
  $('#configuration-status').innerHTML = `<div class="config-row"><strong>语音转写</strong><span class="${c.asr_configured?'':'not-ready'}">${esc(c.asr_note)}</span></div><div class="config-row"><strong>策略提取</strong><span class="${c.ai_configured?'':'not-ready'}">${esc(c.ai_note)}</span></div>`;
  $('#asr-import-hint').textContent = `${c.asr_configured ? `转写服务已配置：${c.asr_provider || 'local'} / ${c.asr_model || 'faster-whisper'}` : "语音转写未配置，请先打开运行配置"}。上限 ${c.max_upload_mb} MB / ${c.max_duration_minutes} 分钟。`;
  updateImportButton();
  if(state.current) updateButtons();
  $('#ai-hint').textContent = c.ai_configured ? `提取使用 ${c.ai_provider || '已配置服务'} / ${c.ai_model}，转写内容将发送到该服务。` : 'AI 尚未配置。请在“运行配置”中选择服务和模型；转写与校对可先完成。';
}
async function refreshLibrary() {state.documents = await api('/api/documents'); renderLibrary();}
function renderLibrary() {
  const query=$('#search').value.trim().toLowerCase();
  const docs=state.documents.filter(d=>d.title.toLowerCase().includes(query));
  $('#document-count').textContent=state.documents.length;
  $('#library').innerHTML = docs.length ? docs.map(d=>`<button class="library-item" data-id="${esc(d.id)}" aria-current="${state.current?.id===d.id}"><strong>${esc(d.title)}</strong><span>${d.is_demo?'示例 · ':''}${esc(labels[d.source_type])} · ${esc(new Date(d.updated_at).toLocaleDateString('zh-CN'))}</span></button>`).join('') : `<p class="muted">${query?'没有匹配的资料。':'导入第一份资料后，它会保存在这里。'}</p>`;
}
function allowLeave() {return !state.dirty || window.confirm('当前转写有未保存的修改，确定放弃这些修改吗？');}
async function selectDocument(id, ask=true) {
  if (ask && !allowLeave()) return;
  const d=await api(`/api/documents/${id}`);
  state.documents=state.documents.map(item=>item.id===id?{...item,title:d.title,updated_at:d.updated_at}:item);
  state.current=d; state.dirty=false; state.working=false; rememberDocument(id);
  $('#import-view').hidden=true; $('#document-view').hidden=false; $('#notice').hidden=true; $('#poll-warning').hidden=true;
  renderDocument(); renderLibrary(); schedulePoll();
}
function renderDocument() {
  const d=state.current;
  $('#document-title').textContent=d.title;
  $('#document-meta').textContent=`${labels[d.source_type]} · 转写版本 ${d.revision} · ${d.segments.length} 个段落`;
  $('#document-badge').textContent=d.strategy_stale?'草案已过期':d.strategy?'草案待核对':d.segments.length?'待提取':(mediaLabels[d.media_status]||'待转写');
  $('#demo-notice').hidden=!d.is_demo;
  const mediaJob=d.jobs.find(j=>['download','transcribe'].includes(j.kind) && ['queued','running'].includes(j.status));
  const complete=!!d.segments.length && !mediaJob;
  $('#transcription-state').className=`transcription-state${complete?' complete':''}`;
  $('#transcription-icon').textContent=complete?'✓':mediaJob?'…':'○';
  $('#transcript-title').textContent=mediaJob?(mediaJob.kind==='download'?'正在获取媒体':'正在识别'):complete?(['text','subtitle'].includes(d.source_type)?'原文已就绪':'转写完成'):d.has_media?(!state.config?.asr_configured?'待配置语音转写':'转写尚未完成'):'等待获取媒体';
  $('#transcript-summary').textContent=complete?'可以提取策略，或展开原文校对。':mediaJob?'处理中，完成后可提取策略。':d.has_media?'已保留本机缓存，可继续转写，无需重新下载。':'导入的媒体获取成功后，将本地模式自动接续转写；云模式需手动开始。';
  const review=$('#transcript-review');
  if(review.dataset.document!==d.id){review.open=false;review.dataset.document=d.id;}
  review.hidden=!d.segments.length;
  $('#transcript-review-count').textContent=`${d.segments.length} 个段落 · 含时间与证据定位`;
  $('#segments').innerHTML=d.segments.map(segmentMarkup).join('');
  const metadata=d.media_metadata||{};
  $('#source-details').innerHTML=d.source_url?`来源：<a href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">${esc(d.source_url)}</a>${metadata.title?` · 平台标题：${esc(metadata.title)}`:''}`:'';
  const hasMedia=d.has_media;
  $('#media-container').hidden=!hasMedia;
  $('#media-file-link').href=`/api/documents/${d.id}/media`;
  $('#media-description').textContent=hasMedia?`原始媒体已缓存${metadata.duration_seconds!=null?` · 时长 ${timeLabel(metadata.duration_seconds)}`:''}${metadata.size_bytes!=null?` · ${(metadata.size_bytes/1024/1024).toFixed(2)} MB`:''}`:'';
  $('#transcribe-actions').hidden=!hasMedia || !!d.segments.length || !!activeJob(d);
  renderJob(); renderStrategy(); updateButtons(); syncWakeLock();
  document.dispatchEvent(new CustomEvent('document-rendered',{detail:d}));
}
function segmentMarkup(s) {
  return `<div class="segment" id="segment-${esc(s.id)}" data-segment="${esc(s.id)}"><label for="text-${esc(s.id)}"><strong>${esc(timeLabel(s.start))}${s.end==null?'':` – ${esc(timeLabel(s.end))}`}</strong><span>段落 ${esc(s.id.slice(1))}</span></label><textarea id="text-${esc(s.id)}" class="segment-text" maxlength="10000" rows="3">${esc(s.text)}</textarea><details class="time-editor"><summary>调整时间 / 段落</summary><div class="time-fields"><label>开始（秒）<input class="segment-start" type="number" min="0" step="0.001" value="${s.start??''}" placeholder="未知则留空"></label><label>结束（秒）<input class="segment-end" type="number" min="0" step="0.001" value="${s.end??''}" placeholder="未知则留空"></label></div><button class="remove-segment" type="button">移除此段</button></details></div>`;
}
function readSegments() {return [...document.querySelectorAll('[data-segment]')].map(el=>({id:el.dataset.segment, text:el.querySelector('.segment-text').value.trim(), start:el.querySelector('.segment-start').value===''?null:Number(el.querySelector('.segment-start').value), end:el.querySelector('.segment-end').value===''?null:Number(el.querySelector('.segment-end').value)}));}
function markDirty() {state.dirty=true;updateButtons();}
function updateButtons() {
  const busy=state.working || !!activeJob(state.current);
  $('#save-transcript').disabled=!state.dirty || busy;
  $('#extract').disabled=!state.current?.segments.length || busy;
  $('#extract').textContent=activeJob(state.current)?.kind==='extract'?'提取中…':state.dirty?'保存并提取':'提取策略';
  $('#export').disabled=!state.current?.strategy || state.current.strategy_stale || state.dirty || busy;
  $('#add-segment').disabled=busy;
  $('#transcribe').disabled=busy || !state.current?.has_media || !state.config?.asr_configured || !!state.current?.segments.length;
  $('#transcribe').textContent=state.current?.media_status==='transcription_failed'?'重试缓存转写':'开始转写';
  $('#transcribe-hint').textContent=state.config?.asr_configured?(state.config.asr_provider==='qwen'?`使用 Qwen / ${state.config.asr_model}，联网并上传缓存音频与上下文，按 Token 计费。重试优先继续查询已有任务。`:'使用本机缓存转写，无需重新下载。'):'媒体已保存在本机。请在运行配置中选择 ASR 语音服务；本地模型或独立 Qwen 凭据配置后可继续转写。';
  $('#save-state').textContent=state.dirty?'有未保存的修改':'已保存到本机';
  document.querySelectorAll('[data-evidence]').forEach(el=>el.disabled=state.dirty || state.current?.strategy_stale);
  document.querySelectorAll('#segments textarea,#segments input,#segments button').forEach(el=>el.disabled=busy);
}
function renderJob() {
  const j=activeJob(state.current)||state.current?.jobs[0], el=$('#job-status');
  if(!j || j.status==='succeeded') {el.hidden=true;return;}
  el.hidden=false;const busy=['queued','running'].includes(j.status);el.className=busy?'running':'failed';
  const message=busy?(j.kind==='transcribe'?'识别中，请保持程序打开并保持设备唤醒。':j.kind==='download'?'正在获取媒体。本地模式自动接续，云模式需手动开始。请保持程序打开并保持设备唤醒。':'正在处理策略，请保持程序打开并保持设备唤醒。'):(j.error||'任务未完成，请重试。');
  el.innerHTML=`<div class="job-heading"><strong>${esc(j.stage)}</strong>${busy?'':`<button class="secondary" data-retry="${esc(j.id)}" ${j.kind==='transcribe'&&!state.config?.asr_configured?'disabled':''}>${j.kind==='download'?'重试获取并转写':j.kind==='transcribe'?'重试缓存转写':'重试提取'}</button>`}</div><p>${esc(message)}</p>${busy?'<div class="indeterminate-progress" role="progressbar" aria-label="正在处理，进度暂不可确定"><span></span></div>':''}`;
}
function evidenceMarkup(evidence) {return evidence.map(e=>{const corrected=e.transcript_version==='corrected';return `<div class="evidence"><button type="button" data-evidence="${esc(e.segment_id)}" data-transcript-version="${corrected?'corrected':'original'}" data-time="${e.start??''}">↗ ${esc(timeLabel(e.start))} · ${corrected?'校正版依据 · 对照原始段落':'查看原始段落'} ${esc(e.segment_id.slice(1))}</button><blockquote>“${esc(e.quote)}”</blockquote></div>`;}).join('');}
function renderStrategy() {
  const d=state.current,s=d.strategy;
  if(!s) {$('#strategy-content').innerHTML='<div class="empty-state"><span aria-hidden="true">引</span><h3>从原话形成有依据的草案</h3><p>转写完成后点击“提取策略”。这里将显示买卖条件、仓位、止损和对应原文依据。</p></div>';return;}
  $('#strategy-content').innerHTML=`<div class="strategy-body">${d.strategy_stale?'<div class="stale">转写已修改。这份草案属于旧版本，请重新提取后导出；旧引用不再定位当前原文。</div>':''}<h3>${esc(s.title)}</h3><p class="draft-note">草案 · 待人工复核 · ${esc(d.strategy_provider)} / ${esc(d.strategy_model)} · 来源版本 ${d.strategy_revision}</p><dl class="facts"><div><dt>标的 / 范围</dt><dd>${esc(s.asset?.value||'原文未明确')}</dd></div><div><dt>观察 / 持仓周期</dt><dd>${esc(s.timeframe?.value||'原文未明确')}</dd></div></dl>${s.asset?evidenceMarkup(s.asset.evidence):''}${s.timeframe?evidenceMarkup(s.timeframe.evidence):''}${s.rules.map(r=>`<article class="rule"><h4>${esc(labels[r.kind])}</h4><p>${esc(r.text)}</p>${r.needs_clarification?'<span class="clarification">含模糊条件，需进一步澄清</span>':''}${evidenceMarkup(r.evidence)}</article>`).join('') || '<p class="muted">未提取到有依据的交易规则。</p>'}<section class="questions"><h3>待澄清与核对</h3><ul>${s.questions.map(q=>`<li>${esc(q)}</li>`).join('')}</ul><p class="draft-note">${esc(s.notice)}</p></section></div>`;
  if(d.strategy_stale) document.querySelectorAll('[data-evidence]').forEach(b=>b.disabled=true);
}
async function saveTranscript() {
  if(!state.dirty)return;
  const segments=readSegments();
  if(!segments.length || segments.some(s=>!s.text))throw new Error('至少保留一段非空原文；空段落请填写或移除。');
  if(segments.some(s=>(s.start==null)!==(s.end==null) || (s.start!=null && s.end<s.start)))throw new Error('请同时填写开始和结束秒数，且结束不能早于开始。');
  const ident=state.current.id, revision=state.current.revision;
  state.working=true;updateButtons();
  try {
    const saved=await api(`/api/documents/${ident}/transcript`,{method:'PUT',body:JSON.stringify({revision,segments})});
    if(state.current?.id===ident){state.current=saved;state.dirty=false;renderDocument();notify('转写已保存到本机。');}
    await refreshLibrary();
  } finally {state.working=false;updateButtons();}
}
function schedulePoll() {
  clearTimeout(state.timer);
  if(!activeJob(state.current))return;
  const id=state.current.id;
  state.timer=setTimeout(async()=>{
    try {
      const next=await api(`/api/documents/${id}`);
      if(state.current?.id!==id)return;
      const previous=state.current;
      state.current=next;$('#poll-warning').hidden=true;
      if(JSON.stringify(next.jobs)!==JSON.stringify(previous.jobs) || next.media_status!==previous.media_status || next.revision!==previous.revision){renderDocument();}
      if(!activeJob(next))await refreshLibrary();
    } catch {
      if(state.current?.id===id){$('#poll-warning').hidden=false;$('#poll-warning').textContent='暂时无法连接本机服务，正在自动重连；尚未确认任务完成。请保持程序打开。';}
    } finally {if(state.current?.id===id)schedulePoll();}
  },1500);
}
function switchTab(name) {
  state.tab=name;
  document.querySelectorAll('[data-tab]').forEach(b=>{b.setAttribute('aria-selected',String(b.dataset.tab===name));b.tabIndex=b.dataset.tab===name?0:-1;});
  ['upload','url','text'].forEach(n=>$(`#panel-${n}`).hidden=n!==name);
  updateImportButton();
}
function updateImportButton(){
  $('#import-submit').textContent=state.tab==='text'?'导入文本':state.tab==='url'?(state.config?.asr_provider==='qwen'?'获取媒体':'导入并自动转写'):'导入文件';
}
document.querySelectorAll('[data-tab]').forEach(b=>{b.addEventListener('click',()=>switchTab(b.dataset.tab));b.addEventListener('keydown',e=>{if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();const tabs=['upload','url','text'];let i=tabs.indexOf(state.tab);i=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;switchTab(tabs[i]);$(`#tab-${tabs[i]}`).focus();}});});
$('#new-document').addEventListener('click',()=>{if(!allowLeave())return;state.current=null;state.dirty=false;rememberDocument(null);syncWakeLock();clearTimeout(state.timer);$('#document-view').hidden=true;$('#import-view').hidden=false;$('#notice').hidden=true;renderLibrary();$('#import-name').focus();});
$('#search').addEventListener('input',renderLibrary);
$('#library').addEventListener('click',e=>{const b=e.target.closest('[data-id]');if(b)action(()=>selectDocument(b.dataset.id));});
$('#settings-toggle').addEventListener('click',()=>{const el=$('#settings');el.hidden=!el.hidden;$('#settings-toggle').setAttribute('aria-expanded',String(!el.hidden));});
$('#refresh-status').addEventListener('click',()=>action(async()=>{await refreshConfig();if(state.current){if(state.dirty){renderJob();updateButtons();}else renderDocument();}}));
$('#segments').addEventListener('input',markDirty);
$('#segments').addEventListener('click',e=>{if(e.target.matches('.remove-segment')){e.target.closest('.segment').remove();markDirty();}});
$('#add-segment').addEventListener('click',()=>{const ids=[...document.querySelectorAll('[data-segment]')].map(e=>Number(e.dataset.segment.slice(1)));const id=`s${Math.max(0,...ids)+1}`;$('#segments').insertAdjacentHTML('beforeend',segmentMarkup({id,text:'',start:null,end:null}));markDirty();$(`#text-${id}`).focus();});
$('#save-transcript').addEventListener('click',()=>action(saveTranscript));
$('#transcribe').addEventListener('click',()=>action(async()=>{const ident=state.current.id;state.working=true;updateButtons();try{await api(`/api/documents/${ident}/transcribe`,{method:'POST'});await selectDocument(ident,false);}finally{state.working=false;updateButtons();}}));
$('#extract').addEventListener('click',()=>action(async()=>{await saveTranscript();state.working=true;updateButtons();try {await api(`/api/documents/${state.current.id}/extract`,{method:'POST'});await selectDocument(state.current.id,false);} finally{state.working=false;updateButtons();}}));
$('#job-status').addEventListener('click',e=>{const b=e.target.closest('[data-retry]');if(b)action(async()=>{b.disabled=true;try{await api(`/api/jobs/${b.dataset.retry}/retry`,{method:'POST'});await selectDocument(state.current.id,false);}finally{b.disabled=false;}});});
$('#strategy-content').addEventListener('click',e=>{const b=e.target.closest('[data-evidence]');if(!b || b.disabled)return;const target=document.getElementById(`segment-${b.dataset.evidence}`);if(target){$('#transcript-review').open=true;target.scrollIntoView({behavior:'smooth',block:'center'});target.classList.add('highlight');target.querySelector('textarea').focus({preventScroll:true});setTimeout(()=>target.classList.remove('highlight'),1800);}});
$('#export').addEventListener('click',()=>action(async()=>{const data=await api(`/api/documents/${state.current.id}/export`);const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`strategy-${state.current.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
$('#import-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  const title=$('#import-name').value.trim();let body,path;
  if(state.tab==='upload'){const f=$('#media-file').files[0];if(!f)throw new Error('请先选择一个文件。');if(f.size>(state.config?.max_upload_mb||200)*1024*1024)throw new Error('文件超过上传大小限制，请拆分后重试。');body=new FormData();body.append('file',f);body.append('title',title);path='upload';}
  else if(state.tab==='url'){const url=$('#video-url').value.trim();if(!url)throw new Error('请填写视频链接。');body=JSON.stringify({title:title||'视频资料',url});path='url';}
  else{const text=$('#source-text').value.trim();if(!text)throw new Error('请粘贴字幕或原文。');body=JSON.stringify({title:title||'文本资料',text});path='text';}
  const b=$('#import-submit');b.disabled=true;$('#import-progress').textContent='正在导入，请稍候…';
  try{const d=await api(`/api/documents/${path}`,{method:'POST',body});await refreshLibrary();await selectDocument(d.id,false);$('#import-form').reset();}finally{b.disabled=false;$('#import-progress').textContent='';}
});});
$('#load-demo').addEventListener('click',()=>action(async()=>{const b=$('#load-demo');b.disabled=true;try{const d=await api('/api/documents/text',{method:'POST',body:JSON.stringify({title:'示例 · 均线思路的原文校对',is_demo:true,text:'1\n00:00:04,000 --> 00:00:12,000\n这是一段界面演示文本。今天讲日线的均线思路，不针对某一只股票。\n\n2\n00:00:12,000 --> 00:00:24,000\n价格突破20日均线时考虑买入，但要观察成交量是否放大。\n\n3\n00:00:24,000 --> 00:00:35,000\n跌破20日均线时考虑卖出。仓位不要太重，要注意止损。\n\n4\n00:00:35,000 --> 00:00:42,000\n具体的放量标准、仓位比例和止损幅度，这段内容没有给出。'})});await refreshLibrary();await selectDocument(d.id,false);}finally{b.disabled=false;}}));
window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue='';}});
document.addEventListener('visibilitychange',()=>syncWakeLock());
action(async()=>{await Promise.all([refreshConfig(),refreshLibrary()]);const remembered=rememberedDocument();if(!state.current && !state.working && remembered && state.documents.some(d=>d.id===remembered))await selectDocument(remembered,false);});
