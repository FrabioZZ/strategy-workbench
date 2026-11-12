import json

from app.trading.engine import advance, execute, new_ledger


SYMBOL = '600000.SH'
INITIAL_CASH = 10000
COSTS = {'commission_bps': 0, 'min_commission': 0, 'sell_tax_bps': 0, 'slippage_bps': 0}
PORTFOLIO = {
    'conflict_policy': 'weighted',
    'items': [{
        'id': 'trend', 'name': '短线趋势', 'enabled': True, 'effective_weight': 100,
        'rules': {
            'type': 'conditional', 'target_pct': 50,
            'buy': {'op': 'gt', 'left': {'indicator': 'CLOSE'}, 'right': {'indicator': 'PREV_CLOSE'}},
            'sell': {'op': 'lt', 'left': {'indicator': 'CLOSE'}, 'right': {'indicator': 'PREV_CLOSE'}},
        },
    }],
}


def intraday_bar(day, opening, end, *, price=10, close=10, volume=100000):
    return {
        'date': f'{day}T{end}:00+08:00', 'trading_day': day,
        'execution_time': f'{day}T{opening}:00+08:00', 'symbol': SYMBOL,
        'open': price, 'high': max(price, close), 'low': min(price, close),
        'close': close, 'volume': volume, 'limit_up': 15, 'limit_down': 5, 'suspended': False,
    }


def test_five_minute_close_signal_fills_at_next_bar_open():
    ledger = new_ledger(INITIAL_CASH)
    day = '2026-01-05'
    advance(ledger, PORTFOLIO, intraday_bar(day, '09:30', '09:35'), COSTS, SYMBOL, INITIAL_CASH)
    advance(ledger, PORTFOLIO, intraday_bar(day, '09:35', '09:40', close=11), COSTS, SYMBOL, INITIAL_CASH)
    assert [signal['target_pct'] for signal in ledger['signals']] == [0, 50]
    assert ledger['fills'] == []

    advance(ledger, PORTFOLIO, intraday_bar(day, '09:40', '09:45', close=9), COSTS, SYMBOL, INITIAL_CASH)
    assert [(order['date'], order['status']) for order in ledger['orders']] == [('2026-01-05T09:40:00+08:00', 'filled')]
    fill = ledger['fills'][0]
    assert (fill['signal_date'], fill['date'], fill['price'], fill['quantity']) == (
        '2026-01-05T09:40:00+08:00', '2026-01-05T09:40:00+08:00', 10, 500,
    )
    assert ledger['signals'][-1]['date'] == '2026-01-05T09:45:00+08:00'


def test_intraday_t_plus_one_preserves_sellability_during_adds_and_partial_sales():
    ledger = new_ledger(INITIAL_CASH)

    def submit(day, opening, end, target):
        bar = intraday_bar(day, opening, end)
        pending = {'date': bar['execution_time'], 'target_pct': target}
        execute(ledger, bar, pending, COSTS, SYMBOL)

    submit('2026-01-05', '09:35', '09:40', 40)
    assert ledger['positions'][0]['available_quantity'] == 0

    submit('2026-01-06', '09:35', '09:40', 80)
    assert ledger['positions'][0]['quantity'] == 800
    assert ledger['positions'][0]['available_quantity'] == 400

    submit('2026-01-06', '09:40', '09:45', 60)
    assert ledger['fills'][-1]['quantity'] == 200
    assert ledger['positions'][0]['quantity'] == 600
    assert ledger['positions'][0]['available_quantity'] == 200

    ledger = json.loads(json.dumps(ledger))
    submit('2026-01-06', '09:45', '09:50', 0)
    assert ledger['fills'][-1]['quantity'] == 200
    assert ledger['positions'][0]['quantity'] == 400
    assert ledger['positions'][0]['available_quantity'] == 0
    submit('2026-01-06', '13:00', '13:05', 0)
    assert ledger['orders'][-1]['status'] == 'rejected'

    submit('2026-01-07', '09:30', '09:35', 0)
    assert ledger['fills'][-1]['quantity'] == 400
    assert ledger['positions'] == []


def test_advance_can_record_a_completed_bar_without_executing_its_open():
    ledger = new_ledger(INITIAL_CASH)
    day = '2026-01-05'
    for bar in (
        intraday_bar(day, '09:30', '09:35'),
        intraday_bar(day, '09:35', '09:40', close=11),
        intraday_bar(day, '09:40', '09:45', close=11),
    ):
        advance(ledger, PORTFOLIO, bar, COSTS, SYMBOL, INITIAL_CASH, execute_pending=False)

    assert ledger['signals'][-1]['target_pct'] == 50
    assert ledger['equity'][-1]['date'] == '2026-01-05T09:45:00+08:00'
    assert ledger['equity'][-1]['equity'] == INITIAL_CASH
    assert ledger['orders'] == []


def test_five_minute_volume_guard_rejects_insufficient_bar_volume():
    ledger = new_ledger(INITIAL_CASH)
    day = '2026-01-05'
    execute(
        ledger, intraday_bar(day, '09:40', '09:45', volume=499),
        {'date': '2026-01-05T09:40:00+08:00', 'target_pct': 50}, COSTS, SYMBOL,
    )
    assert ledger['orders'][-1]['date'] == '2026-01-05T09:40:00+08:00'
    assert ledger['orders'][-1]['status'] == 'rejected'
    assert ledger['fills'] == []


def test_equity_mark_restores_peak_and_fees_from_persisted_ledger():
    from app.trading.engine import mark_equity

    ledger = new_ledger(INITIAL_CASH)
    day = '2026-01-05'
    execute(
        ledger, intraday_bar(day, '09:40', '09:45'),
        {'date': '2026-01-05T09:40:00+08:00', 'target_pct': 50},
        {**COSTS, 'min_commission': 1}, SYMBOL,
    )
    ledger['equity'] = [
        {'date': '2026-01-05T09:45:00+08:00', 'cash': 4999, 'market_value': 7000, 'equity': 11999},
        {'date': '2026-01-05T09:50:00+08:00', 'cash': 4999, 'market_value': 5000, 'equity': 9999},
    ]

    mark_equity(ledger, {'date': '2026-01-05T13:15:00+08:00', 'close': 12}, INITIAL_CASH)
    assert ledger['metrics']['max_drawdown_pct'] == 16.668056
    assert ledger['metrics']['fees'] == 1
    assert ledger['metrics']['trade_count'] == 1

    mark_equity(ledger, {'date': '2026-01-05T13:10:00+08:00', 'close': 8}, INITIAL_CASH)
    assert ledger['equity'][-1]['date'] == '2026-01-05T13:15:00+08:00'
    assert len(ledger['equity']) == 3

    mark_equity(ledger, {'date': '2026-01-05T14:00:00+08:00', 'close': 8}, INITIAL_CASH)
    assert ledger['equity'][-1]['equity'] == 8999
    assert ledger['metrics']['total_return_pct'] == -10.01
    assert ledger['metrics']['max_drawdown_pct'] == 25.002084
