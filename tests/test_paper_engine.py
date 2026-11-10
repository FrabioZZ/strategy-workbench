"""Real BackBroker tests: timing, accounting, market guards and signal semantics."""
from copy import deepcopy
import importlib
import importlib.util
import pytest


def replay(*args, **kwargs):
    assert importlib.util.find_spec('app.trading.paper_engine'), 'external BackBroker adapter is not implemented'
    return importlib.import_module('app.trading.paper_engine').replay(*args, **kwargs)


def portfolio():
    return {'conflict_policy': 'weighted', 'items': [dict(id='a', name='阈值', enabled=True,
        effective_weight=100, rules=dict(type='threshold', buy_below=10, sell_above=11,
                                        target_pct=90, stop_loss_pct=None))]}


def bars():
    return [dict(date=d, symbol='600000.SH', open=o, high=h, low=l, close=c,
                 prev_close=p, limit_up=u, limit_down=v, volume=100000, suspended=False)
            for d,o,h,l,c,p,u,v in [
        ('2026-01-05',10,10,9,9.5,10,11,9),
        ('2026-01-06',10,10.4,10,10.4,9.5,10.45,8.55),
        ('2026-01-07',10.5,11.4,10.5,11.4,10.4,11.44,9.36),
        ('2026-01-08',12,12,11,11.5,11.4,12.54,10.26)]]


COSTS = dict(commission_bps=0, min_commission=5, sell_tax_bps=5, slippage_bps=0)


def test_real_broker_roundtrip_cash_commission_and_next_open():
    result = replay(portfolio(), bars(), 10000, COSTS)
    assert [(f['date'], f['side'], f['quantity'], f['price']) for f in result['fills']] == [
        ('2026-01-06', 'buy', 900, 10), ('2026-01-07', 'sell', 100, 10.5),
        ('2026-01-08', 'sell', 800, 12)]
    assert result['cash'] == 11629.67
    assert result['positions'] == []
    assert result['metrics']['fees'] == 20.33
    assert result['metrics']['trade_count'] == 3
    assert result['engine']['version'] == '1.9.78.123'
    assert result['orders'][0]['engine_status'] == 'Completed'


def test_prefix_does_not_see_future_or_fill_last_signal():
    partial = replay(portfolio(), bars()[:1], 10000, COSTS)
    full = replay(portfolio(), bars(), 10000, COSTS)
    assert partial['fills'] == []
    assert partial['orders'][0]['status'] == 'submitted'
    assert partial['signals'] == full['signals'][:1]
    assert partial['orders'][0]['id'] == full['orders'][0]['id']
    changed = bars(); changed[3]['close'] = 12
    assert replay(portfolio(), changed, 10000, COSTS)['equity'][:3] == full['equity'][:3]


@pytest.mark.parametrize('change', [dict(volume=0), dict(suspended=True), dict(open=10.45, high=10.45)])
def test_market_guard_cancels_without_carrying_order(change):
    rows = bars()[:2]; rows[1].update(change)
    result = replay(portfolio(), rows, 10000, COSTS)
    assert result['fills'] == []
    assert result['cash'] == 10000
    assert result['orders'][0]['status'] == 'cancelled'
    assert result['orders'][0]['reason']


def test_broker_margin_rejection_is_not_replaced_by_local_fill():
    p = portfolio(); p['items'][0]['rules']['target_pct'] = 100
    result = replay(p, bars()[:2], 10000, COSTS)
    # Fixed quantity at previous 9.5 close = 1000; next 10 open + fee is unaffordable.
    assert result['fills'] == []
    assert result['orders'][0]['engine_status'] == 'Margin'
    assert result['cash'] == 10000


def test_cancellation_date_remains_attempted_bar_after_later_notification():
    rows = bars(); rows[1]['volume'] = 0
    result = replay(portfolio(), rows, 10000, COSTS)
    assert result['orders'][0]['date'] == '2026-01-06'
    assert result['orders'][0]['status'] == 'cancelled'


def test_slippage_is_charged_by_broker():
    rows = bars()[:2]; rows[1]['low'] = 9.99
    result = replay(portfolio(), rows, 10000, {**COSTS, 'slippage_bps': 10})
    assert result['fills'][0]['price'] == pytest.approx(10.01)
    assert result['cash'] == pytest.approx(986)


def test_blocked_conflict_and_ma_warmup_do_not_trade():
    p = portfolio(); p['conflict_policy'] = 'block'
    b = deepcopy(p['items'][0]); b.update(id='b', effective_weight=50)
    b['rules'].update(type='ma', fast=1, slow=3)
    p['items'][0]['effective_weight'] = 50; p['items'].append(b)
    result = replay(p, bars()[:2], 10000, COSTS)
    assert result['fills'] == []
    assert result['signals'][0]['target_pct'] is None
