'use strict';
(async()=>{
  const host=document.getElementById('api-endpoints');
  try {
    const response=await fetch('/openapi.json');
    if(!response.ok)throw new Error();
    const schema=await response.json();host.textContent='';
    for(const [path,methods] of Object.entries(schema.paths))for(const [method,info] of Object.entries(methods)){
      const section=document.createElement('section');section.className='rule';
      const title=document.createElement('h2');title.textContent=`${method.toUpperCase()} ${path}`;section.append(title);
      const summary=document.createElement('p');summary.textContent=info.summary||'';section.append(summary);
      const details=document.createElement('details'),label=document.createElement('summary');label.textContent='查看请求与响应结构';details.append(label);
      const pre=document.createElement('pre');pre.className='api-schema';pre.textContent=JSON.stringify(info,null,2);details.append(pre);section.append(details);host.append(section);
    }
    const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='数据模型定义';details.append(summary);
    const pre=document.createElement('pre');pre.className='api-schema';pre.textContent=JSON.stringify(schema.components?.schemas||{},null,2);details.append(pre);host.append(details);
  }catch{host.textContent='无法读取接口定义，请检查本地服务后刷新。';}
})();
