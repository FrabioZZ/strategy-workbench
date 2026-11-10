"""Phase 6 contracts: causal indicators, executable conditions, bounded P&L."""
import copy
from datetime import date, timedelta
import math
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.trading.models import Item
from tests.test_trading import portfolio, dataset, run_payload, PREFIX


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        yield c


def ind(name, **params):
    return {'indicator': name, 'params': params}


def condition(name='CLOSE', op='gt', value=0, **params):
    return {'op': op, 'left': ind(name, **params), 'right': {'value': value}}


def rules(buy=None, sell=None):
    return {'type': 'conditional', 'target_pct': 50,
            'buy': buy or condition(), 'sell': sell or condition(op='lt', value=0)}


def bars(closes):
    return [dict(date=(date(2026, 1, 1)+timedelta(days=i)).isoformat(), symbol='600000.SH',
                 open=c, high=c+1, low=c-1, close=c, prev_close=closes[i-1] if i else c,
                 volume=100*(i+1), limit_up=1000, limit_down=.01, suspended=False)
            for i, c in enumerate(closes)]


def test_capabilities_publish_actual_rule_schema(client):
    caps=client.get(PREFIX+'/capabilities').json()
    assert 'conditional' in caps['rule_types']
    registry=client.get(PREFIX+'/indicators')
    assert registry.status_code == 200
    assert {'MACD_DIF','KDJ_J','BOLL_UPPER','FIRST_LIMIT_UP'} <= {r['name'] for r in registry.json()['indicators']}
    assert 'rule_schema' in registry.json()


def test_conditional_rules_accepted_and_invalid_params_rejected(client):
    item=dict(id='c', name='明确条件', confirmed=True, mapping_note='测试确认', rules=rules())
    assert client.post(PREFIX+'/portfolios', json={'name':'条件组合','items':[item]}).status_code == 201
    for operand in [ind('UNKNOWN'), ind('MA', period=0), ind('MA', period=2.5), ind('MA', lookahead=2),
                    ind('MACD_DIF',fast=30,slow=10), {'indicator':'CLOSE','offset':-1},
                    {'indicator':'CLOSE','value':10}]:
        bad=copy.deepcopy(item); bad['rules']['buy']['left']=operand
        assert client.post(PREFIX+'/portfolios', json={'name':'无效','items':[bad]}).status_code == 422


def test_interval_does_not_trade_warmup_or_include_earlier_equity(client):
    p,d=portfolio(client),dataset(client)
    response=client.post(PREFIX+'/backtests', json={**run_payload(p,d), 'start_date':'2026-01-06','end_date':'2026-01-07'})
    assert response.status_code == 201, response.text
    result=response.json()
    assert result['fills'] == []  # prior day's threshold signal must not enter interval
    assert [r['date'] for r in result['equity']] == ['2026-01-06','2026-01-07']
    assert [r['date'] for r in result['signals']] == ['2026-01-06','2026-01-07']
    assert result['warmup_bars']==1 and result['actual_start_date']=='2026-01-06'
    assert result['initial_equity']==result['final_equity']==10000 and result['pnl']==0


@pytest.mark.parametrize('changes,expected',[
    ({'start_date':'2026-02-30'},422), ({'start_date':'20260105'},422),
    ({'start_date':'2026-01-08','end_date':'2026-01-05'},422),
    ({'start_date':'2027-01-01'},400), ({'end_date':'2025-01-01'},400)])
def test_interval_validation(client, changes, expected):
    p,d=portfolio(client),dataset(client)
    assert client.post(PREFIX+'/backtests', json={**run_payload(p,d),**changes}).status_code==expected


