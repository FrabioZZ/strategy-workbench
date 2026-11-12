"""Phase 5 contracts. HTTP model outputs are test doubles, never real paid calls."""
import json
import copy
import os
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


def local_client(path, **kwargs):
    return TestClient(create_app(Settings(data_dir=path), **kwargs), client=('127.0.0.1', 32000))


def config_body(**changes):
    return dict(provider='openai', base_url='https://example.test/v1', model='contract-model',
                api_key='only-a-test-secret', **changes)


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows DPAPI contract')
def test_credentials_local_encrypted_restart_delete_and_destination(tmp_path):
    with local_client(tmp_path) as c:
        r = c.put('/api/ai/config', json=config_body())
        assert r.status_code == 200, r.text
        assert r.json()['configured'] and r.json()['has_api_key']
        assert 'only-a-test-secret' not in r.text
        assert 'api_key' not in c.get('/api/status').text
        assert c.get('/api/status').json()['ai_model'] == 'contract-model'
        for path in tmp_path.rglob('*'):
            if path.is_file(): assert b'only-a-test-secret' not in path.read_bytes()
        body=config_body(); body['api_key']=''; body['model']='second-model'
        assert c.put('/api/ai/config', json=body).json()['configured']
        body['base_url']='https://other.test/v1'
        assert c.put('/api/ai/config', json=body).status_code == 400
    with local_client(tmp_path) as c:
        assert c.get('/api/ai/config').json()['model'] == 'second-model'
        assert c.delete('/api/ai/config').json()['configured'] is False
    with local_client(tmp_path) as c:
        assert not c.get('/api/ai/config').json()['has_api_key']


def test_config_rejects_nonloopback_client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path)), client=('192.168.1.15', 1234)) as c:
        for verb in ('get','put','delete','post'):
            url='/api/ai/test' if verb=='post' else '/api/ai/config'
            r=getattr(c,verb)(url, **({'json':config_body()} if verb=='put' else {}))
            assert r.status_code == 403


def model_transport(monkeypatch, outputs):
    original=httpx.Client
    requests=[]
    def respond(req):
        requests.append(req)
        out=outputs.pop(0)
        if isinstance(out, Exception): raise out
        if isinstance(out, httpx.Response): return out
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(out,ensure_ascii=False)}}]})
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    return requests


def poll(c, ident):
    for _ in range(300):
        j=c.get('/api/jobs/'+ident).json()
        if j['status'] in ('succeeded','failed','interrupted'): return j
        time.sleep(.01)
    raise AssertionError('job timeout')


def draft_fixture():
    texts=['沪市主板股票，日线。','收盘价小于等于10元买入，目标仓位50%。','收盘价大于等于11元全部卖出。']
    def ref(i): return [{'segment_id':f's{i+1}','quote':texts[i]}]
    draft={'title':'日线10/11元阈值策略','asset':{'value':'沪市主板股票','evidence':ref(0)},
           'timeframe':{'value':'日线','evidence':ref(0)},'questions':[],
           'rules':[{'kind':'buy','text':texts[1],'evidence':ref(1)},
                    {'kind':'position','text':'目标仓位50%','evidence':ref(1)},
                    {'kind':'sell','text':texts[2],'evidence':ref(2)}]}
    mapping={'rules':{'type':'threshold','buy_below':10,'sell_above':11,'target_pct':50},
             'mapping_note':'日线收盘生成信号，次日开盘执行；阈值含等号，卖出为清仓。',
             'questions':[], 'evidence':[{'field':f,'segment_id':f's{i+1}','quote':texts[i]}
                    for f,i in [('buy_below',1),('sell_above',2),('target_pct',1),('timeframe',0)]]}
    return texts,draft,mapping


