const test=require('node:test');const assert=require('node:assert/strict');
const {acceptDetail,observeDetails}=require('../app/adapters/douyin_browser.cjs');
const url='https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123';
const body=JSON.stringify({status_code:0,aweme_detail:{aweme_id:'123',video:{duration:1000}}});
test('only matching detail from the normal Douyin endpoint is accepted',()=>{
 assert.equal(acceptDetail(url,200,body,'123').aweme_id,'123');
 for(const [u,s,b,id] of [[url,403,body,'123'],[url,200,body,'124'],
  ['https://evil.org/aweme/v1/web/aweme/detail/',200,body,'123'],
  [url,200,'{"status_code":1}','123'],[url,200,'x'.repeat(2*1024*1024+1),'123']])
  assert.equal(acceptDetail(u,s,b,id),null);
});

test('page navigation cannot replace the resolved target identity',async()=>{
 let handler;let current='https://www.douyin.com/video/123';const accepted=[];
 const page={url:()=>current,on:(event,callback)=>{assert.equal(event,'response');handler=callback;}};
 observeDetails(page,'https://www.douyin.com/video/123',result=>accepted.push(result));
 current='https://www.douyin.com/video/999';
 const response=id=>({url:()=>url,status:()=>200,text:async()=>JSON.stringify({
  status_code:0,aweme_detail:{aweme_id:id,video:{duration:1000}}})});
 await handler(response('999'));
 assert.deepEqual(accepted,[]);
 await handler(response('123'));
 assert.equal(accepted.length,1);
 assert.equal(accepted[0].url,'https://www.douyin.com/video/123');
 assert.equal(accepted[0].detail.aweme_id,'123');
});
