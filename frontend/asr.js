'use strict';
(() => {
  const panel=document.createElement('details');
  panel.id='asr-settings';
  panel.innerHTML=`<summary>语音转写服务与金融词表</summary><form id="asr-form">
  <label>ASR 服务<select id="asr-provider"><option value="local">本地 small / faster-whisper</option><option value="qwen">Qwen 云文件转写</option></select></label>
  <div id="asr-cloud-fields" hidden><label>模型<select id="asr-model"><option value="qwen-audio-3.1-asr-flash-filetrans">qwen-audio-3.1-asr-flash-filetrans</option></select></label>
  <label>地域<select id="asr-region"><option value="beijing">华北2（北京）</option><option value="singapore">新加坡</option></select></label>
  <label>Workspace ID（可选，使用推荐专属域名）<input id="asr-workspace" maxlength="80" pattern="[a-zA-Z0-9-]*"></label>
  <label>独立 ASR API Key<input id="asr-key" type="password" autocomplete="new-password" placeholder="不复用文本 AI Key；留空保留当前地域凭据"></label>
  <p>云转写需联网，将音频、资料标题、主题和词表上传阿里云。3.1 按 Token 计费，以百炼账单为准；保存不发起调用。导入后需点击“开始转写”。换地域或空间须重新填写对应 Key。</p>
  <label class="check"><input id="asr-consent" type="checkbox">我同意上传与云端计费，点击开始或重试时调用 Qwen</label></div>
  <label class="check"><input id="asr-finance" type="checkbox" checked>启用金融词表（权重4，辅助识别，仍需人工核对数字与术语）</label>
  <label>补充术语（空格或逗号分隔）<textarea id="asr-hotwords" maxlength="2000" rows="2"></textarea></label>
  <label>默认主题上下文（与各资料标题合并，最多400字符）<input id="asr-topic" maxlength="200" placeholder="例如：A股量价分析与均线策略"></label>
  <p id="asr-storage-note" class="helper"></p><button class="primary" type="submit">保存语音配置</button><span id="asr-feedback" role="status"></span></form>`;
  document.querySelector('#configuration-status').after(panel);
  function cloud(){document.querySelector('#asr-cloud-fields').hidden=document.querySelector('#asr-provider').value!=='qwen';}
  async function load(){
    const c=await api('/api/asr/config');
    for(const [id,key] of [['provider','provider'],['region','region'],['workspace','workspace_id'],['topic','topic'],['hotwords','hotwords']]) document.querySelector('#asr-'+id).value=c[key]||'';
    document.querySelector('#asr-finance').checked=c.finance_vocabulary;
    document.querySelector('#asr-consent').checked=c.cloud_enabled;
    document.querySelector('#asr-storage-note').textContent=c.storage_note;
    document.querySelector('#asr-key').placeholder=c.has_api_key?'已保存独立 Key；留空保留当前地域凭据':'填写独立 ASR Key';
    cloud();
  }
  document.querySelector('#asr-provider').addEventListener('change',cloud);
  document.querySelector('#asr-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
    const value=id=>document.querySelector('#asr-'+id).value;
    const body={provider:value('provider'),model:value('model'),region:value('region'),workspace_id:value('workspace'),topic:value('topic'),hotwords:value('hotwords'),finance_vocabulary:document.querySelector('#asr-finance').checked,cloud_enabled:document.querySelector('#asr-consent').checked};
    if(value('key'))body.api_key=value('key');
    await api('/api/asr/config',{method:'PUT',body:JSON.stringify(body)});
    document.querySelector('#asr-key').value='';
    document.querySelector('#asr-feedback').textContent='已保存；连接尚未验证。';
    await load();await refreshConfig();
    if(state.current && !state.dirty)renderDocument();
  });});
  document.addEventListener('document-rendered',e=>{
    const d=e.detail;let area=document.querySelector('#asr-document-info');
    if(!area){area=document.createElement('div');area.id='asr-document-info';document.querySelector('#transcription-state').after(area);}
    const m=d.asr_metadata||{};
    const canCopy=d.has_media && !activeJob(d) && (d.segments.length || d.media_status==='transcription_failed');
    area.innerHTML=`${m.provider?`<p class="helper">识别服务：${esc(m.provider)} / ${esc(m.model)} ${esc(m.region||'')} · 原始识别与时间戳已保留</p>`:''}${d.parent_document_id?`<p>重转写副本 · <button class="quiet" type="button" id="asr-parent">查看父来源资料</button></p>`:''}${canCopy?'<button class="secondary" type="button" id="asr-copy">创建副本重新转写</button><p class="helper">复用媒体缓存，保留原资料和策略证据；副本创建后手动开始转写。</p>':''}`;
    document.querySelector('#asr-parent')?.addEventListener('click',()=>action(()=>selectDocument(d.parent_document_id)));
    document.querySelector('#asr-copy')?.addEventListener('click',()=>action(async()=>{if(!allowLeave())return;const copy=await api(`/api/documents/${d.id}/retranscribe-copy`,{method:'POST'});await refreshLibrary();await selectDocument(copy.id,false);}));
  });
  action(load);
})();