def test_ai_to_original_portfolio_backtest_and_paper_contract(tmp_path,monkeypatch):
    texts,draft,mapping=draft_fixture()
    calls = model_transport(monkeypatch,[{'changes':[],'questions':[]},draft,mapping])
    settings=Settings(data_dir=tmp_path,ai_provider='openai',ai_base_url='https://example.test/v1',
                      ai_model='test-double',ai_api_key='test-only-key')
    with TestClient(create_app(settings), client=('127.0.0.1',1234)) as c:
        doc=c.post('/api/documents/text',json={'title':'视频资料','text':'\n'.join(texts)}).json()
        j=c.post(f'/api/documents/{doc["id"]}/extract').json()
        assert poll(c,j['id'])['status']=='succeeded'
        doc=c.get(f'/api/documents/{doc["id"]}').json()
        assert doc['ai_review']['status']=='reviewed'
        assert doc['segments']==doc['corrected_segments']
        src=c.get('/api/trading/strategies').json()[0]
        assert doc['strategy_id'] == src['id']
        assert src['title']==draft['title'] and src['source_title']=='视频资料'
        r=c.post('/api/ai/strategies/'+src['id']+'/mapping')
        assert r.status_code==200,r.text
        suggestion=r.json()
        assert suggestion['ready'] and suggestion['confirmed'] is False, suggestion
        assert c.post('/api/ai/strategies/'+src['id']+'/mapping').json() == suggestion
        assert len(calls) == 3
        assert c.get(f'/api/documents/{doc["id"]}/export').json()['ai_mapping'] == suggestion
        item={'id':'a','name':src['title'],'source_id':src['id'],'enabled':True,'weight':100,
              'confirmed':False,'mapping_note':suggestion['mapping_note'],'rules':suggestion['rules']}
        p=c.post('/api/trading/portfolios',json={'name':'AI契约组合','items':[item]}).json()
        assert not p['readiness']['ready']
        item['confirmed']=True  # Deliberate human confirmation through the existing API.
        p=c.put('/api/trading/portfolios/'+p['id'],json={'name':p['name'],'revision':p['revision'],'items':[item]}).json()
        assert p['readiness']['ready'],p
        csv='date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'
        csv+='2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n'
        csv+='2026-01-06,600000.SH,10,10.4,10,10.4,100000,9.5,10.45,8.55\n'
        csv+='2026-01-07,600000.SH,10.5,11.2,10.5,11.1,100000,10.4,11.44,9.36\n'
        csv+='2026-01-08,600000.SH,11,11.3,10.9,11.2,100000,11.1,12.21,9.99\n'
        d=c.post('/api/trading/datasets/import',json={'name':'fixture','source':'test-only','csv_text':csv,
            'ordinary_stock_confirmed':True,'corporate_actions_confirmed_absent':True}).json()
        payload={'portfolio_id':p['id'],'portfolio_revision':p['revision'],'dataset_id':d['id'],
                 'symbol':'600000.SH','initial_cash':10000}
        r=c.post('/api/trading/backtests',json=payload)
        assert r.status_code==201,r.text
        backtest=r.json()
        r=c.post('/api/trading/paper/sessions',json={**payload,'name':'AI回放','mode':'replay'})
        assert r.status_code==201,r.text
        url='/api/trading/paper/sessions/'+r.json()['id']
        assert c.post(url+'/start').status_code==200
        for _ in range(5): c.app.state.paper_worker.tick()
        paper=c.get(url).json()
        assert paper['fills']==backtest['fills'] and paper['fills']
        assert 'test-only-key' not in c.get(f'/api/documents/{doc["id"]}/export').text
        assert c.put(f'/api/documents/{doc["id"]}/transcript', json={
            'revision': doc['revision'], 'segments': doc['segments'],
        }).status_code == 200
        assert c.post('/api/ai/strategies/'+src['id']+'/mapping').status_code == 409
        assert len(calls) == 3


def settings(path, provider='openai'):
    return Settings(data_dir=path,ai_provider=provider,ai_base_url='https://example.test/v1',
                    ai_model='test-double',ai_api_key='only-a-test-secret')


