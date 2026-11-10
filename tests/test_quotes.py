"""Deterministic quote boundary and independent valuation tests (no internet)."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import sqlite3
import threading

import pytest

from app.trading.quotes import QuoteService, parse_snapshot, quote_status, market_state
from app.trading.quote_accounts import QuoteAccounts, value_account
from app.trading.store import TradingStore


def dt(value='2026-11-10T10:00:00+08:00'):
    return datetime.fromisoformat(value)


def wire(symbol='600000.SH', price='10.20', previous='10.00', stamp='20261110100000', volume='100', code=None):
    fields = [''] * 88
    fields[0:7] = ['1', '浦发银行', code or symbol[:6], price, previous, '10.00', volume]
    fields[30] = stamp
    return f'v_{symbol[-2:].lower()}{symbol[:6]}="' + '~'.join(fields) + '";\n'


def parsed(now=None, **kwargs):
    return parse_snapshot(wire(**kwargs), ['600000.SH'], now or dt())[0]['600000.SH']


class Clock:
    def __init__(self): self.now = dt()
    def __call__(self): return self.now
    def advance(self, seconds): self.now += timedelta(seconds=seconds)


def test_parser_preserves_source_and_receipt_and_computes_change():
    q = parsed(now=dt('2026-11-10T10:00:02+08:00'))
    assert q['source_time'] == '2026-11-10T10:00:00+08:00'
    assert q['received_at'] == '2026-11-10T10:00:02+08:00'
    assert q['price'] == 10.2 and q['change'] == 0.2 and q['change_pct'] == 2
    assert q['volume_lots'] == 100 and q['security_status'] == 'not_verified'


@pytest.mark.parametrize('kwargs', [dict(code='600001'), dict(price='0'), dict(price='NaN'),
    dict(previous='0'), dict(volume='-1'), dict(stamp=''), dict(stamp='20261110110000'),
    dict(stamp='20261108100000'), dict(stamp='20261110080000')])
def test_invalid_rows_never_become_prices(kwargs):
    rows, errors = parse_snapshot(wire(**kwargs), ['600000.SH'], dt())
    assert not rows and errors['600000.SH']


def test_missing_and_duplicate_symbols_are_not_silently_valid():
    rows, errors = parse_snapshot(wire() + wire(), ['600000.SH', '000001.SZ'], dt())
    assert not rows and set(errors) == {'600000.SH', '000001.SZ'}


def test_zero_volume_is_unknown_and_not_confirmed_suspension():
    q = parsed(volume='0')
    s = quote_status(q, dt())
    assert q['security_status'] == 'zero_volume_unknown'
    assert s['freshness'] == 'status_unknown' and not s['valid_for_valuation']


@pytest.mark.parametrize('now,source,expected', [
    ('2026-10-07T12:00:00+08:00', '20260930161500', 'closed_latest'),
    ('2026-02-23T12:00:00+08:00', '20260213150000', 'closed_latest'),
    ('2026-11-08T12:00:00+08:00', '20261106161500', 'closed_latest'),
    ('2026-11-10T12:30:00+08:00', '20261110113000', 'break_latest'),
    ('2026-11-10T09:00:00+08:00', '20261109150000', 'closed_latest'),
    ('2026-11-10T10:00:00+08:00', '20261110095500', 'stale'),
    ('2026-10-08T10:00:00+08:00', '20260930161500', 'stale'),
    ('2026-11-10T18:00:00+08:00', '20261110110000', 'stale'),
    ('2027-01-04T10:00:00+08:00', '20270104100000', 'calendar_unknown'),
])
def test_freshness_uses_trading_calendar_not_natural_day_age(now, source, expected):
    q = parsed(now=dt(now), stamp=source)
    assert quote_status(q, dt(now))['freshness'] == expected


def test_calendar_range_and_transport_expiration_are_explicit():
    assert market_state(dt('2026-01-01T10:00:00+08:00'))['expected_date'] is None
    assert market_state(dt('2027-01-04T10:00:00+08:00'))['phase'] == 'calendar_unknown'
    s = quote_status(parsed(), dt('2026-11-10T10:03:01+08:00'))
    assert s['freshness'] == 'stale_cache' and not s['valid_for_valuation']


def test_cache_is_shared_and_manual_reads_do_not_bypass_interval():
    clock = Clock(); calls = []
    def fetch(symbols): calls.append(symbols); return wire()
    service = QuoteService(transport=fetch, clock=clock)
    a = service.get(['600000.SH', '600000.SH'])
    b = service.get(['600000.SH'])
    assert len(calls) == 1 and len(a['quotes']) == 1
    assert a['quotes'][0] == b['quotes'][0]
    clock.advance(46)
    service.get(['600000.SH'])
    assert len(calls) == 2


def test_concurrent_requests_share_one_provider_call():
    clock = Clock(); calls = []; entered = threading.Event(); release = threading.Event()
    def fetch(symbols): calls.append(symbols); entered.set(); assert release.wait(2); return wire()
    service = QuoteService(transport=fetch, clock=clock)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(service.get, ['600000.SH'])
        assert entered.wait(2)
        second = pool.submit(service.get, ['600000.SH'])
        release.set()
        assert first.result()['quotes'] == second.result()['quotes']
    assert len(calls) == 1


def test_partial_failure_keeps_valid_peer_and_failure_disables_cached_price():
    clock = Clock(); count = 0
    def fetch(symbols):
        nonlocal count
        count += 1
        if count == 1: return wire() + wire('000001.SZ')
        if count == 2: return wire(stamp='20261110100046')
        raise TimeoutError('test timeout')
    service = QuoteService(transport=fetch, clock=clock)
    service.get(['600000.SH', '000001.SZ'])
    clock.advance(46)
    q = service.get(['600000.SH', '000001.SZ'])['quotes']
    assert q[0]['valid_for_valuation'] and not q[1]['valid_for_valuation']
    assert q[1]['price'] == 10.2 and q[1]['feed_status'] == 'error'
    assert q[1]['last_success_at'] == dt().isoformat()
    clock.advance(46)
    failed = service.get(['600000.SH'])['quotes'][0]
    assert failed['feed_status'] == 'error' and not failed['valid_for_valuation']
    clock.advance(2)
    service.get(['600000.SH', '300750.SZ'])
    assert count == 3, 'global source failure backoff must also cover new symbols'


def test_regressive_time_rejected_and_source_time_does_not_advance_on_fetch():
    clock = Clock(); replies = iter([wire(), wire(stamp='20261110095900')])
    service = QuoteService(transport=lambda symbols: next(replies), clock=clock)
    service.get(['600000.SH']); clock.advance(46)
    q = service.get(['600000.SH'])['quotes'][0]
    assert q['source_time'] == dt().isoformat() and q['feed_status'] == 'error'


def test_source_failure_recovers_after_backoff_and_repeated_old_tick_stays_stale():
    clock = Clock(); calls = 0
    def fetch(symbols):
        nonlocal calls
        calls += 1
        if calls == 2: raise TimeoutError('artificial outage')
        return wire()
    service = QuoteService(transport=fetch, clock=clock)
    service.get(['600000.SH']); clock.advance(46)
    assert not service.get(['600000.SH'])['quotes'][0]['valid_for_valuation']
    clock.advance(46)
    recovered = service.get(['600000.SH'])['quotes'][0]
    assert recovered['feed_status'] == 'ok' and recovered['valid_for_valuation']
    clock.advance(120)
    stale = service.get(['600000.SH'])['quotes'][0]
    assert stale['received_at'] != stale['source_time']
    assert stale['freshness'] == 'stale' and not stale['valid_for_valuation']


def test_provider_batches_are_bounded_and_unfetched_symbols_are_not_starved():
    clock = Clock(); batches = []
    def fetch(symbols):
        batches.append(symbols)
        return ''.join(wire(s) for s in symbols)
    symbols = [f'{600000+i}.SH' for i in range(60)]
    service = QuoteService(transport=fetch, clock=clock)
    first = service.get(symbols)['quotes']
    assert len(batches[0]) == 50 and sum(q['feed_status']=='waiting' for q in first) == 10
    clock.advance(46)
    service.get(symbols)
    assert len(batches[1]) == 50 and set(symbols[50:]).issubset(batches[1])


def test_watch_expiration_is_not_extended_by_background_reads():
    clock = Clock(); service = QuoteService(transport=lambda symbols: wire(), clock=clock)
    service.get(['600000.SH'])
    clock.advance(46)
    service.get(service.watch_symbols(), watch=False)
    clock.advance(75)
    assert service.watch_symbols() == []


def account(ident='a', mode='incremental', positions=None):
    return dict(id=ident, name=ident, mode=mode, status='paused', cash=8000,
                positions=positions if positions is not None else [dict(symbol='600000.SH', quantity=200, average_cost=9.5)],
                cursor='2026-11-09', portfolio_revision=4, equity=[{'equity':9900}], orders=[{'id':'old'}], fills=[])


def test_account_valuation_is_separate_complete_only_and_cash_only_is_stable():
    q = parsed() | quote_status(parsed(), dt())
    s = account(); before = json.dumps(s, sort_keys=True)
    v = value_account(s, {'600000.SH':q}, dt())
    assert (v['market_value'], v['total_assets'], v['unrealized_pnl']) == (2040, 10040, 140)
    assert json.dumps(s, sort_keys=True) == before
    assert value_account(account(positions=[]), {}, dt())['total_assets'] == 8000
    incomplete = value_account(s, {}, dt())
    assert incomplete['total_assets'] is None and incomplete['unrealized_pnl'] is None
    assert value_account(account(mode='replay'), {}, dt())['eligible'] is False


def test_account_reads_release_sqlite_before_network_and_preserve_every_resource(tmp_path):
    store = TradingStore(tmp_path); store.init()
    with store.transaction() as c:
        store.put(c, 'paper', account())
        store.put(c, 'paper', account('b', positions=[]))
        store.put(c, 'paper', account('historical', mode='replay'))
        store.put(c, 'paper_external', account('external', mode='replay'))
        before = c.execute('select * from resources order by id').fetchall()
    def fetch(symbols):
        # A real independent connection can acquire the write lock during network I/O.
        with sqlite3.connect(store.path, timeout=0.1) as c:
            c.execute('BEGIN IMMEDIATE'); c.rollback()
        return wire()
    service = QuoteService(transport=fetch, clock=Clock())
    accounts = QuoteAccounts(store, service)
    result = accounts.overview(['600000.SH'])
    assert len(result['accounts']) == 2 and result['excluded_historical_accounts'] == 2
    assert {v['id']:v['total_assets'] for v in result['accounts']} == {'a':10040, 'b':8000}
    with store.transaction() as c:
        assert c.execute('select * from resources order by id').fetchall() == before
