"""Tushare five-minute A-share data for local simulation."""

from datetime import date, datetime, time, timedelta
import os

import httpx

from app.trading.datasets import number
from app.trading.quotes import CN, SYMBOL


_URL = 'https://api.tushare.pro'
_FIRST_DAY = date(2010, 1, 1)
# Below the 8,000 row cap even at 49 rows per day including the auction.
_HISTORY_CHUNK_DAYS = 150
_FIVE_MINUTES = timedelta(minutes=5)
_END_TIMES = tuple(time(n // 60, n % 60)
                   for n in (*range(9 * 60 + 35, 11 * 60 + 31, 5), *range(13 * 60 + 5, 15 * 60 + 1, 5)))
_LIMIT_FIELDS = 'ts_code,trade_date,up_limit,down_limit'


def configured() -> bool:
    return bool(os.getenv('TUSHARE_TOKEN', '').strip())


def _token():
    token = os.getenv('TUSHARE_TOKEN', '').strip()
    if not token:
        raise ValueError('Tushare 5分钟行情未配置 TUSHARE_TOKEN')
    return token


def _now():
    return datetime.now(CN)


def _client():
    return httpx.Client(timeout=8, follow_redirects=False)


def _call(client, token, api, params, fields=''):
    try:
        response = client.post(_URL, json=dict(api_name=api, token=token, params=params, fields=fields))
        response.raise_for_status()
        payload = response.json()
        if payload['code'] != 0:
            raise ValueError
        names, rows = payload['data']['fields'], payload['data']['items']
        if (not isinstance(names, list) or not all(isinstance(field, str) for field in names)
                or len(set(names)) != len(names) or not isinstance(rows, list)
                or any(not isinstance(row, list) or len(row) != len(names) for row in rows)):
            raise ValueError
        return [dict(zip(names, row)) for row in rows]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        # The upstream error and HTTP body may contain the token.
        raise ValueError(f'Tushare {api} 请求失败，请检查连接、令牌和接口权限') from None


def _symbol(value):
    if not isinstance(value, str) or not SYMBOL.fullmatch(value):
        raise ValueError('Tushare 5分钟行情仅支持单个沪深 A 股代码，如 600000.SH')
    return value


def _parse_day(value):
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            raise ValueError
        return day
    except (TypeError, ValueError):
        raise ValueError('Tushare 5分钟历史日期须使用 YYYY-MM-DD 格式') from None


def _calendar(client, token, start, end):
    rows = _call(client, token, 'trade_cal',
                 dict(exchange='SSE', start_date=start.strftime('%Y%m%d'), end_date=end.strftime('%Y%m%d')),
                 'exchange,cal_date,is_open')
    seen, open_days = set(), set()
    try:
        for row in rows:
            day = datetime.strptime(row['cal_date'], '%Y%m%d').date()
            state = str(row['is_open'])
            if not start <= day <= end or day in seen or state not in ('0', '1') or row['exchange'] != 'SSE':
                raise ValueError
            seen.add(day)
            if state == '1':
                open_days.add(day)
        if len(seen) != (end - start).days + 1:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError('Tushare 交易日历缺失或无效，无法验证 5分钟覆盖') from None
    return open_days


def _amount(value, label, *, zero=False):
    if isinstance(value, bool):
        raise ValueError
    return number(value, label, zero)


def _limits(client, token, symbol, start, end):
    rows = _call(client, token, 'stk_limit',
                 dict(ts_code=symbol, start_date=start.strftime('%Y%m%d'), end_date=end.strftime('%Y%m%d')),
                 _LIMIT_FIELDS)
    limits = {}
    try:
        for row in rows:
            day = datetime.strptime(row['trade_date'], '%Y%m%d').date()
            lower = _amount(row['down_limit'], '跌停价')
            upper = _amount(row['up_limit'], '涨停价')
            if row['ts_code'] != symbol or not start <= day <= end or day in limits or lower >= upper:
                raise ValueError
            limits[day] = (lower, upper)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('Tushare 官方每日限价无效，无法模拟撮合') from None
    return limits


def _normalize(rows, symbol, expected, *, live=False, cutoff=None):
    bars = {}
    time_field = 'time' if live else 'trade_time'
    for row in rows:
        try:
            stamp = datetime.strptime(row[time_field], '%Y-%m-%d %H:%M:%S').replace(tzinfo=CN)
            if row.get('ts_code', row.get('code')) != symbol or (live and row['freq'] != '5MIN'):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError('Tushare 5分钟行情的代码、时间或周期无效') from None
        if stamp.date() not in expected:
            raise ValueError('Tushare 5分钟行情日期超出请求区间或交易日历')
        if stamp.time() == time(9, 30):
            continue
        if stamp.time() not in _END_TIMES or stamp in bars:
            raise ValueError('Tushare 5分钟行情时间重复或不在 5分钟交易区间')
        if cutoff is not None and stamp > cutoff:
            continue
        try:
            prices = {field: _amount(row[field], field) for field in ('open', 'high', 'low', 'close')}
            volume = _amount(row['vol'], '成交量', zero=True)
            if not prices['low'] <= min(prices['open'], prices['close']) <= max(prices['open'], prices['close']) <= prices['high']:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError('Tushare 5分钟行情价格或成交量无效') from None
        bars[stamp] = dict(date=stamp.isoformat(), execution_time=(stamp - _FIVE_MINUTES).isoformat(),
                           trading_day=stamp.date().isoformat(), symbol=symbol, **prices,
                           volume=volume, suspended=volume == 0)
    stamps = [datetime.combine(day, end, CN) for day in sorted(expected) for end in expected[day]]
    for stamp in stamps:
        if stamp not in bars:
            raise ValueError(f'Tushare 5分钟行情有缺口，缺少 {stamp.isoformat()}')
        previous = bars.get(stamp - _FIVE_MINUTES)
        if previous:
            bars[stamp]['prev_close'] = previous['close']
    return [bars[stamp] for stamp in stamps]


def _apply_limits(bars, limits):
    for bar in bars:
        official = limits.get(date.fromisoformat(bar['trading_day']))
        if official is None:
            raise ValueError(f"Tushare 缺少 {bar['trading_day']} 官方每日限价，无法模拟撮合")
        lower, upper = official
        if bar['low'] < lower - 1e-8 or bar['high'] > upper + 1e-8:
            raise ValueError('Tushare 5分钟行情超出官方每日限价，无法模拟撮合')
        bar.update(limit_up=upper, limit_down=lower)


def history(symbol: str, start_date: str, end_date: str) -> list[dict]:
    """Return complete sessions within the inclusive Shanghai date range."""
    symbol = _symbol(symbol)
    token = _token()
    start, end = _parse_day(start_date), _parse_day(end_date)
    now = _now()
    if not _FIRST_DAY <= start <= end <= now.date():
        raise ValueError('Tushare 5分钟历史日期超出可请求范围（2010-01-01 至今天）')
    bars = []
    with _client() as client:
        while start <= end:
            last = min(end, start + timedelta(days=_HISTORY_CHUNK_DAYS - 1))
            days = _calendar(client, token, start, last)
            if now.date() in days and now.time() < _END_TIMES[-1]:
                raise ValueError('Tushare 5分钟历史行情需要完整交易日，今天尚未收盘')
            if days:
                raw = _call(client, token, 'stk_mins', dict(ts_code=symbol, freq='5min',
                            start_date=f'{start} 00:00:00', end_date=f'{last} 23:59:59'))
                chunk = _normalize(raw, symbol, {day: _END_TIMES for day in days})
                _apply_limits(chunk, _limits(client, token, symbol, start, last))
                bars.extend(chunk)
            start = last + timedelta(days=1)
    if not bars:
        raise ValueError('Tushare 所选日期内没有可用的 5分钟交易日')
    return bars


def latest(symbol: str) -> list[dict]:
    """Return today's elapsed five-minute intervals or an empty preopen/closed series."""
    symbol = _symbol(symbol)
    token = _token()
    now = _now()
    today = now.date()
    elapsed = tuple(end for end in _END_TIMES if end <= now.time())
    if not elapsed:
        return []
    with _client() as client:
        if today not in _calendar(client, token, today, today):
            return []
        raw = _call(client, token, 'rt_min_daily', dict(ts_code=symbol, freq='5MIN'))
        bars = _normalize(raw, symbol, {today: elapsed}, live=True, cutoff=now)
        _apply_limits(bars, _limits(client, token, symbol, today, today))
    return bars
