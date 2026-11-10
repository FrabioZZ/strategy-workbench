from copy import deepcopy
import importlib
import importlib.util
import pytest
from fastapi import HTTPException
from app.store import Store
from app.trading.store import TradingStore
from app.trading.models import PortfolioInput, DatasetInput
from app.trading.portfolios import save_portfolio
from app.trading.datasets import build_dataset


@pytest.fixture
def fixture(tmp_path):
    sources = Store(tmp_path); sources.init()
    store = TradingStore(tmp_path); store.init()
    with store.transaction() as c:
        p = save_portfolio(store,c,sources,PortfolioInput(name='我的组合', items=[dict(id='a', name='规则',
            enabled=True, confirmed=True, mapping_note='人工确认', rules=dict(type='threshold', buy_below=10,
            sell_above=11, target_pct=90))]))
        ds = build_dataset(DatasetInput(name='测试行情', source='隔离测试夹具', ordinary_stock_confirmed=True,
            corporate_actions_confirmed_absent=True, is_demo=True, csv_text=
            'date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'
            '2026-01-05,600000.SH,10,10,9,9.5,100000,10,11,9\n'
            '2026-01-06,600000.SH,10,10.4,10,10.4,100000,9.5,10.45,8.55\n'
            '2026-01-07,600000.SH,10.5,11.4,10.5,11.4,100000,10.4,11.44,9.36\n'
            '2026-01-08,600000.SH,12,12,11,11.5,100000,11.4,12.54,10.26\n'))
        store.put(c,'dataset',ds)
    assert importlib.util.find_spec('app.trading.paper_service'), 'external paper service is not implemented'
    m = importlib.import_module('app.trading.paper_service')
    svc = m.PaperService(store,sources)
    payload = dict(name='外部引擎',portfolio_id=p['id'],portfolio_revision=1,dataset_id=ds['id'],
                   symbol='600000.SH',initial_cash=10000)
    return svc,m,payload,p,ds


def create(f):
    svc,m,body,_,_ = f
    with svc.store.transaction() as c:
        return svc.create(c,m.PaperInput(**body))


def act(f,ident,action,request_id='r'):
    svc,m,*_ = f
    with svc.store.transaction() as c:
        return svc.action(c,ident,action, m.ActionInput(request_id=request_id))


def test_step_run_idempotence_and_restart_preserve_ledger(fixture):
    svc,m,*_ = fixture
    s = create(fixture)
    assert s['cash'] == 10000 and not s['fills']
    s = act(fixture,s['id'],'step')
    assert s['consumed_bars'] == 1 and not s['fills']
    assert act(fixture,s['id'],'step')['consumed_bars'] == 1
    with pytest.raises(HTTPException) as err:
        act(fixture,s['id'],'run')
    assert err.value.status_code == 409
    s = act(fixture,s['id'],'step','r2')
    before = deepcopy(s)
    m.PaperService(svc.store,svc.sources).recover()
    with svc.store.transaction() as c:
        s = svc.store.get(c,'paper_external',s['id'])
    assert s['cash'] == before['cash'] and s['fills'] == before['fills']
    s = act(fixture,s['id'],'run','r3')
    assert s['status'] == 'completed' and s['consumed_bars'] == 4
    assert act(fixture,s['id'],'run','r3')['fills'] == s['fills']
    assert act(fixture,s['id'],'run','r4')['fills'] == s['fills']
    assert all(not k.startswith('_') for k in m.public(s))
    with svc.store.transaction() as c:
        assert svc.store.list(c,'paper') == []


def test_frozen_strategy_requires_current_version_and_confirmation(fixture):
    svc,m,_,p,_ = fixture
    s = create(fixture)
    with svc.store.transaction() as c:
        p['revision']=2; p['items'][0]['rules']['buy_below']=1
        svc.store.put(c,'portfolio',p)
    with pytest.raises(HTTPException) as err:
        act(fixture,s['id'],'run')
    assert err.value.status_code == 409
    with svc.store.transaction() as c:
        frozen=svc.store.get(c,'paper_external',s['id'])
    assert frozen['portfolio_snapshot']['items'][0]['rules']['buy_below']==10
    assert frozen['consumed_bars']==0


@pytest.mark.parametrize('changes',[{'price_basis':'forward_adjusted'},
    {'dataset_type':'research_adjusted'},{'allowed_modes':['backtest']},{'market':'CN_A'}])
def test_research_data_cannot_enter_trade_simulator(fixture,changes):
    svc,_,_,_,ds=fixture
    with svc.store.transaction() as c:
        ds.update(changes);svc.store.put(c,'dataset',ds)
    with pytest.raises(HTTPException) as err: create(fixture)
    assert err.value.status_code==400


def test_data_tampering_refused_without_partial_write(fixture):
    svc,_,_,_,ds=fixture
    s=create(fixture)
    with svc.store.transaction() as c:
        ds['rows'][1]['open']=10.1;svc.store.put(c,'dataset',ds)
    with pytest.raises(HTTPException) as err: act(fixture,s['id'],'run')
    assert err.value.status_code==409
    with svc.store.transaction() as c: assert svc.store.get(c,'paper_external',s['id'])['consumed_bars']==0


def test_incremental_mode_is_rejected(fixture):
    _,m,body,*_=fixture
    from pydantic import ValidationError
    with pytest.raises(ValidationError):m.PaperInput(**body,mode='incremental')


def test_missing_optional_package_reports_unavailable_without_creating_account(fixture,monkeypatch):
    from app.trading import paper_engine
    from importlib.metadata import PackageNotFoundError
    def missing(name):
        raise PackageNotFoundError(name)
    monkeypatch.setattr(paper_engine,'version',missing)
    svc,*_=fixture
    assert svc.capabilities()['installed'] is False
    with pytest.raises(HTTPException) as err:create(fixture)
    assert err.value.status_code==503
    with svc.store.transaction() as c:assert svc.store.list(c,'paper_external')==[]


def test_concurrent_duplicate_steps_commit_once(fixture):
    from concurrent.futures import ThreadPoolExecutor
    s=create(fixture)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(lambda _:act(fixture,s['id'],'step','same-request'),range(2)))
    assert [x['consumed_bars'] for x in values]==[1,1]
    assert values[0]['orders']==values[1]['orders']
