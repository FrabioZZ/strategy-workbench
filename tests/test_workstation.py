from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.store import Store
from app.config import Settings
from app.main import create_app
from app.trading import feeds
from app.trading.models import PortfolioInput
from app.trading.portfolios import save_portfolio
from app.trading.store import TradingStore
from app.trading.workstation import BACKTEST, PAPER, Workstation, WorkstationInput


def bar(end, price):
    stamp = datetime.fromisoformat('2026-11-10T' + end + '+08:00')
    return dict(date=stamp.isoformat(), execution_time=(stamp-timedelta(minutes=5)).isoformat(),
                trading_day='2026-11-10', symbol='600000.SH', open=price, high=price,
                low=price, close=price, volume=100000, suspended=False, limit_up=11, limit_down=9)


def setup(folder, provider, clock, quote=None, timeframe='5m'):
    sources = Store(folder)
    sources.init()
    store = TradingStore(folder)
    store.init()
    item = dict(id='rule', name='测试规则', confirmed=True, timeframe=timeframe, mapping_note='测试',
                rules=dict(type='threshold', buy_below=10, sell_above=10.5, target_pct=50))
    with store.transaction() as c:
        p = save_portfolio(store, c, sources, PortfolioInput(name='工作台测试', items=[item]))
    body = WorkstationInput(portfolio_id=p['id'], portfolio_revision=p['revision'], symbol='600000.SH',
                            start_date='2026-11-10', end_date='2026-11-10', initial_cash=10000)
    return Workstation(store, sources, provider=provider, clock=clock, quote=quote), body


class Feed:
    def __init__(self, bars):
        self.bars = bars
        self.live = []

    def history(self, symbol, start_date, end_date):
        return [b for b in self.bars if start_date <= b['trading_day'] <= end_date]

    def latest(self, symbol):
        return self.live


def stamp(time):
    return datetime.fromisoformat('2026-11-10T' + time + '+08:00')


def test_intraday_backtest_uses_next_open_and_returns_chart_series(tmp_path):
    feed = Feed([bar('09:35:00', 10), bar('09:40:00', 10.6), bar('09:45:00', 10.4)])
    app, body = setup(tmp_path, feed, lambda: stamp('18:30:00'))
    result = app.backtest(body)
    assert result['timeframe'] == '5m'
    assert [(f['side'], f['date'], f['price']) for f in result['fills']] == [
        ('buy', stamp('09:35:00').isoformat(), 10.6)]
    assert result['fills'][0]['signal_date'] == stamp('09:35:00').isoformat()
    assert len(result['bars']) == 3
    assert any(x['name'] == 'CLOSE' and x['values'] == [10, 10.6, 10.4] for x in result['indicator_series'])


def test_live_session_never_fills_past_price_and_fills_after_observation(tmp_path):
    feed = Feed([])
    current = [stamp('09:32:00')]
    quote = [None]
    app, body = setup(tmp_path, feed, lambda: current[0], quote=lambda _: quote[0])
    ident = app.create_paper(body)['id']

    current[0] = stamp('09:35:20')
    feed.live = [bar('09:35:00', 10)]
    quote[0] = dict(symbol='600000.SH', price=10, volume_lots=1000, valid_for_valuation=True,
                    freshness='fresh', source_time=stamp('09:35:30').isoformat(),
                    received_at=stamp('09:35:05').isoformat())
    app.tick()
    assert app.paper(ident)['fills'] == []

    current[0] = stamp('09:36:20')
    app.tick()
    assert app.paper(ident)['fills'] == []
    quote[0].update(price=10.1, source_time=stamp('09:36:10').isoformat(),
                    received_at=stamp('09:36:10').isoformat())
    app.tick()
    app.tick()
    result = app.paper(ident)
    assert [(f['side'], f['price']) for f in result['fills']] == [('buy', 10.1)]
    assert result['fills'][0]['date'] == stamp('09:36:10').isoformat()
    app.action(ident, 'pause')
    assert app.paper(ident)['status'] == 'paused'


def test_empty_history_fails_explicitly(tmp_path):
    app, body = setup(tmp_path, Feed([]), lambda: stamp('18:30:00'))
    with pytest.raises(HTTPException, match='没有'):
        app.backtest(body)


@pytest.mark.parametrize(('operation', 'kind'), [('backtest', BACKTEST), ('create_paper', PAPER)])
def test_daily_history_without_a_feed_offers_historical_csv(tmp_path, monkeypatch, operation, kind):
    monkeypatch.delenv('TUSHARE_TOKEN', raising=False)
    app, body = setup(tmp_path, Feed([]), lambda: stamp('18:30:00'), timeframe='daily')

    with pytest.raises(HTTPException) as failure:
        getattr(app, operation)(body)

    assert failure.value.status_code == 400
    assert 'TUSHARE_TOKEN' in failure.value.detail
    assert '历史日线' in failure.value.detail
    assert '覆盖该区间的未复权日线 CSV' in failure.value.detail
    assert app.list(kind) == []


def test_daily_feed_without_dates_retains_incremental_csv_guidance(monkeypatch):
    monkeypatch.delenv('TUSHARE_TOKEN', raising=False)

    with pytest.raises(ValueError, match='等待导入增量CSV'):
        feeds.fetch('600000.SH')


def test_workstation_endpoint_runs_historical_interval_without_dataset_input(tmp_path, monkeypatch):
    from app.trading import minutes

    feed = Feed([bar('09:35:00', 10), bar('09:40:00', 10.6)])
    service, body = setup(tmp_path, feed, lambda: stamp('18:30:00'))
    monkeypatch.setattr(minutes, 'history', feed.history)
    prefix = '/api/trading/workstation'
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        response = client.post(prefix + '/backtests', json=body.model_dump(mode='json'))
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved['fills'][0]['side'] == 'buy'
        assert client.get(f"{prefix}/backtests/{saved['id']}").json() == saved
        assert client.get(prefix + '/backtests').json()[0]['id'] == saved['id']
        assert 'dataset_id' not in saved
        paper = client.post(prefix + '/paper/sessions', json=body.model_dump(mode='json'))
        assert paper.status_code == 201, paper.text
        replay = paper.json()
        assert replay['mode'] == 'replay'
        assert replay['fills'] == saved['fills']
        assert client.get(f"{prefix}/paper/sessions/{replay['id']}").json() == replay
    assert service.store.path.exists()


def test_day_research_automatically_loads_matching_local_history(tmp_path):
    app, body = setup(tmp_path, Feed([]), lambda: stamp('18:30:00'), timeframe='daily')
    body = body.model_copy(update=dict(start_date='2026-11-09', end_date='2026-11-10'))
    rows = [dict(date=day, symbol='600000.SH', open=price, high=price, low=price, close=price,
                 volume=10000, suspended=False) for day, price in [('2026-11-09', 10), ('2026-11-10', 10.6)]]
    dataset = dict(id='adjusted', dataset_type='research_adjusted', symbols=['600000.SH'],
                   is_demo=False, rows=rows, name='本地研究数据')
    with app.store.transaction() as c:
        app.store.put(c, 'dataset', dataset)
        portfolio = app.store.get(c, 'portfolio', body.portfolio_id)
        portfolio['items'][0]['rules'] = dict(type='ma', fast=1, slow=2, target_pct=50)
        app.store.put(c, 'portfolio', portfolio)
    result = app.backtest(body)
    assert result['bars'] == rows
    assert result['price_basis'] == 'forward_adjusted'
    assert result['signals'][-1]['target_pct'] == 50
    assert all(x['name'] != 'FIRST_LIMIT_UP' for x in result['indicator_series'])
