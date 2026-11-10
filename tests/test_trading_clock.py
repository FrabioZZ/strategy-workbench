"""Real service/SQLite regression cases; clocks are independent of bar dates."""
from datetime import datetime, timedelta

import pytest

from app.store import Store
from app.trading.datasets import build_dataset
from app.trading.models import DatasetInput, PortfolioInput, SessionInput, SyncInput
from app.trading.portfolios import save_portfolio
from app.trading.service import TradingService
from app.trading.store import TradingStore


HEADER = 'date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'
ROWS = [
    '2026-11-06,600000.SH,10,10,9,9.5,100000,10,11,9\n',
    '2026-11-09,600000.SH,10,10.4,10,10.4,100000,9.5,10.45,8.55\n',
    '2026-11-10,600000.SH,10.5,11.4,10.5,11.4,100000,10.4,11.44,9.36\n',
    '2026-11-11,600000.SH,12,12,11,11.5,100000,11.4,12.54,10.26\n',
]


class Clock:
    def __init__(self):
        self.set('2026-11-06T19:00:00+08:00')

    def set(self, value):
        self.current = datetime.fromisoformat(value)

    def __call__(self):
        return self.current

    def completed_date(self):
        return self.current.date() - timedelta(days=self.current.hour < 18)


class SessionHarness:
    def __init__(self, folder, clock):
        self.clock = clock
        self.store = TradingStore(folder)
        self.sources = Store(folder)
        self.sources.init()
        self.store.init()
        self.service = TradingService(self.store, self.sources)
        # On the old implementation this independent clock is ignored: the
        # regression must fail on actual fills, not a missing constructor arg.
        self.service.clock = clock
        with self.store.transaction() as c:
            self.portfolio = save_portfolio(self.store, c, self.sources, PortfolioInput(
                name='时钟回归', conflict_policy='weighted', items=[dict(
                    id='a', name='阈值', enabled=True, confirmed=True,
                    mapping_note='人工确认', weight=100,
                    rules=dict(type='threshold', buy_below=10, sell_above=11, target_pct=100))]))

    def create(self, dataset_id=None):
        with self.store.transaction() as c:
            result = self.service.create(c, SessionInput(
                portfolio_id=self.portfolio['id'], portfolio_revision=1,
                dataset_id=dataset_id, symbol='600000.SH', initial_cash=10000,
                name='时钟测试', mode='incremental'), paper=True)
        self.ident = result['id']
        return result

    def import_rows(self, count):
        dataset = build_dataset(DatasetInput(
            name='时钟夹具', source='人工构造，仅用于测试', csv_text=HEADER+''.join(ROWS[:count]),
            ordinary_stock_confirmed=True, corporate_actions_confirmed_absent=True))
        with self.store.transaction() as c:
            self.store.put(c, 'dataset', dataset)
        return dataset['id']

    def action(self, action, request_id=None, dataset_id=None):
        body = SyncInput(request_id=request_id, dataset_id=dataset_id) if request_id else None
        with self.store.transaction() as c:
            return self.service.action(c, self.ident, action, body)

    def restart(self):
        self.store.init()
        self.service = TradingService(self.store, self.sources)
        self.service.clock = self.clock
        with self.store.transaction() as c:
            return self.store.get(c, 'paper', self.ident)