def test_formula_values_and_prefix_invariance():
    from app.trading.indicators import IndicatorEngine, registry
    rows=bars([10,11,12,13,12,15,14,13,16,17]*6)
    computed=IndicatorEngine(rows)
    assert computed.series('MA',{'period':3})[:4] == [None,None,11,12]
    assert computed.series('EMA',{'period':3})[:4] == [None,None,11,12]
    assert computed.series('RSI',{'period':3})[3] == 100
    assert computed.series('ATR',{'period':3})[2] == 2
    assert computed.series('OBV')[:3] == [100,300,600]
    assert computed.series('VOLUME_RATIO',{'period':2})[2] == 2
    assert computed.series('BOLL_UPPER',{'period':3,'stddev':2})[2] == pytest.approx(11+2*math.sqrt(2/3))
    assert computed.series('WR',{'period':3})[2] == -25
    assert computed.series('CCI',{'period':3})[2] == pytest.approx(100)
    assert computed.series('KDJ_K',{'period':3})[2] == pytest.approx(58.3333333333)
    assert computed.series('KDJ_D',{'period':3})[2] == pytest.approx(52.7777777778)
    assert computed.series('KDJ_J',{'period':3})[2] == pytest.approx(69.4444444444)
    short=IndicatorEngine(bars([10,12,14,13,16]))
    assert short.series('EMA',{'period':3}) == [None,None,12,12.5,14.25]
    assert short.series('MACD_DIF',{'fast':2,'slow':3,'signal':2}) == [None,None,1,.5,.75]
    assert short.series('MACD_DEA',{'fast':2,'slow':3,'signal':2}) == [None,None,None,.75,.75]
    assert short.series('MACD_HIST',{'fast':2,'slow':3,'signal':2}) == [None,None,None,-.5,0]
    for definition in registry():
        name=definition['name']
        full=computed.series(name)
        for stop in (1,3,15,34,55):
            prefix=IndicatorEngine(rows[:stop]).series(name)
            assert prefix == full[:stop], name
    dif=computed.series('MACD_DIF'); dea=computed.series('MACD_DEA'); hist=computed.series('MACD_HIST')
    assert all(v is None for v in dea[:33])
    assert hist[40] == pytest.approx(2*(dif[40]-dea[40]))


def test_cross_boolean_unknown_and_offset():
    from app.trading.indicators import IndicatorEngine
    from app.trading.conditions import evaluate
    book=IndicatorEngine(bars([9,10,11]))
    cross={'op':'cross_above','left':ind('CLOSE'),'right':{'value':10}}
    assert evaluate(cross,book,2) is True and evaluate(cross,book,1) is False
    unknown=condition('MA',period=20)
    assert evaluate(unknown,book,2) is None
    assert evaluate({'op':'or','conditions':[unknown,condition()]},book,2) is True
    assert evaluate({'op':'and','conditions':[unknown,condition()]},book,2) is None
    prior=condition(value=10); prior['left']['offset']=1
    assert evaluate(prior,book,2) is False


def test_first_board_requires_known_prior_and_actual_limit():
    from app.trading.indicators import IndicatorEngine
    rows=bars([10,11,12.1,12,13.2])
    for row in rows: row['limit_up']=round(row['prev_close']*1.1,2)
    b=IndicatorEngine(rows)
    assert b.series('FIRST_LIMIT_UP')==[0,1,0,0,1]
    assert b.series('LIMIT_UP_STREAK')==[0,1,2,0,1]
    rows[0]['limit_up']=10
    b=IndicatorEngine(rows)
    assert b.series('FIRST_LIMIT_UP')[:3]==[None,None,None]
    assert b.series('LIMIT_UP_STREAK')[:3]==[None,None,None]


