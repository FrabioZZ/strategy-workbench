from datetime import date, datetime, timedelta
import json

import httpx
import pytest


SYMBOL = '600000.SH'
TODAY = '2026-11-11'
YESTERDAY = '2026-11-10'


def bar(day, at, *, live=False, volume=67200):
    row = dict(open=10.08, high=10.11, low=10.05, close=10.09, vol=volume, amount=677376)
    if live:
        return dict(row, code=SYMBOL, freq='5MIN', time=f'{day} {at}:00')
    return dict(row, ts_code=SYMBOL, trade_time=f'{day} {at}:00')


def full_day(day):
    return [bar(day, f'{minute // 60:02d}:{minute % 60:02d}')
            for minute in (*range(9 * 60 + 35, 11 * 60 + 31, 5), *range(13 * 60 + 5, 15 * 60 + 1, 5))]


def limits(day):
    return [dict(ts_code=SYMBOL, trade_date=day.replace('-', ''), pre_close=10.12, up_limit=10.63, down_limit=9.61)]


def calendar(start, end, open_days):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    rows = []
    while first <= last:
        rows.append(dict(exchange='SSE', cal_date=first.strftime('%Y%m%d'), is_open=int(first.isoformat() in open_days)))
        first += timedelta(days=1)
    return rows


def vendor(monkeypatch, responses, now=f'{TODAY}T09:44:00+08:00'):
    from app.trading import minutes

    def respond(request):
        assert str(request.url) == 'https://api.tushare.pro'
        assert request.method == 'POST'
        body = json.loads(request.content)
        assert body['token'] == 'fake-test-token'
        data = responses[body['api_name']]
        if callable(data):
            data = data(body['params'])
        if isinstance(data, httpx.Response):
            return data
        fields = list(data[0]) if data else []
        return httpx.Response(200, json=dict(code=0, data=dict(fields=fields, items=[list(row.values()) for row in data])))

    monkeypatch.setenv('TUSHARE_TOKEN', 'fake-test-token')
    monkeypatch.setattr(minutes, '_now', lambda: datetime.fromisoformat(now))
    monkeypatch.setattr(minutes, '_client', lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    return minutes


def test_live_uses_only_completed_intervals_and_ignores_the_auction(monkeypatch):
    def realtime(params):
        assert params == dict(ts_code=SYMBOL, freq='5MIN')
        return [bar(TODAY, stamp, live=True, volume=0 if stamp == '09:40' else 67200)
                for stamp in ('09:45', '09:40', '09:30', '09:35')]

    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, {TODAY}), rt_min_daily=realtime, stk_limit=limits(TODAY)))

    first, second = minutes.latest(SYMBOL)

    assert first == dict(date=f'{TODAY}T09:35:00+08:00', execution_time=f'{TODAY}T09:30:00+08:00', trading_day=TODAY,
                         symbol=SYMBOL, open=10.08, high=10.11, low=10.05, close=10.09, volume=67200,
                         limit_up=10.63, limit_down=9.61, suspended=False)
    assert second['date'] == f'{TODAY}T09:40:00+08:00'
    assert second['prev_close'] == 10.09
    assert second['volume'] == 0 and second['suspended']


@pytest.mark.parametrize('stamps', [('09:40',), ('09:35', '09:35'), ('09:35', '09:36'), ('09:35',)])
def test_live_rejects_incomplete_duplicate_or_misaligned_coverage(monkeypatch, stamps):
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, {TODAY}),
                                      rt_min_daily=[bar(TODAY, stamp, live=True) for stamp in stamps],
                                      stk_limit=limits(TODAY)))
    with pytest.raises(ValueError, match='5分钟'):
        minutes.latest(SYMBOL)


def test_latest_rejects_rows_from_another_trade_day(monkeypatch):
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, {TODAY}),
                                      rt_min_daily=[bar(YESTERDAY, '09:35', live=True)], stk_limit=limits(TODAY)))
    with pytest.raises(ValueError, match='日期'):
        minutes.latest(SYMBOL)


def test_latest_rejects_wrong_frequency_even_when_timestamps_align(monkeypatch):
    wrong_freq = dict(bar(TODAY, '09:35', live=True), freq='1MIN')
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, {TODAY}),
                                      rt_min_daily=[wrong_freq, bar(TODAY, '09:40', live=True)]))
    with pytest.raises(ValueError, match='周期'):
        minutes.latest(SYMBOL)


def test_closed_day_does_not_fetch_minute_data(monkeypatch):
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, set())))
    assert minutes.latest(SYMBOL) == []


