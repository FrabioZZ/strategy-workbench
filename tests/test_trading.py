import copy
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

PREFIX = '/api/trading'

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        yield c


def portfolio(c, **changes):
    payload = {'name': '测试组合', 'mode': 'equal', 'conflict_policy': 'weighted', 'items': [
        {'id': 'a', 'name': '阈值', 'source_id': None, 'enabled': True, 'weight': 100,
         'confirmed': True, 'mapping_note': '人工确认完整规则',
         'rules': {'type': 'threshold', 'buy_below': 10, 'sell_above': 11, 'target_pct': 100}}]}
    payload.update(changes)
    r = c.post(PREFIX+'/portfolios', json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def dataset(c, rows=None, **changes):
    csv = 'date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'
    csv += rows or ('2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n'
                    '2026-01-06,600000.SH,10,10.4,10,10.4,100000,9.5,10.45,8.55\n'
                    '2026-01-07,600000.SH,10.5,11.4,10.5,11.4,100000,10.4,11.44,9.36\n'
                    '2026-01-08,600000.SH,12,12,11,11.5,100000,11.4,12.54,10.26\n')
    p = dict(name='复算', source='测试夹具', csv_text=csv, market='CN_A_MAIN', price_basis='raw',
             is_demo=False, ordinary_stock_confirmed=True, corporate_actions_confirmed_absent=True)
    p.update(changes)
    r = c.post(PREFIX+'/datasets/import', json=p)
    assert r.status_code == 201, r.text
    return r.json()


def run_payload(p, d):
    return {'portfolio_id': p['id'], 'portfolio_revision': p['revision'], 'dataset_id': d['id'],
            'symbol': '600000.SH', 'initial_cash': 10000,
            'costs': {'commission_bps': 0, 'min_commission': 5, 'sell_tax_bps': 5, 'slippage_bps': 0}}


def test_readiness_confirmation_weights_and_disabled(client):
    p = portfolio(client)
    assert p['readiness']['ready']
    items = p['items']
    for item in items:
        for key in ('source_snapshot', 'effective_weight'):
            item.pop(key)
    items[0]['confirmed'] = False
    p2 = portfolio(client, items=items)
    assert not p2['readiness']['ready']
    items[0]['confirmed'] = True
    items[0]['enabled'] = False
    assert not portfolio(client, items=items)['readiness']['ready']
    items[0]['enabled'] = True
    items[0]['weight'] = 50
    p3 = portfolio(client, items=items, mode='weighted')
    assert not p3['readiness']['ready']
    normalized = client.post(PREFIX+'/portfolios/'+p3['id']+'/normalize', json={'revision': 1}).json()
    assert normalized['readiness']['ready']
    assert normalized['items'][0]['effective_weight'] == 100


def test_next_open_fees_cash_and_determinism(client):
    p, d = portfolio(client), dataset(client)
    payload = run_payload(p, d)
    r = client.post(PREFIX+'/backtests', json=payload)
    assert r.status_code == 201, r.text
    a = r.json()
    assert [(x['date'], x['side'], x['quantity'], x['price']) for x in a['fills']] == [
        ('2026-01-06', 'buy', 900, 10), ('2026-01-08', 'sell', 900, 12)]
    assert a['fills'][0]['signal_date'] == '2026-01-05'
    assert a['cash'] == 11784.6  # 10000 - 9000 - 5 + 10800 - 5 - 5.4
    assert a['metrics']['fees'] == 15.4
    assert a['positions'] == []
    b = client.post(PREFIX+'/backtests', json=payload).json()
    assert a['fills'] == b['fills'] and a['equity'] == b['equity']


def test_weight_changes_results_and_conflict_blocks(client):
    p = portfolio(client)
    items = [{k:v for k,v in p['items'][0].items() if k not in ('source_snapshot','effective_weight')}]
    other = copy.deepcopy(items[0]); other['id']='b'; other['rules']['buy_below']=8
    items.append(other)
    d = dataset(client)
    weighted = portfolio(client, items=items)
    a = client.post(PREFIX+'/backtests',json=run_payload(weighted,d)).json()
    assert a['fills'][0]['quantity'] == 500
    blocked = portfolio(client, items=items, conflict_policy='block')
    b = client.post(PREFIX+'/backtests',json=run_payload(blocked,d)).json()
    assert b['fills'] == [] and b['signals'][0]['conflict']


def test_csv_rejects_bad_data_and_limit_block(client):
    for rows in ['2026-01-05,600000.SH,nan,10,9,9.5,1,10,11,9\n',
                 '2026-01-05,688001.SH,10,10,9,9.5,1,10,11,9\n',
                 '2099-01-05,600000.SH,10,10,9,9.5,1,10,11,9\n']:
        with pytest.raises(AssertionError): dataset(client, rows)
    p = portfolio(client)
    d = dataset(client, '2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n'
                        '2026-01-06,600000.SH,10.45,10.45,10.45,10.45,100000,9.5,10.45,8.55\n')
    run = client.post(PREFIX+'/backtests',json=run_payload(p,d)).json()
    assert not run['fills'] and run['orders'][0]['status']=='rejected'


def test_paper_idempotency_isolation_and_restart(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    with TestClient(create_app(cfg)) as c:
        p,d=portfolio(c),dataset(c)
        body={**run_payload(p,d),'name':'回放','mode':'replay','feed':'csv'}
        a=c.post(PREFIX+'/paper/sessions',json=body)
        assert a.status_code==201,a.text
        a=a.json(); sid=a['id']
        url=PREFIX+'/paper/sessions/'+sid
        first=c.post(url+'/step',json={'request_id':'one'}).json()
        duplicate=c.post(url+'/step',json={'request_id':'one'}).json()
        assert duplicate['cursor']==first['cursor']=='2026-01-05'
        second=c.post(url+'/step',json={'request_id':'two'}).json()
        assert len(second['fills'])==1
        other=c.post(PREFIX+'/paper/sessions',json=body).json()
        assert other['cash']==10000 and other['fills']==[]
        assert c.post(url+'/start').json()['status']=='running'
    with TestClient(create_app(cfg)) as c:
        recovered=c.get(url).json()
        assert recovered['status']=='paused' and recovered['cursor']=='2026-01-06'
        assert len(recovered['fills'])==1


def test_stale_draft_and_version_blocks(client):
    s=client.app.state.store
    doc=s.create_document('有证据','text',segments=[{'id':'s1','text':'跌破10买入'}])
    s.save_strategy(doc,{'title':'规则','rules':[{'kind':'buy','text':'跌破10买入'}]},'test','test')
    candidates=client.get(PREFIX+'/strategies').json()
    assert len(candidates)==1
    p=portfolio(client)
    item={k:v for k,v in p['items'][0].items() if k not in ('source_snapshot','effective_weight')}
    item['source_id']=candidates[0]['id']
    p=portfolio(client,items=[item])
    assert p['readiness']['ready'] and p['items'][0]['source_snapshot']['transcript'][0]['text']=='跌破10买入'
    s.edit(doc['id'],1,[{'id':'s1','text':'规则改变'}])
    assert not client.get(PREFIX+'/portfolios/'+p['id']+'/readiness').json()['ready']
    assert client.post(PREFIX+'/backtests',json=run_payload(p,dataset(client))).status_code==409


def test_incremental_old_data_waits_without_fills(client):
    p,d=portfolio(client),dataset(client)
    body={**run_payload(p,d),'name':'增量','mode':'incremental','feed':'csv'}
    a=client.post(PREFIX+'/paper/sessions',json=body).json()
    url=PREFIX+'/paper/sessions/'+a['id']
    client.post(url+'/start')
    a=client.post(url+'/sync',json={'request_id':'one','dataset_id':d['id']}).json()
    assert a['fills']==[] and a['feed_status']=='stale'

def test_source_stop_loss_cannot_disappear_from_mapping(client):
    s=client.app.state.store
    doc=s.create_document('止损规则','text',segments=[{'id':'s1','text':'跌破10买入，亏损5%止损'}])
    s.save_strategy(doc,{'title':'规则','rules':[{'kind':'buy','text':'跌破10买入'}, {'kind':'stop_loss','text':'亏损5%止损'}]},'test','test')
    source=client.get(PREFIX+'/strategies').json()[0]
    p=portfolio(client)
    item={k:v for k,v in p['items'][0].items() if k not in ('source_snapshot','effective_weight')}
    item['source_id']=source['id']
    p=portfolio(client,items=[item])
    assert not p['readiness']['ready']
    assert any('止损' in error for error in p['readiness']['errors'])


def test_incremental_bootstrap_new_bar_duplicate_and_revision(client,monkeypatch):
    from datetime import date,datetime
    wall_clock=[datetime.fromisoformat('2026-01-06T19:00:00+08:00')]
    client.app.state.trading_service.clock=lambda:wall_clock[0]
    monkeypatch.setattr('app.trading.service.completed_date',lambda:date(2026,1,6))
    p=portfolio(client); full=dataset(client)
    rows=client.get(PREFIX+'/datasets/'+full['id']).json()['rows']
    import csv,io
    out=io.StringIO(); w=csv.DictWriter(out,fieldnames=list(rows[0])); w.writeheader()
    for row in rows[:2]: w.writerow({**row,'suspended':int(row['suspended'])})
    initial=dataset(client,csv_text=out.getvalue())
    w.writerow({**rows[2],'suspended':int(rows[2]['suspended'])})
    next_day=dataset(client,csv_text=out.getvalue())
    created=client.post(PREFIX+'/paper/sessions',json={**run_payload(p,initial),'name':'增量','mode':'incremental'}).json()
    url=PREFIX+'/paper/sessions/'+created['id']
    client.post(url+'/start')
    warm=client.post(url+'/sync',json={'request_id':'warm'}).json()
    assert warm['cursor']=='2026-01-06' and warm['fills']==[]
    # Observe each daily signal before the next open. A batch first observed on
    # Jan 8 cannot create a Jan 7 signal in time to sell at Jan 8's past open.
    wall_clock[0]=datetime.fromisoformat('2026-01-07T19:00:00+08:00')
    monkeypatch.setattr('app.trading.service.completed_date',lambda:date(2026,1,7))
    bought=client.post(url+'/sync',json={'request_id':'next_day','dataset_id':next_day['id']}).json()
    assert bought['fills'][0]['date']=='2026-01-07' and bought['fills'][0]['side']=='buy'
    wall_clock[0]=datetime.fromisoformat('2026-01-08T19:00:00+08:00')
    monkeypatch.setattr('app.trading.service.completed_date',lambda:date(2026,1,8))
    result=client.post(url+'/sync',json={'request_id':'new','dataset_id':full['id']}).json()
    assert result['cursor']=='2026-01-08'
    assert result['fills'][0]['date']=='2026-01-07'
    assert len(result['fills'])==2
    assert result['fills'][1]['date']=='2026-01-08' and result['fills'][1]['side']=='sell'
    assert client.post(url+'/sync',json={'request_id':'new','dataset_id':full['id']}).json()['fills']==result['fills']
    assert client.post(url+'/sync',json={'request_id':'another'}).json()['fills']==result['fills']
    assert client.post(url+'/sync',json={'request_id':'new','dataset_id':initial['id']}).status_code==409
    client.post(url+'/pause')
    assert client.post(url+'/sync',json={'request_id':'paused'}).status_code==409


def test_rule_warmup_no_lookahead_stop_loss_and_t1():
    from app.trading.engine import new_ledger,advance,execute
    p={'items':[{'id':'a','name':'MA','enabled':True,'effective_weight':100,
                 'rules':{'type':'ma','fast':1,'slow':2,'target_pct':100,'stop_loss_pct':5}}], 'conflict_policy':'weighted'}
    costs={'commission_bps':0,'min_commission':0,'sell_tax_bps':0,'slippage_bps':0}
    ledger=new_ledger(10000)
    def bar(d,close,opening=None):
        return {'date':d,'symbol':'600000.SH','open':opening or close,'high':max(opening or close,close)+.1,
                'low':min(opening or close,close)-.1,'close':close,'volume':100000,'suspended':False,
                'limit_up':20,'limit_down':1}
    advance(ledger,p,bar('2026-01-05',10),costs,'600000.SH',10000)
    assert ledger['signals'][0]['target_pct']==0 and ledger['fills']==[]
    advance(ledger,p,bar('2026-01-06',11),costs,'600000.SH',10000)
    assert ledger['signals'][-1]['target_pct']==100 and ledger['fills']==[]
    advance(ledger,p,bar('2026-01-07',10,11),costs,'600000.SH',10000)
    assert ledger['fills'][0]['date']=='2026-01-07' and ledger['positions'][0]['available_quantity']==0
    assert '止损' in ledger['signals'][-1]['components'][0]['reason']
    execute(ledger,bar('2026-01-07',10),{'date':'2026-01-07','target_pct':0},costs,'600000.SH')
    assert ledger['orders'][-1]['status']=='rejected' and len(ledger['fills'])==1
    advance(ledger,p,bar('2026-01-08',10),costs,'600000.SH',10000)
    assert ledger['positions']==[] and ledger['cash']==9100


def test_freeze_edit_and_worker_persistence(client):
    p,d=portfolio(client),dataset(client)
    a=client.post(PREFIX+'/paper/sessions',json={**run_payload(p,d),'name':'回放','mode':'replay'}).json()
    url=PREFIX+'/paper/sessions/'+a['id']
    client.post(url+'/start'); client.app.state.paper_worker.tick()
    assert client.get(url).json()['cursor']=='2026-01-05'
    edit={k:v for k,v in p.items() if k in ('name','mode','conflict_policy','revision','items')}
    edit['items']=[{k:v for k,v in p['items'][0].items() if k not in ('source_snapshot','effective_weight')}]
    edit['items'][0]['enabled']=False
    assert client.put(PREFIX+'/portfolios/'+p['id'],json=edit).status_code==200
    # Running sessions use their immutable snapshot. Explicit resume validates current portfolio.
    client.app.state.paper_worker.tick()
    assert len(client.get(url).json()['fills'])==1
    client.post(url+'/pause')
    assert client.post(url+'/start').status_code==409
    assert client.get(url).json()['portfolio_snapshot']['items'][0]['enabled'] is True

def test_tiny_cash_rejected_and_nonfinite_input(client):
    p,d=portfolio(client),dataset(client)
    body=run_payload(p,d); body['initial_cash']=0.001
    response=client.post(PREFIX+'/backtests',json=body)
    assert response.status_code==422
    body=run_payload(p,d)
    response=client.post(PREFIX+'/backtests',content=__import__('json').dumps(body).replace('10000','NaN'),headers={'Content-Type':'application/json'})
    assert response.status_code==422


def test_csv_missing_limits_duplicates_ohlc_company_action():
    from app.trading.datasets import parse_rows
    header='date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'
    good='2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n'
    bad=['2026-01-05,600000.SH,10,9,10,9.5,100000,10,11,9\n',good+good,
         good+'2026-01-06,600000.SH,10,10,9.8,10,100000,10,11,9\n',
         '2026-01-05,600000.SH,0.0000001,0.0000001,0.0000001,0.0000001,1,0.0000001,0.0000002,0.00000001\n']
    for rows in bad:
        with pytest.raises(ValueError): parse_rows(header+rows)
    with pytest.raises(ValueError): parse_rows('date,symbol,open,high,low,close,volume\n'+good)

def test_incremental_does_not_backfill_before_bootstrap_clock(client,monkeypatch):
    from datetime import date,datetime
    client.app.state.trading_service.clock=lambda:datetime.fromisoformat('2026-01-08T19:00:00+08:00')
    monkeypatch.setattr('app.trading.service.completed_date',lambda:date(2026,1,8))
    p=portfolio(client)
    initial=dataset(client,'2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n')
    full=dataset(client)
    created=client.post(PREFIX+'/paper/sessions',json={**run_payload(p,initial),'name':'不补历史成交','mode':'incremental'}).json()
    url=PREFIX+'/paper/sessions/'+created['id']
    client.post(url+'/start')
    client.post(url+'/sync',json={'request_id':'warm'})
    result=client.post(url+'/sync',json={'request_id':'old_new_bars','dataset_id':full['id']}).json()
    assert result['cursor']=='2026-01-08' and result['fills']==[]


def test_initial_cash_must_have_cent_precision(client):
    p,d=portfolio(client),dataset(client)
    body=run_payload(p,d); body['initial_cash']=10000.001
    assert client.post(PREFIX+'/backtests',json=body).status_code==422

def test_affordable_lot_respects_rounded_fee():
    from app.trading.engine import new_ledger,execute
    ledger=new_ledger(1010.30)
    costs={'commission_bps':3,'min_commission':0,'sell_tax_bps':0,'slippage_bps':0}
    bar={'date':'2026-01-06','open':1.01,'high':1.02,'low':1,'volume':100000,
         'suspended':False,'limit_up':1.1,'limit_down':.9}
    execute(ledger,bar,{'date':'2026-01-05','target_pct':100},costs,'600000.SH')
    assert ledger['fills'][0]['quantity']==1000
    assert ledger['cash']==0 and ledger['fills'][0]['fee']==.3