def test_confirmed_daily_first_board_rule_shared_with_paper(client):
    # This is an explicitly defined synthetic daily rule, not a mapping of the imported video.
    rule=rules(condition('FIRST_LIMIT_UP','eq',1), condition('CHANGE_PCT','lt',0))
    p=portfolio(client,items=[dict(id='b',name='首板次日开盘',confirmed=True,mapping_note='仅测试确认日线规则',rules=rule)])
    d=dataset(client, '2026-01-05,600000.SH,10,10.1,9.9,10,100000,10,11,9\n'
                      '2026-01-06,600000.SH,10,11,10,11,100000,10,11,9\n'
                      '2026-01-07,600000.SH,11,11.2,10.8,11,100000,11,12.1,9.9\n'
                      '2026-01-08,600000.SH,11,11,10.8,10.9,100000,11,12.1,9.9\n')
    backtest=client.post(PREFIX+'/backtests',json=run_payload(p,d)).json()
    assert backtest['fills'][0]['date']=='2026-01-07'
    assert backtest['signals'][1]['components'][0]['rule_type']=='conditional'
    paper=client.post(PREFIX+'/paper/sessions',json={**run_payload(p,d),'name':'日线首板回放','mode':'replay'}).json()
    for i in range(4):
        paper=client.post(PREFIX+'/paper/sessions/'+paper['id']+'/step',json={'request_id':str(i)}).json()
    assert paper['fills']==backtest['fills'] and paper['signals']==backtest['signals']


def test_interval_warms_ma_then_trades_only_after_first_in_range_signal(client):
    p=portfolio(client,items=[dict(id='ma',name='均线',confirmed=True,mapping_note='完整确认',
        rules={'type':'ma','fast':1,'slow':2,'target_pct':50})])
    d=dataset(client)
    run=client.post(PREFIX+'/backtests',json={**run_payload(p,d),'start_date':'2026-01-06','end_date':'2026-01-07'}).json()
    assert run['signals'][0]['target_pct']==50
    assert [(f['signal_date'],f['date']) for f in run['fills']]==[('2026-01-06','2026-01-07')]
    assert run['pnl']==355 and run['final_equity']==10355
    assert run['metrics']['pnl']==355 and run['actual_end_date']=='2026-01-07'
    assert len(run['equity'])==2


def test_backtrader_and_local_engine_use_identical_condition_signals():
    from app.trading.engine import new_ledger, advance
    from app.trading.paper_engine import replay
    from tests.test_paper_engine import bars as real_bars, COSTS
    rule=rules(condition(value=10,op='lt'),condition(value=11,op='gt'))
    p={'conflict_policy':'weighted','items':[dict(id='c',name='条件',enabled=True,effective_weight=100,rules=rule)]}
    rows=real_bars(); local=new_ledger(10000)
    for bar in rows: advance(local,p,bar,COSTS,'600000.SH',10000)
    external=replay(p,rows,10000,COSTS)
    assert local['signals']==external['signals']
    assert external['fills'] and external['fills'][0]['signal_date']=='2026-01-05'
    assert external['fills'][0]['date']=='2026-01-06'


def test_all_indicators_incremental_cache_survives_json_roundtrip():
    import json
    from app.trading.indicators import IndicatorEngine, registry
    rows=bars([10,11,12,13,12,15,14,13,16,17]*6)
    cache={}; consumed=[]
    for bar in rows:
        consumed.append(bar)
        book=IndicatorEngine(consumed,cache)
        for definition in registry(): book.series(definition['name'])
        cache=json.loads(json.dumps(cache,allow_nan=False))
    incremental=IndicatorEngine(consumed,cache)
    whole=IndicatorEngine(rows)
    for definition in registry():
        name=definition['name']
        assert incremental.series(name)==whole.series(name)


def test_unknown_indicator_does_not_trigger_ne_and_flat_indicators_are_finite():
    from app.trading.indicators import IndicatorEngine, registry
    from app.trading.conditions import evaluate
    rows=bars([10]*60)
    for row in rows: row.update(high=10,low=10,volume=0)
    b=IndicatorEngine(rows)
    assert evaluate(condition('MA','ne',0,period=200),b) is None
    for definition in registry():
        assert all(v is None or math.isfinite(v) for v in b.series(definition['name']))
    assert b.series('RSI')[-1]==50
    assert b.series('KDJ_J')[-1]==50
    assert b.series('VOLUME_RATIO')[-1] is None