def test_history_requests_the_inclusive_last_day_and_keeps_lunch_separate(monkeypatch):
    def historical(params):
        assert params == dict(ts_code=SYMBOL, freq='5min', start_date=f'{YESTERDAY} 00:00:00', end_date=f'{YESTERDAY} 23:59:59')
        return list(reversed(full_day(YESTERDAY) + [bar(YESTERDAY, '09:30')]))

    minutes = vendor(monkeypatch, dict(trade_cal=calendar(YESTERDAY, YESTERDAY, {YESTERDAY}),
                                      stk_mins=historical, stk_limit=limits(YESTERDAY)))

    bars = minutes.history(SYMBOL, YESTERDAY, YESTERDAY)

    assert len(bars) == 48
    assert bars[0]['date'] == f'{YESTERDAY}T09:35:00+08:00'
    assert bars[23]['date'] == f'{YESTERDAY}T11:30:00+08:00'
    assert bars[24]['execution_time'] == f'{YESTERDAY}T13:00:00+08:00'
    assert 'prev_close' not in bars[24]
    assert bars[-1]['date'] == f'{YESTERDAY}T15:00:00+08:00'
    assert bars[-1]['volume'] == 67200


def test_history_splits_requests_before_the_provider_row_cap(monkeypatch):
    open_days = {'2026-03-02', YESTERDAY}
    ranges = []

    def historical(params):
        start, end = params['start_date'][:10], params['end_date'][:10]
        assert (date.fromisoformat(end) - date.fromisoformat(start)).days < 160
        ranges.append((start, end))
        return [row for day in sorted(open_days) if start <= day <= end for row in full_day(day)]

    def trading_calendar(params):
        return calendar(date.fromisoformat(params['start_date']).isoformat(), date.fromisoformat(params['end_date']).isoformat(), open_days)

    def limits_range(params):
        return [row for day in sorted(open_days)
                if params['start_date'] <= day.replace('-', '') <= params['end_date'] for row in limits(day)]

    minutes = vendor(monkeypatch, dict(trade_cal=trading_calendar, stk_mins=historical, stk_limit=limits_range))

    bars = minutes.history(SYMBOL, '2026-03-02', YESTERDAY)

    assert {row['trading_day'] for row in bars} == open_days
    assert len(ranges) > 1


def test_history_rejects_missing_open_trading_day(monkeypatch):
    before = '2026-11-09'
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(before, YESTERDAY, {before, YESTERDAY}),
                                      stk_mins=full_day(before), stk_limit=limits(before)))
    with pytest.raises(ValueError, match='5分钟.*缺口'):
        minutes.history(SYMBOL, before, YESTERDAY)


def test_history_waits_for_the_selected_trading_day_to_close(monkeypatch):
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, {TODAY})))
    with pytest.raises(ValueError, match='尚未收盘'):
        minutes.history(SYMBOL, TODAY, TODAY)


def test_missing_official_limits_prevents_use_of_an_entire_batch(monkeypatch):
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(YESTERDAY, YESTERDAY, {YESTERDAY}),
                                      stk_mins=full_day(YESTERDAY), stk_limit=[]))
    with pytest.raises(ValueError, match='限价'):
        minutes.history(SYMBOL, YESTERDAY, YESTERDAY)


def test_bars_above_the_official_limit_are_rejected(monkeypatch):
    bad_high = dict(bar(TODAY, '09:35', live=True), high=10.8)
    minutes = vendor(monkeypatch, dict(trade_cal=calendar(TODAY, TODAY, {TODAY}),
                                      rt_min_daily=[bad_high, bar(TODAY, '09:40', live=True)], stk_limit=limits(TODAY)))
    with pytest.raises(ValueError, match='超出官方每日限价'):
        minutes.latest(SYMBOL)


def test_request_errors_are_reported_without_provider_secrets(monkeypatch):
    denial = httpx.Response(200, json=dict(code=2002, msg='fake-test-token leaked by upstream'))
    minutes = vendor(monkeypatch, dict(trade_cal=denial))
    with pytest.raises(ValueError, match='Tushare.*trade_cal') as caught:
        minutes.latest(SYMBOL)
    assert 'fake-test-token' not in str(caught.value)
    assert caught.value.__suppress_context__


def test_missing_token_is_reported_without_a_request(monkeypatch):
    from app.trading import minutes

    monkeypatch.delenv('TUSHARE_TOKEN', raising=False)
    assert minutes.configured() is False
    with pytest.raises(ValueError, match='TUSHARE_TOKEN'):
        minutes.history(SYMBOL, YESTERDAY, YESTERDAY)
