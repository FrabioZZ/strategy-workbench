"""Behavioral checks for a synthetic-unit research account, using isolated stores."""
import copy
import pytest
from fastapi import HTTPException
from app.trading import engine, models
from app.trading.service import TradingService
from app.trading.store import TradingStore
from app.store import Store
from app.trading.portfolios import save_portfolio


def setup_service(tmp_path):
    sources=Store(tmp_path); sources.init()
    store=TradingStore(tmp_path); store.init()
    service=TradingService(store,sources)
    with store.transaction() as c:
        p=save_portfolio(store,c,sources,models.PortfolioInput(name='测试',items=[dict(
            id='rule',name='明确阈值',confirmed=True,mapping_note='测试夹具',
            rules=dict(type='threshold',buy_below=10,sell_above=11,target_pct=100))]))
    return service,p


def dataset(symbol='300750.SZ'):
    return dict(id='research',name='隔离测试数据',dataset_type='research_adjusted',price_basis='forward_adjusted',
                market='CN_A',symbols=[symbol],is_demo=False,hash='fixture',warnings=['研究价格不是实际成交价格'],
                allowed_modes=['backtest'],rows=[
                    dict(date=day,symbol=symbol,open=opening,close=closing,high=max(opening,closing),
                         low=min(opening,closing),volume=100000,suspended=False,gap_before=False)
                    for day,opening,closing in [('2024-01-02',10,9),('2024-01-03',10,12),('2024-01-04',12,12)]])


def body(p,**changes):
    value=dict(portfolio_id=p['id'],portfolio_revision=1,dataset_id='research',symbol='300750.SZ',
               initial_cash=1000,costs=dict(commission_bps=0,min_commission=0,sell_tax_bps=0,slippage_bps=0))
    value.update(changes)
    return value


def test_research_uses_requested_strategy_next_open_and_synthetic_units(tmp_path):
    service,p=setup_service(tmp_path)
    with service.store.transaction() as c:
        service.store.put(c,'dataset',dataset())
        run=service.create(c,models.RunInput(**body(p,initial_cash=1001)))
    assert run['execution_model']=='adjusted_research'
    assert run['quantity_unit']=='synthetic_unit'
    assert [f['date'] for f in run['fills']]==['2024-01-03','2024-01-04']
    assert run['fills'][0]['quantity']==pytest.approx(100.1)
    assert run['fills'][0]['signal_date']=='2024-01-02'
    assert run['cash']==1201.2 and run['positions']==[]
    assert run['metrics']['total_return_pct']==20
    assert run['dataset_snapshot']['price_basis']=='forward_adjusted'


@pytest.mark.parametrize('mode',['replay','incremental'])
def test_research_cannot_create_paper_account(tmp_path,mode):
    service,p=setup_service(tmp_path)
    with service.store.transaction() as c:
        service.store.put(c,'dataset',dataset('600000.SH'))
        with pytest.raises(HTTPException,match='研究'):
            service.create(c,models.SessionInput(**body(p,symbol='600000.SH',name='禁止',mode=mode)),paper=True)
        assert service.store.list(c,'paper')==[]


def test_research_gap_and_suspension_block_rebalance(tmp_path):
    service,p=setup_service(tmp_path); ds=dataset('600000.SH')
    ds['rows'][1]['gap_before']=True
    with service.store.transaction() as c:
        service.store.put(c,'dataset',ds)
        run=service.create(c,models.RunInput(**body(p,symbol='600000.SH')))
    assert run['fills']==[] and run['cash']==1000
    assert '缺' in run['orders'][0]['reason']
    ds['rows'][1].update(gap_before=False,suspended=True,volume=0)
    with service.store.transaction() as c:
        service.store.put(c,'dataset',ds)
        run=service.create(c,models.RunInput(**body(p,symbol='600000.SH')))
    assert run['fills']==[]


def test_research_sync_rejected_without_mutating_existing_paper(tmp_path):
    service,p=setup_service(tmp_path)
    with service.store.transaction() as c:
        service.store.put(c,'dataset',dataset('600000.SH'))
        session=service.create(c,models.SessionInput(**body(p,symbol='600000.SH',dataset_id=None,name='原会话',mode='incremental')),paper=True)
        service.action(c,session['id'],'start')
    with pytest.raises(HTTPException,match='研究'):
        with service.store.transaction() as c:
            service.action(c,session['id'],'sync',models.SyncInput(request_id='one',dataset_id='research'))
    with service.store.transaction() as c:
        after=service.store.get(c,'paper',session['id'])
    assert after['dataset_id'] is None and after['fills']==[]