def test_boolean_tree_bounds_and_extra_fields_rejected(client):
    c=condition()
    for _ in range(9): c={'op':'and','conditions':[c,condition()]}
    for invalid in [c,{'op':'and','conditions':[]}, {**condition(),'lookahead':True}]:
        response=client.post(PREFIX+'/portfolios',json={'name':'过深条件','items':[
            dict(id='x',name='x',rules=rules(invalid))]})
        assert response.status_code==422


def test_research_rejects_board_rule_and_honors_date_pnl(tmp_path):
    from tests.test_research import setup_service, dataset as research_dataset, body
    from app.trading import models
    from app.trading.portfolios import save_portfolio
    from fastapi import HTTPException
    service,p=setup_service(tmp_path)
    with service.store.transaction() as c:
        service.store.put(c,'dataset',research_dataset())
        run=service.create(c,models.RunInput(**body(p,start_date='2024-01-03')))
        assert run['fills']==[] and run['pnl']==0 and len(run['equity'])==2
        p=save_portfolio(service.store,c,service.sources,models.PortfolioInput(name='首板',items=[dict(
            id='b',name='首板',confirmed=True,mapping_note='明确确认',rules=rules(condition('FIRST_LIMIT_UP','eq',1)))]))
        with pytest.raises(HTTPException,match='涨跌停'):
            service.create(c,models.RunInput(**body(p)))


def test_conditional_source_filter_can_be_confirmed_without_weakening_legacy_guard(client):
    store=client.app.state.store
    doc=store.create_document('首板筛选','text',segments=[{'id':'s1','text':'收盘首板，次日开盘买入，仓位50%，收盘下跌退出'}])
    store.save_strategy(doc,{'title':'首板筛选','rules':[{'kind':'filter','text':'收盘首板'},
        {'kind':'buy','text':'首板次日开盘买入'},{'kind':'sell','text':'收盘下跌退出'}]},'test','test')
    source=client.get(PREFIX+'/strategies').json()[0]
    p=portfolio(client,items=[dict(id='s',name='首板',source_id=source['id'],confirmed=True,mapping_note='完整确认日线筛选',
        rules=rules(condition('FIRST_LIMIT_UP','eq',1),condition('CHANGE_PCT','lt',0)))])
    assert p['readiness']['ready'],p['readiness']
    legacy=portfolio(client,items=[dict(id='s',name='旧规则不允许漏筛选',source_id=source['id'],confirmed=True,mapping_note='声称确认',
        rules={'type':'ma','fast':5,'slow':20,'target_pct':50})])
    assert not legacy['readiness']['ready']


def test_adjusted_prices_can_derive_prev_close_without_inventing_gap_data():
    from app.trading.indicators import IndicatorEngine
    rows=bars([10,11,12,13])
    for row in rows: row.pop('prev_close')
    rows[2]['gap_before']=True
    b=IndicatorEngine(rows)
    assert b.series('PREV_CLOSE')==[None,10,None,12]
    assert b.series('CHANGE_PCT')[1]==pytest.approx(10)
    assert b.series('CHANGE_PCT')[2] is None
    assert b.series('GAP_PCT')[3]==pytest.approx(100/12)


def test_actual_interval_for_weekend_bounds_and_unrealized_pnl(client):
    p,d=portfolio(client),dataset(client)
    response=client.post(PREFIX+'/backtests',json={**run_payload(p,d),'start_date':'2026-01-04','end_date':'2026-01-07'})
    result=response.json()
    assert result['requested_start_date']=='2026-01-04' and result['actual_start_date']=='2026-01-05'
    assert result['actual_end_date']=='2026-01-07' and result['positions']
    assert len(result['fills'])==1  # final sell signal has no next bar inside interval
    assert result['initial_equity']==10000 and result['final_equity']==11255 and result['pnl']==1255


def test_atr_does_not_invent_previous_close_after_missing_trading_days():
    from app.trading.indicators import IndicatorEngine
    rows=bars([10,11,12,13,14])
    for row in rows: row.pop('prev_close')
    rows[2]['gap_before']=True
    assert IndicatorEngine(rows).series('ATR',{'period':2})==[None,2,None,None,2]
