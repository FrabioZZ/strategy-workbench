"""Isolated browser fixture: artificial snapshots, clock and holdings; never production."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn
from fastapi import Body
from app.config import Settings
from app.main import create_app
from app.trading.engine import new_ledger
from app.trading.models import PortfolioInput, SessionInput
from app.trading.portfolios import save_portfolio
from test_quotes import wire


if __name__ == '__main__':
    folder = Path(sys.argv[1]).resolve()
    assert folder.name.startswith('phase4-ui-') and folder.parent.name == '.runtime'
    port = int(sys.argv[2]); assert port != 8765
    app = create_app(Settings(data_dir=folder))
    state = dict(calls=0, offset=0, fault=False)
    started = time.monotonic()
    clock = lambda: datetime.fromisoformat('2026-11-10T10:00:00+08:00') + timedelta(seconds=time.monotonic()-started+state['offset'])
    def transport(symbols):
        state['calls'] += 1
        if state['fault']: raise TimeoutError('explicit browser fault fixture')
        return ''.join(wire(s, price=str(10+state['calls']/10), stamp=clock().strftime('%Y%m%d%H%M%S')).replace('浦发银行', '测试报价') for s in symbols)
    app.state.quotes.clock = clock
    app.state.quotes.transport = transport

    @app.post('/__test__/clock')
    def change_clock(body: dict = Body()):
        state['offset'] += body.get('seconds',0)
        state['fault'] = body.get('fault',state['fault'])
        return state

    @app.get('/__test__/state')
    def status(): return state

    @app.post('/__test__/catalog')
    def seed_catalog():
        store = app.state.trading_service.store
        symbols = ['000001.SZ', '300750.SZ']+[f'{600000+i}.SH' for i in range(298)]
        with store.transaction() as c:
            # Only metadata is needed by the quote catalog; existing dataset listings need summary fields.
            store.put(c, 'dataset', dict(id='test-pool',name='人工测试股票池', dataset_type='research_adjusted',
                is_demo=True, source='仅隔离测试', price_basis='forward_adjusted',market='CN_A',
                allowed_modes=['backtest'],symbols=symbols,rows=[],row_count=0,hash='TEST',
                start_date='2026-11-09',end_date='2026-11-09',warnings=['人工测试'],
                universe={'name':'沪深300（测试）','as_of_date':'2026-11-09'},
                symbol_metadata=[dict(symbol=s,name='平安银行' if s=='000001.SZ' else '宁德时代' if s=='300750.SZ' else '测试股票'+str(i)) for i,s in enumerate(symbols)]))
        return {'count':300}

    @app.post('/__test__/accounts')
    def seed_accounts():
        store = app.state.trading_service.store
        with store.transaction() as c:
            portfolio = save_portfolio(store,c,app.state.store,PortfolioInput(name='人工测试组合',items=[dict(
                id='a', name='人工测试规则', enabled=True, confirmed=True, mapping_note='仅隔离测试', weight=100,
                rules=dict(type='threshold', buy_below=10, sell_above=12, target_pct=100))]))
            for name in ('持仓账户（测试）', '现金账户（测试）'):
                value = app.state.trading_service.create(c,SessionInput(name=name,portfolio_id=portfolio['id'],
                    portfolio_revision=1,symbol='600000.SH',mode='incremental',initial_cash=10000), paper=True)
                if name.startswith('持仓'):
                    value.update(cash=8000,positions=[dict(symbol='600000.SH',quantity=200,available_quantity=200,average_cost=9.5)])
                    store.put(c,'paper',value)
            history = {**value, **new_ledger(10000), 'id':'test-history', 'name':'历史账户（测试）', 'mode':'replay'}
            store.put(c,'paper',history)
        return {'test_only':True}

    uvicorn.run(app,host='127.0.0.1',port=port)
