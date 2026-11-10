'use strict';
const MAX_RESULT=2*1024*1024;
function acceptDetail(url,status,body,id){
 try{
  const u=new URL(url);
  if(u.protocol!=='https:'||!['www.douyin.com','www-hj.douyin.com'].includes(u.hostname)||
   u.pathname!=='/aweme/v1/web/aweme/detail/'||status!==200||Buffer.byteLength(body)>MAX_RESULT)return null;
  const data=JSON.parse(body);
  return data.status_code===0&&data.aweme_detail?.aweme_id===id&&data.aweme_detail.video&&
   typeof data.aweme_detail.video==='object'?data.aweme_detail:null;
 }catch{return null;}
}
function observeDetails(page,requestedURL,onDetail){
 const match=/^https:\/\/www\.douyin\.com\/video\/(\d+)$/.exec(requestedURL);
 if(!match)throw new Error('A resolved video target is required');
 const expectedId=match[1];let received=false;
 page.on('response',async response=>{
  if(received||!response.url().includes('/aweme/v1/web/aweme/detail/'))return;
  try{
   const body=await response.text();
   const detail=acceptDetail(response.url(),response.status(),body,expectedId);
   if(detail&&!received){received=true;onDetail({url:requestedURL,detail});}
  }catch{}
 });
}
module.exports={acceptDetail,observeDetails};

async function main(input){
 let browser;let output={error:'unavailable'};
 async function cleanup(){if(browser)await browser.close().catch(()=>{});}
 process.stdin.on('end',async()=>{await cleanup();process.exit(1);});
 const timer=setTimeout(async()=>{await cleanup();process.exit(1);},input.timeout+10000);
 try{
  let chromium;
  try{({chromium}=require('playwright-core'));}catch{output={error:'dependency'};return;}
  try{
   browser=await chromium.launch({...process.env.QUANT_BROWSER_PATH ? {executablePath:process.env.QUANT_BROWSER_PATH} : {channel:'chrome'},headless:true,
    proxy:{server:`http://127.0.0.1:${input.port}`},
    args:['--proxy-bypass-list=<-loopback>','--disable-quic','--disable-http2',
     '--force-webrtc-ip-handling-policy=disable_non_proxied_udp']});
  }catch{output={error:'dependency'};return;}
  const context=await browser.newContext({locale:'zh-CN',serviceWorkers:'block'});
  const page=await context.newPage();let result;
  observeDetails(page,input.url,accepted=>{result=accepted;});
  const deadline=Date.now()+input.timeout;
  try{await page.goto(input.url,{waitUntil:'domcontentloaded',timeout:40000});}catch{}
  let reloaded=false;
  while(!result&&Date.now()<deadline){
   const text=await page.locator('body').innerText({timeout:1000}).catch(()=>'');
   if(/请完成验证|拖动.{0,12}滑块|安全验证/.test(text)){output={error:'verification'};break;}
   // One ordinary reload can recover incomplete public static resources; never solve a challenge.
   if(!reloaded&&Date.now()>deadline-input.timeout/2){
    reloaded=true;try{await page.reload({waitUntil:'domcontentloaded',timeout:20000});}catch{}
   }
   await page.waitForTimeout(500);
  }
  if(result)output=result;
 }catch{output={error:'unavailable'};}
 finally{
  await cleanup();clearTimeout(timer);
  const raw=JSON.stringify(output);
  process.stdout.write(Buffer.byteLength(raw)<=MAX_RESULT?raw:'{"error":"size"}');
  process.stdin.destroy();
 }
}
if(require.main===module){
 let input='';
 process.stdin.setEncoding('utf8');
 process.stdin.on('data',chunk=>{
  input+=chunk;
  if(input.length>8192)process.exit(1);
  const end=input.indexOf('\n');
  if(end!==-1){process.stdin.removeAllListeners('data');try{main(JSON.parse(input.slice(0,end)));}catch{process.exit(1);}}
 });
}
