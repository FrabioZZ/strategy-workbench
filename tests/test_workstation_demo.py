from datetime import datetime
import hashlib
import json

import pytest
from fastapi import HTTPException

from app.store import Store
from app.trading import demo_market, feeds, minutes, research
from app.trading.models import PortfolioInput
from app.trading.portfolios import save_portfolio
from app.trading.store import TradingStore
from app.trading.workstation import Workstation, WorkstationInput


SYMBOL = '600000.SH'


def make_bundle(folder):
    folder.mkdir()
    files = {}
    records = [
        ['2024-01-02', 10, 10, 10.2, 9.8, 10000],
        ['2024-01-03', 11, 12, 12.1, 10.9, 10000],
        ['2024-01-04', 13, 13, 13.1, 12.9, 10000],
        ['2026-01-05', 99, 99, 99.1, 98.9, 10000],
    ]

    for filename, code in [('raw.json', 'sh600000'), ('calendar.json', 'sh000300')]:
        data = json.dumps(dict(code=0, data={code: {'day': records}})).encode()
        (folder / filename).write_bytes(data)
        files[filename] = {'sha256': hashlib.sha256(data).hexdigest()}
    manifest = dict(schema_version=1, requested_start_date='2024-01-01',
                    requested_end_date_exclusive='2026-11-01', files=files,
                    calendar_files=['calendar.json'],
                    securities=[dict(symbol=SYMBOL, raw_files=['raw.json'])])
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')


@pytest.fixture
def demo(tmp_path, monkeypatch):
    def unexpected_fetch(*args, **kwargs):
        pytest.fail('The demo must not request external market data')

    monkeypatch.setattr(feeds, 'fetch', unexpected_fetch)
    monkeypatch.setattr(minutes, 'history', unexpected_fetch)
    folder = tmp_path / 'history'
    make_bundle(folder)
    sources = Store(tmp_path)
    sources.init()
    store = TradingStore(tmp_path)
    store.init()
    with store.transaction() as c:
        portfolio = save_portfolio(store, c, sources, PortfolioInput(name='演示', items=[
            dict(id='sample', name='收盘信号', confirmed=True, mapping_note='测试样例',
                 rules=dict(type='threshold', buy_below=10, sell_above=11.5, target_pct=50)),
        ]))
    body = WorkstationInput(portfolio_id=portfolio['id'], portfolio_revision=portfolio['revision'],
                            symbol=SYMBOL, start_date='2024-01-01', initial_cash=100000)
    wall_time = ['2026-01-03T14:59:59+08:00']
    workstation = Workstation(store, sources, clock=lambda: datetime.fromisoformat(wall_time[0]),
                              replay_market=demo_market.ReplayMarket(folder))
    return workstation, body, wall_time


def test_replay_publishes_only_closed_bars_and_advances_once_per_day(demo):
    workstation, body, wall_time = demo
    created = workstation.create_paper(body)
    ident = created['id']
    assert created['mode'] == 'market_replay'
    assert created['simulated_at'] == '2024-01-03T14:59:59+08:00'
    assert created['status'] == 'running'
    assert created['price_basis'] == 'raw'
    assert [bar['date'] for bar in created['bars']] == ['2024-01-02']
    assert created['bars'][0]['close'] == 10
    assert 'limit_up' not in created['bars'][0]
    assert created['fills'] == []
    assert [signal['date'] for signal in created['signals']] == ['2024-01-02']
    assert [point['date'] for point in created['equity']] == ['2024-01-02']

    wall_time[0] = '2026-01-03T15:00:00+08:00'
    workstation.tick()
    workstation.tick()
    after_close = workstation.paper(ident)
    assert [bar['date'] for bar in after_close['bars']] == ['2024-01-02', '2024-01-03']
    assert [(fill['date'], fill['price']) for fill in after_close['fills']] == [('2024-01-03', 11)]

    wall_time[0] = '2026-01-03T14:59:59+08:00'
    assert workstation.paper(ident)['bars'] == created['bars']
    assert workstation.paper(ident)['fills'] == []
    assert workstation.paper(ident)['positions'] == []


