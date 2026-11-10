"""Read-only public snapshots. Never feeds the daily execution engine."""
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
import threading
import urllib.request

CN = timezone(timedelta(hours=8))
SOURCE = '腾讯公开快照（免账号）'
CALENDAR_SOURCE = 'https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml'
REFRESH_SECONDS = 45
MAX_BATCH = 50
SYMBOL = re.compile(r'(?:6\d{5}\.SH|[03]\d{5}\.SZ)\Z')
# Exchange calendar, not the government's make-up workday calendar.
HOLIDAYS = [('01-01', '01-03'), ('02-15', '02-23'), ('04-04', '04-06'),
            ('05-01', '05-05'), ('06-19', '06-21'), ('09-25', '09-27'), ('10-01', '10-07')]


def trading_day(day):
    if day.year != 2026:
        return None
    return day.weekday() < 5 and not any(a <= day.strftime('%m-%d') <= b for a, b in HOLIDAYS)


def market_state(now):
    now = now.astimezone(CN)
    day, t = now.date(), now.time()
    known = trading_day(day)
    phase = 'calendar_unknown'
    if known is not None:
        if not known: phase = 'closed'
        elif t < time(9, 15): phase = 'preopen'
        elif t < time(9, 30): phase = 'auction'
        elif t < time(11, 30): phase = 'trading'
        elif t < time(13): phase = 'lunch'
        elif t < time(15): phase = 'trading'
        else: phase = 'closed'
    expected = day
    if phase in ('closed', 'preopen') and (not known or t < time(9, 15)):
        expected -= timedelta(days=1)
        while trading_day(expected) is False:
            expected -= timedelta(days=1)
    if trading_day(expected) is not True:
        expected = None
    return dict(phase=phase, expected_date=expected.isoformat() if expected else None,
                timezone='Asia/Shanghai', calendar_start='2026-01-01', calendar_end='2026-12-31',
                calendar_source=CALENDAR_SOURCE)


def parse_snapshot(text, requested, received_at):
    """Tencent field 30 is source snapshot time; fields 3/4 are price/prev-close."""
    received_at = received_at.astimezone(CN)
    rows, errors, seen = {}, {}, set()
    wanted = {s[-2:].lower()+s[:6]: s for s in requested}
    for match in re.finditer(r'v_(sh\d{6}|sz\d{6})="([^"\r\n]*)"\s*;', text):
        key, payload = match.groups()
        if key not in wanted:
            continue
        symbol = wanted[key]
        if symbol in seen:
            rows.pop(symbol, None); errors[symbol] = '来源重复返回同一代码'; continue
        seen.add(symbol)
        fields = payload.split('~')
        try:
            if len(fields) < 31 or fields[2] != symbol[:6] or not fields[1].strip():
                raise ValueError('代码或返回格式不匹配')
            price, previous, volume = (Decimal(fields[i]) for i in (3, 4, 6))
            if not all(x.is_finite() for x in (price, previous, volume)) or min(price, previous) <= 0 or volume < 0:
                raise ValueError('价格、昨收或成交量无效')
            if max(price, previous) > 1000000 or volume > 1e12:
                raise ValueError('数值超出可接受范围')
            if not re.fullmatch(r'\d{14}', fields[30]):
                raise ValueError('缺少可信源时间')
            stamp = datetime.strptime(fields[30], '%Y%m%d%H%M%S').replace(tzinfo=CN)
            if stamp > received_at + timedelta(seconds=30):
                raise ValueError('来源时间在未来')
            if trading_day(stamp.date()) is False or not time(9, 15) <= stamp.time() <= time(18):
                raise ValueError('来源时间不在可信交易日/快照时段')
            rows[symbol] = dict(symbol=symbol, name=fields[1], price=float(price), previous_close=float(previous),
                change=float(price-previous), change_pct=round(float((price-previous)/previous*100), 4),
                volume_lots=float(volume), source_time=stamp.isoformat(), received_at=received_at.isoformat(),
                source=SOURCE, security_status='zero_volume_unknown' if volume == 0 else 'not_verified')
        except (ValueError, InvalidOperation, OverflowError) as exc:
            errors[symbol] = str(exc) or '来源数据无效'
    for symbol in requested:
        if symbol not in rows and symbol not in errors:
            errors[symbol] = '来源未返回此代码'
    return rows, errors


def quote_status(quote, now):
    now = now.astimezone(CN)
    market = market_state(now)
    state = 'unavailable'
    if quote:
        source = datetime.fromisoformat(quote['source_time'])
        received = datetime.fromisoformat(quote['received_at'])
        phase = market['phase']
        if phase == 'calendar_unknown' or not market['expected_date'] or trading_day(source.date()) is None:
            state = 'calendar_unknown'
        elif (now-received).total_seconds() > 180 or received > now + timedelta(seconds=30):
            state = 'stale_cache'
        elif source > now + timedelta(seconds=30):
            state = 'invalid_time'
        elif quote['security_status'] == 'zero_volume_unknown':
            state = 'status_unknown'
        elif source.date().isoformat() != market['expected_date']:
            state = 'stale'
        elif phase in ('trading', 'auction'):
            state = 'fresh' if (now-source).total_seconds() <= 180 else 'stale'
        elif phase == 'lunch':
            state = 'break_latest' if source.time() >= time(11, 28) else 'stale'
        else:
            state = 'closed_latest' if source.time() >= time(14, 58) else 'stale'
    return dict(freshness=state, valid_for_valuation=state in ('fresh', 'break_latest', 'closed_latest'), market=market)