def test_correction_snapshot_quotes_and_audit_persist(tmp_path,monkeypatch):
    original='5日均现高于20日均线时买入'
    corrected='5日均线高于20日均线时买入。'
    draft={'title':'五二十日均线策略','asset':None,'timeframe':None,'questions':[],
           'rules':[{'kind':'buy','text':corrected,'evidence':[{'segment_id':'s1','quote':corrected}]}]}
    calls=model_transport(monkeypatch,[{'changes':[{'segment_id':'s1','original':original,
        'corrected':corrected,'reason':'均现为均线的确定错词，并补句号','certain':True}], 'questions':[]},draft])
    with TestClient(create_app(settings(tmp_path))) as c:
        doc=c.post('/api/documents/text',json={'title':'资料','text':original}).json()
        job=c.post('/api/documents/'+doc['id']+'/extract').json()
        assert poll(c,job['id'])['status']=='succeeded'
        out=c.get('/api/documents/'+doc['id']).json()
        assert out['segments'][0]['text']==original
        assert out['corrected_segments'][0]['text']==corrected
        assert out['ai_review']['changes'][0]['original']==original
        assert out['strategy']['rules'][0]['evidence'][0]['transcript_version']=='corrected'
        assert corrected in json.loads(calls[1].content)['messages'][1]['content']
        export=c.get('/api/documents/'+doc['id']+'/export').json()
        assert export['transcript'][0]['text']==original
        assert export['corrected_transcript'][0]['text']==corrected
    with TestClient(create_app(settings(tmp_path))) as c:
        out=c.get('/api/documents/'+doc['id']).json()
        assert out['ai_review']['changes']
        c.put('/api/documents/'+doc['id']+'/transcript',json={'revision':out['revision'],
             'segments':[{'id':'s1','text':corrected}]})
        assert c.get('/api/documents/'+doc['id']).json()['ai_review']['stale']


@pytest.mark.parametrize('original,corrected,certain',[
    ('10元买入','20元买入',True),('10元买入','10元卖出',True),
    ('不要买入','要买入',True),('价格大于10元买入','价格小于10元买入',True),
    ('1.5元买入','15元买入',True),('均现买入','均线买入',False),
    ('不要买入','不，要买入',True),
])
def test_sensitive_or_uncertain_corrections_preserve_original(tmp_path,monkeypatch,original,corrected,certain):
    from app.ai.review import review_transcript
    from app.models import Segment
    model_transport(monkeypatch,[{'changes':[{'segment_id':'s1','original':original,'corrected':corrected,
        'certain':certain,'reason':'测试拟议修正'}],'questions':[]}])
    revised,review=review_transcript(settings(tmp_path),[Segment(id='s1',text=original)])
    assert revised[0].text==original and review['questions']
    assert review['status']=='needs_confirmation' and not review['changes']


def test_bad_correction_or_extraction_citation_saves_nothing(tmp_path,monkeypatch):
    model_transport(monkeypatch,[{'changes':[{'segment_id':'s1','original':'不存在的原文','corrected':'原文',
        'certain':True,'reason':'测试'}],'questions':[]}])
    with TestClient(create_app(settings(tmp_path))) as c:
        doc=c.post('/api/documents/text',json={'title':'资料','text':'原文'}).json()
        job=c.post('/api/documents/'+doc['id']+'/extract').json()
        assert poll(c,job['id'])['status']=='failed'
        assert c.get('/api/documents/'+doc['id']).json()['strategy'] is None


def source_fixture():
    texts,draft,proposal=draft_fixture()
    source={'strategy':draft,'transcript':[{'id':f's{i+1}','text':t} for i,t in enumerate(texts)],
            'evidence_transcript_version':'original','ai_review':None}
    return source,proposal


@pytest.mark.parametrize('failure',['single_ma','strict_threshold','filter','omitted_filter','weekly','number','quote','direction','missing_position','question'])
def test_unsupported_or_unproven_mapping_is_never_ready(failure):
    from app.ai.mapping import validate_proposal
    src,p=source_fixture()
    if failure=='single_ma':
        src['strategy']['rules'][0]['text']='价格上穿20日均线时买入'
        p['rules']={'type':'ma','fast':1,'slow':20,'target_pct':50}
    elif failure=='strict_threshold': src['strategy']['rules'][0]['text']='收盘价小于10元买入'
    elif failure=='filter': src['strategy']['rules'].append({'kind':'filter','text':'只选成交量增加股票'})
    elif failure=='omitted_filter': src['transcript'].append({'id':'s4','text':'仅买市盈率小于10的股票'})
    elif failure=='weekly': src['strategy']['timeframe']['value']='周线'
    elif failure=='number': p['rules']['buy_below']=9
    elif failure=='quote': p['evidence'][0]['quote']='不存在的引文'
    elif failure=='direction': src['strategy']['rules'][0]['text']='收盘价大于等于10元买入'
    elif failure=='missing_position': src['strategy']['rules']=[r for r in src['strategy']['rules'] if r['kind']!='position']
    elif failure=='question': src['strategy']['questions']=['买卖条件需要确认']
    rules,note,questions,evidence=validate_proposal(p,src)
    assert rules is None and questions