def test_replay_waits_before_start_and_finishes_at_source_end(demo):
    workstation, body, wall_time = demo
    created = workstation.create_paper(body.model_copy(update={'start_date': '2024-01-04'}))
    ident = created['id']
    assert created['bars'] == []
    assert created['feed_status'] == 'waiting'

    wall_time[0] = '2028-01-05T16:00:00+08:00'
    workstation.tick()
    finished = workstation.paper(ident)
    assert [bar['date'] for bar in finished['bars']] == ['2024-01-04']
    assert finished['status'] == 'completed'
    assert finished['actual_end_date'] == '2024-01-04'


def test_replay_pauses_and_resumes_without_skipping_elapsed_bars(demo):
    workstation, body, wall_time = demo
    ident = workstation.create_paper(body)['id']
    workstation.action(ident, 'pause')
    wall_time[0] = '2026-01-04T16:00:00+08:00'
    workstation.tick()
    assert [bar['date'] for bar in workstation.paper(ident)['bars']] == ['2024-01-02']
    assert workstation.action(ident, 'start')['status'] == 'running'
    workstation.tick()
    result = workstation.paper(ident)
    assert [bar['date'] for bar in result['bars']] == ['2024-01-02', '2024-01-03', '2024-01-04']
    assert [fill['side'] for fill in result['fills']] == ['buy', 'sell']


def test_replay_rejects_requests_outside_the_hs300_archive(demo):
    workstation, body, _ = demo
    with pytest.raises(HTTPException, match='600519.SH'):
        workstation.create_paper(body.model_copy(update={'symbol': '600519.SH'}))
    with pytest.raises(HTTPException, match='2026-01-01'):
        workstation.create_paper(body.model_copy(update={'end_date': '2026-01-02'}))


def test_backtest_uses_archive_trading_days_at_request_boundary(demo):
    workstation, body, _ = demo
    rows = [dict(date=day, symbol=SYMBOL, open=10, high=10.1, low=9.9, close=10,
                 volume=10000, suspended=False) for day in ('2024-01-02', '2024-01-03')]
    with workstation.store.transaction() as c:
        portfolio = workstation.store.get(c, 'portfolio', body.portfolio_id)
        portfolio['items'][0]['rules'] = dict(type='ma', fast=1, slow=2, target_pct=50)
        workstation.store.put(c, 'portfolio', portfolio)
        workstation.store.put(c, 'dataset', dict(id='phase3', name='历史源', symbols=[SYMBOL],
                                                  dataset_type='research_adjusted', is_demo=False, rows=rows))
    workstation.history_store = workstation.store
    result = workstation.backtest(body.model_copy(update={'end_date': '2024-01-03'}))
    assert result['bars'] == rows


def test_replay_processing_failure_leaves_last_complete_ledger(demo, monkeypatch):
    workstation, body, wall_time = demo
    ident = workstation.create_paper(body)['id']
    original_advance = research.advance

    def interrupt(ledger, portfolio, bar, *args):
        original_advance(ledger, portfolio, bar, *args)
        if bar['date'] == '2024-01-04':
            raise ValueError('replay batch interrupted')

    wall_time[0] = '2026-01-04T16:00:00+08:00'
    monkeypatch.setattr(research, 'advance', interrupt)
    workstation.tick()
    failed = workstation.paper(ident)
    assert failed['feed_status'] == 'error'
    assert [bar['date'] for bar in failed['bars']] == ['2024-01-02']
    assert failed['fills'] == []

    monkeypatch.setattr(research, 'advance', original_advance)
    workstation.tick()
    recovered = workstation.paper(ident)
    assert [fill['side'] for fill in recovered['fills']] == ['buy', 'sell']
    assert recovered['actual_end_date'] == '2024-01-04'


def test_replay_converts_to_shanghai_time_before_shifting_calendar_years():
    utc_time = datetime.fromisoformat('2026-11-10T16:23:44+00:00')
    leap_time = datetime.fromisoformat('2028-02-29T01:23:44+08:00')
    assert demo_market.simulated_time(utc_time).isoformat() == '2024-11-11T00:23:44+08:00'
    assert demo_market.simulated_time(leap_time).isoformat() == '2026-02-28T23:59:59.999999+08:00'