def fetch_tencent(symbols):
    url = 'https://qt.gtimg.cn/q=' + ','.join(s[-2:].lower()+s[:6] for s in symbols)
    request = urllib.request.Request(url, headers={'User-Agent':'quant-local/phase4', 'Referer':'https://gu.qq.com/'})
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError('来源响应过大')
    return raw.decode('gb18030')


class QuoteService:
    """One process-wide provider cache; manual reads obey the same throttle.

    All I/O is inside this service's own mutex, never a database transaction.
    One call fetches at most 50 due symbols, with oldest attempts first.
    """
    def __init__(self, transport=None, clock=None):
        self.transport = transport or fetch_tencent
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        self.entries = OrderedDict()
        self.watched = {}
        self.next_batch_at = None
        self.failures = 0

    def get(self, symbols, watch=True):
        symbols = list(dict.fromkeys(symbols))
        if any(not SYMBOL.fullmatch(s) for s in symbols) or len(symbols) > 1000:
            raise ValueError('仅支持沪深A股完整代码，例如600000.SH；单次最多1000个账户持仓标的')
        with self.lock:
            now = self.clock().astimezone(CN)
            self.watched = {s:until for s,until in self.watched.items() if until > now}
            if watch:
                for symbol in symbols:
                    self.watched[symbol] = now + timedelta(seconds=120)
            for symbol in symbols:
                self.entries.setdefault(symbol, dict(quote=None, last_attempt_at=None, last_success_at=None,
                    next_attempt_at=now, error=None, failures=0))
                self.entries.move_to_end(symbol)
            due = sorted((s for s in symbols if self.entries[s]['next_attempt_at'] <= now),
                         key=lambda s:self.entries[s]['last_attempt_at'] or '')[:MAX_BATCH]
            if due and (self.next_batch_at is None or now >= self.next_batch_at):
                for symbol in due:
                    self.entries[symbol]['last_attempt_at'] = now.isoformat()
                try:
                    raw = self.transport(due)
                    received = self.clock().astimezone(CN)
                    rows, errors = parse_snapshot(raw, due, received)
                    for symbol in list(rows):
                        old = self.entries[symbol]['quote']
                        if old and rows[symbol]['source_time'] < old['source_time']:
                            rows.pop(symbol); errors[symbol] = '来源时间倒退，保留旧值并停止有效估值'
                    source_failed = not rows
                except Exception as exc:
                    received = self.clock().astimezone(CN)
                    rows, errors = {}, {s:'公开行情请求失败（'+type(exc).__name__+'），稍后重试' for s in due}
                    source_failed = True
                self.failures = min(self.failures+1, 4) if source_failed else 0
                self.next_batch_at = received + timedelta(seconds=min(300, 45*2**(self.failures-1)) if self.failures else 2)
                for symbol in due:
                    entry = self.entries[symbol]
                    if symbol in rows:
                        entry.update(quote=rows[symbol], last_success_at=received.isoformat(), error=None, failures=0)
                    else:
                        entry.update(error=errors[symbol], failures=min(entry['failures']+1, 4))
                    delay = min(300, 45*2**max(0, entry['failures']-1))
                    entry['next_attempt_at'] = received + timedelta(seconds=delay)
            now = self.clock().astimezone(CN)
            views = [self._view(s, now) for s in symbols]
            # Bound memory even with many successive searches. Inactive oldest entries go first.
            while len(self.entries) > 1500:
                old, _ = self.entries.popitem(last=False)
                self.watched.pop(old, None)
            return dict(quotes=views, server_time=now.isoformat(), refresh_seconds=REFRESH_SECONDS,
                        source=SOURCE, market=market_state(now))

    def _view(self, symbol, now):
        entry = self.entries[symbol]
        quote = entry['quote']
        state = quote_status(quote, now)
        if entry['error']:
            state['valid_for_valuation'] = False
        next_at = max(entry['next_attempt_at'], self.next_batch_at or now)
        return dict(**(quote or dict(symbol=symbol, name=symbol, price=None, previous_close=None,
                    change=None, change_pct=None, source_time=None, received_at=None,
                    source=SOURCE, security_status='not_verified')), **state,
                    feed_status='error' if entry['error'] else 'ok' if quote else 'waiting',
                    error=entry['error'], last_attempt_at=entry['last_attempt_at'],
                    last_success_at=entry['last_success_at'], next_attempt_at=next_at.isoformat())

    def watch_symbols(self):
        with self.lock:
            now = self.clock().astimezone(CN)
            return [s for s, until in self.watched.items() if until > now]