def ma_fixture():
    src,p=source_fixture()
    buy='5日均线高于20日均线时买入'
    sell='5日均线不高于20日均线时全部卖出'
    src['strategy']['rules'][0]['text']=buy
    src['strategy']['rules'][2]['text']=sell
    src['transcript'][1]['text']='目标仓位50%'
    src['transcript'][2]['text']=sell
    src['transcript'] += [{'id':'s4','text':buy}]
    p['rules']={'type':'ma','fast':5,'slow':20,'target_pct':50}
    p['evidence']=[e for e in p['evidence'] if e['field'] not in ('buy_below','sell_above')]
    for e in p['evidence']:
        if e['field']=='target_pct': e['quote']='目标仓位50%'
    p['evidence'] += [{'field':f,'segment_id':'s4','quote':buy} for f in ('fast','slow')]
    return src,p


def test_explicit_dual_ma_maps_but_reversed_buy_sell_does_not():
    from app.ai.mapping import validate_proposal
    src,p=ma_fixture()
    assert validate_proposal(p,src)[0]=={**p['rules'],'stop_loss_pct':None}
    src['strategy']['rules'][0]['text']='5日均线不高于20日均线时全部卖出'
    assert validate_proposal(p,src)[0] is None


def test_mapping_cannot_drop_unextracted_financial_filter():
    from app.ai.mapping import validate_proposal
    src,p=source_fixture()
    src['transcript'].append({'id':'s4','text':'ROE需要高于15%'})
    assert validate_proposal(p,src)[0] is None


def test_optional_stop_loss_requires_exact_engine_basis_and_evidence():
    from app.ai.mapping import validate_proposal
    src,p=source_fixture()
    stop='以入场信号收盘价为基准收盘下跌5%时全部止损'
    src['transcript'].append({'id':'s4','text':stop})
    src['strategy']['rules'].append({'kind':'stop_loss','text':stop})
    assert validate_proposal(p,src)[0] is None
    p['rules']['stop_loss_pct']=5
    p['evidence'].append({'field':'stop_loss_pct','segment_id':'s4','quote':stop})
    assert validate_proposal(p,src)[0]['stop_loss_pct']==5
    src['strategy']['rules'][-1]['text']='以买入成本价为基准下跌5%止损'
    assert validate_proposal(p,src)[0] is None


def test_explicit_model_question_is_not_removed_as_optional_stop_loss(tmp_path,monkeypatch):
    from app.adapters.extractor import Extractor
    from app.models import Segment
    texts,draft,_=draft_fixture()
    explicit='原文未提取到止损，需补充确认；不能据此执行交易。'
    draft['questions']=[explicit]
    model_transport(monkeypatch,[{'changes':[],'questions':[]},draft])
    result=Extractor(settings(tmp_path)).extract_reviewed([Segment(id=f's{i+1}',text=t) for i,t in enumerate(texts)])
    assert explicit in result['strategy']['questions']


@pytest.mark.parametrize('provider',['openai','deepseek','qwen','kimi','glm','custom','ollama'])
def test_each_provider_uses_supported_protocol(tmp_path,monkeypatch,provider):
    from app.ai.client import complete
    response=httpx.Response(200,json={'message':{'content':'OK'}}) if provider=='ollama' else httpx.Response(200,json={'choices':[{'message':{'content':'OK'},'finish_reason':'stop'}]})
    calls=model_transport(monkeypatch,[response])
    assert complete(settings(tmp_path,provider),[{'role':'user','content':'OK'}],probe=True)=='OK'
    assert calls[0].url.path.endswith('/api/chat' if provider=='ollama' else '/chat/completions')
    assert ('authorization' in calls[0].headers)==(provider!='ollama')


@pytest.mark.parametrize('response',[httpx.Response(302,headers={'Location':'https://elsewhere.test/v1'}),
    httpx.Response(401,text='only-a-test-secret'),httpx.Response(200,text='not-json'),
    httpx.ReadTimeout('only-a-test-secret'),httpx.Response(200,json={'choices':[{'message':{'content':'partial'},'finish_reason':'length'}]})])
def test_connection_failures_are_sanitized_and_never_redirect(tmp_path,monkeypatch,response):
    calls=model_transport(monkeypatch,[response])
    with TestClient(create_app(settings(tmp_path)),client=('127.0.0.1',1234)) as c:
        out=c.post('/api/ai/test')
        assert out.status_code==200 and not out.json()['ok']
        assert 'only-a-test-secret' not in out.text and len(calls)==1