@pytest.fixture
def session(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr('app.trading.service.completed_date', clock.completed_date)
    monkeypatch.setattr('app.trading.datasets.completed_date', clock.completed_date)
    return SessionHarness(tmp_path, clock)


@pytest.mark.parametrize('observed_at, expected_dates', [
    ('2026-11-09T09:29:59+08:00', ['2026-11-09']),
    ('2026-11-09T09:30:00+08:00', []),
    ('2026-11-09T10:00:00+08:00', []),
    ('2026-11-09T17:00:00+08:00', []),
    ('2026-11-09T19:00:00+08:00', []),
])
def test_first_observation_must_precede_open(session, observed_at, expected_dates):
    """R1: completed_date before 18:00 must not authorize that morning's open."""
    session.clock.set(observed_at)
    session.create(session.import_rows(1))
    session.action('start')
    warm = session.action('sync', 'warm')
    assert warm['fills'] == [] and warm['cursor'] == '2026-11-06'
    session.clock.set('2026-11-09T19:01:00+08:00')
    result = session.action('sync', 'monday', session.import_rows(2))
    assert [f['date'] for f in result['fills']] == expected_dates
    assert result['cursor'] == '2026-11-09'
    # A skipped historical open must not prevent the next genuinely eligible one.
    session.clock.set('2026-11-10T19:00:00+08:00')
    next_day = session.action('sync', 'tuesday', session.import_rows(3))
    if not expected_dates:
        assert [(f['date'], f['quantity']) for f in next_day['fills']] == [('2026-11-10', 900)]


def test_first_valid_data_after_start_does_not_backfill(session):
    session.clock.set('2026-11-09T09:00:00+08:00')
    session.create()
    session.action('start')
    assert session.action('sync', 'empty')['feed_status'] == 'waiting'
    session.clock.set('2026-11-09T10:00:00+08:00')
    session.action('sync', 'first_valid', session.import_rows(1))
    session.clock.set('2026-11-09T19:00:00+08:00')
    result = session.action('sync', 'monday', session.import_rows(2))
    assert result['fills'] == [] and result['cash'] == 10000


@pytest.mark.parametrize('restart', [False, True], ids=['pause', 'restart'])
@pytest.mark.parametrize('first_observed, expected_dates', [
    ('2026-11-09T09:10:00+08:00', ['2026-11-09']),
    ('2026-11-09T10:00:00+08:00', []),
])
def test_resume_observation_boundary(session, restart, first_observed, expected_dates):
    """R2: resuming must not turn a paused interval into historical trading."""
    session.create(session.import_rows(1))
    session.action('start')
    session.action('sync', 'friday')
    if restart:
        recovered = session.restart()
        assert recovered['status'] == 'paused' and recovered['cursor'] == '2026-11-06'
    else:
        session.action('pause')
    session.clock.set('2026-11-09T09:00:00+08:00')
    session.action('start')
    session.clock.set(first_observed)
    # Even with no new rows, first valid observation after resume matters.
    session.action('sync', 'observe_again')
    session.clock.set('2026-11-09T19:00:00+08:00')
    result = session.action('sync', 'monday', session.import_rows(2))
    assert [f['date'] for f in result['fills']] == expected_dates
    assert result['cursor'] == '2026-11-09'


@pytest.mark.parametrize('restart', [False, True], ids=['pause', 'restart'])
def test_resume_after_open_skips_paused_bars_and_keeps_ledger(session, restart):
    session.create(session.import_rows(1))
    session.action('start')
    session.action('sync', 'friday')
    session.clock.set('2026-11-09T19:00:00+08:00')
    bought = session.action('sync', 'monday', session.import_rows(2))
    assert [(f['date'], f['side']) for f in bought['fills']] == [('2026-11-09', 'buy')]
    if restart:
        assert session.restart()['fills'] == bought['fills']
    else:
        session.action('pause')
    session.clock.set('2026-11-11T10:00:00+08:00')
    session.action('start')
    session.clock.set('2026-11-11T19:00:00+08:00')
    result = session.action('sync', 'catch_up', session.import_rows(4))
    assert result['fills'] == bought['fills']
    assert result['cash'] == bought['cash']
    assert result['positions'][0]['quantity'] == 900
    assert result['cursor'] == '2026-11-11'


def test_running_start_is_idempotent_and_does_not_reset_clock(session):
    session.clock.set('2026-11-09T09:00:00+08:00')
    session.create(session.import_rows(1))
    session.action('start')
    warm = session.action('sync', 'warm')
    session.clock.set('2026-11-09T10:00:00+08:00')
    assert session.action('start') == warm
    session.clock.set('2026-11-09T19:00:00+08:00')
    result = session.action('sync', 'monday', session.import_rows(2))
    assert [f['date'] for f in result['fills']] == ['2026-11-09']
    assert session.action('sync', 'monday', result['dataset_id'])['fills'] == result['fills']
    assert session.action('sync', 'same_data')['fills'] == result['fills']


def test_late_batch_signal_cannot_trade_an_already_elapsed_open(session):
    """A Monday signal first computed Tuesday evening cannot sell Tuesday open."""
    with session.store.transaction() as c:
        p = session.store.get(c, 'portfolio', session.portfolio['id'])
        p['items'][0]['rules']['sell_above'] = 10.3
        session.store.put(c, 'portfolio', p)
    session.create(session.import_rows(1))
    session.action('start')
    session.action('sync', 'friday')
    session.clock.set('2026-11-10T19:00:00+08:00')
    result = session.action('sync', 'batch', session.import_rows(3))
    assert [(f['date'], f['side']) for f in result['fills']] == [('2026-11-09', 'buy')]
    assert result['signals'][-1]['target_pct'] == 0
    session.clock.set('2026-11-11T19:00:00+08:00')
    next_day = session.action('sync', 'wednesday', session.import_rows(4))
    assert [(f['date'], f['side']) for f in next_day['fills']] == [
        ('2026-11-09', 'buy'), ('2026-11-11', 'sell')]
