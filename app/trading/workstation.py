"""Select market data automatically and share the signal engine across workspaces."""
from datetime import date, datetime, time, timedelta
from threading import Event, Thread
import logging
import re
from sqlite3 import OperationalError

from fastapi import APIRouter, HTTPException
from pydantic import Field

from app.store import now
from app.trading import demo_market, engine, feeds, research
from app.trading.conditions import indicator_names, raw_only_indicators
from app.trading.datasets import CN_TZ
from app.trading.indicators import IndicatorEngine, REGISTRY, normalize_params
from app.trading.models import MAIN_BOARD_SYMBOL_PATTERN, RunInput, portfolio_timeframe
from app.trading.portfolios import check_portfolio_symbol, ready_portfolio
from app.trading.quotes import trading_day
from app.trading.store import identity

BACKTEST = 'workstation_backtest'
PAPER = 'workstation_paper'
MARKET_REPLAY = 'market_replay'
DAY_INDICATORS = {'FIRST_LIMIT_UP', 'LIMIT_UP_STREAK', 'IS_LIMIT_UP', 'IS_LIMIT_DOWN'}
PRICE_INDICATORS = {'OPEN', 'HIGH', 'LOW', 'CLOSE', 'PREV_CLOSE', 'ATR',
                    'BOLL_MID', 'BOLL_UPPER', 'BOLL_LOWER', 'MACD_DIF', 'MACD_DEA', 'MACD_HIST'}


class WorkstationInput(RunInput):
    dataset_id: None = Field(default=None, exclude=True)
    start_date: str


def trading_date(bar):
    return bar.get('trading_day', bar['date'][:10])


def inside_session(stamp):
    t = stamp.time()
    return time(9, 30) <= t < time(11, 30) or time(13) <= t < time(15)


def eligible_open(recent):
    end = datetime.fromisoformat(recent['date'])
    return end.replace(hour=13, minute=0) if end.time() == time(11, 30) else end


def calendar_edge(value, direction):
    day = date.fromisoformat(value)
    while day.weekday() >= 5 or trading_day(day) is False:
        day += timedelta(days=direction)
    return day.isoformat()


def days_before(day, count):
    return date.fromordinal(max(1, day.toordinal() - count)).isoformat()


def has_absolute_price(node):
    if 'conditions' in node:
        return any(has_absolute_price(child) for child in node['conditions'])
    for operand, opposite in ((node['left'], node['right']), (node['right'], node['left'])):
        name = operand.get('indicator')
        if 'value' in opposite and (name in PRICE_INDICATORS or (
                name in ('MA', 'EMA') and operand.get('params', {}).get('field', 'close') != 'volume')):
            return True
    return False


def needs_unadjusted(portfolio):
    if raw_only_indicators(portfolio):
        return True
    for item in portfolio['items']:
        if item['enabled']:
            rule = item['rules']
            if rule['type'] == 'threshold' or (rule['type'] == 'conditional'
                    and (has_absolute_price(rule['buy']) or has_absolute_price(rule['sell']))):
                return True
    return False


def chart_indicators(run, first):
    book = IndicatorEngine(run['_history'])
    used = {}

    def collect(value):
        if not isinstance(value, dict):
            return
        if 'indicator' in value:
            name = value['indicator']
            params = normalize_params(name, value.get('params'))
            used[name, tuple(sorted(params.items()))] = params
        for child in value.values():
            if isinstance(child, list):
                for node in child:
                    collect(node)
            elif isinstance(child, dict):
                collect(child)

    for item in run['portfolio_snapshot']['items']:
        if item['enabled']:
            rule = item['rules']
            collect(rule)
            if rule['type'] == 'ma':
                for period in (rule['fast'], rule['slow']):
                    params = normalize_params('MA', {'period': period})
                    used['MA', tuple(sorted(params.items()))] = params
            elif rule['type'] == 'threshold':
                used['CLOSE', ()] = {}

    requested = dict(used)
    for name in REGISTRY:
        if run['timeframe'] == '5m' and name in DAY_INDICATORS:
            continue
        if run['execution_model'] in ('adjusted_research', 'raw_replay') and REGISTRY[name]['raw_only']:
            continue
        params = normalize_params(name)
        requested.setdefault((name, tuple(sorted(params.items()))), params)
    result = []
    for key, params in requested.items():
        name = key[0]
        label = REGISTRY[name]['label']
        if run['timeframe'] == '5m':
            label = {'PREV_CLOSE': '上一根收盘价', 'CHANGE_PCT': '5分钟涨跌幅',
                     'GAP_PCT': '5分钟开盘缺口', 'AMPLITUDE_PCT': '5分钟振幅',
                     'VOLUME_RATIO': '本根成交量 / 前序均量'}.get(name, label)
        result.append(dict(name=name, label=label, params=params, used=key in used,
                           values=book.series(name, params)[first:]))
    return result


def public(run):
    first = run['_display_from']
    if run.get('mode') == 'incremental':
        first = max(first, len(run['_history']) - 600)
    return engine.public(run) | dict(bars=run['_history'][first:], indicator_series=chart_indicators(run, first))


class Workstation:
    def __init__(self, store, sources, provider=None, clock=None, quote=None, *,
                 history_store=None, replay_market=None):
        if provider is None:
            from app.trading import minutes
            provider = minutes
        self.store = store
        self.sources = sources
        self.provider = provider
        self.history_store = history_store
        self.replay_market = replay_market
        self.clock = clock or (lambda: datetime.now(CN_TZ))
        self.quote = quote or (lambda symbol: None)
        self.minute_slot = None
        self.minute_rows = {}

    def current(self):
        return self.clock().astimezone(CN_TZ)

    def setup(self, body):
        with self.store.transaction() as c:
            portfolio = ready_portfolio(self.store, c, self.sources, body.portfolio_id, body.portfolio_revision)
        try:
            timeframe = portfolio_timeframe(portfolio)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        check_portfolio_symbol(portfolio, body.symbol, ticker_message='{name}指定 {ticker}，请选择该股票')
        for item in portfolio['items']:
            if not item['enabled']:
                continue
            source = item.get('source_snapshot')
            if timeframe == '5m':
                restricted = indicator_names(item['rules']) & DAY_INDICATORS
                if restricted:
                    raise HTTPException(400, '以下指标按日线定义，请在日线策略中使用：' + '、'.join(sorted(restricted)))
                if source:
                    origin = (source['strategy'].get('timeframe') or {}).get('value', '')
                    if not re.search(r'(?:5|五)\s*分钟', origin):
                        raise HTTPException(400, '来源草案需明确为5分钟周期才能运行盘中规则')
        if timeframe == '5m' and not re.fullmatch(MAIN_BOARD_SYMBOL_PATTERN, body.symbol):
            raise HTTPException(400, '5分钟模拟撮合目前支持沪深普通主板股票')
        return portfolio, timeframe

    def ledger(self, body, portfolio, timeframe, kind):
        return dict(**identity(), **body.model_dump(), **engine.new_ledger(body.initial_cash),
                    portfolio_snapshot=portfolio, timeframe=timeframe, kind=kind,
                    name=portfolio['name'], execution_model='strict_daily', price_basis='raw',
                    quantity_unit='share', status='running', feed_status='waiting', warnings=[],
                    _display_from=0)

    def daily_history(self, run, start, end, allow_research):
        symbol = run['symbol']
        strict = needs_unadjusted(run['portfolio_snapshot'])
        if self.history_store is None:
            with self.store.transaction() as c:
                datasets = self.store.list(c, 'dataset')
        else:
            try:
                with self.history_store.readonly_transaction() as c:
                    datasets = self.history_store.list(c, 'dataset')
            except OperationalError:
                raise ValueError('已有沪深300回测行情库无法读取') from None
        candidates = []
        if self.history_store is not None and self.replay_market is not None:
            days = self.replay_market.trading_days(start, end)
            if not days:
                return []
            first_day, last_day = days[0], days[-1]
        else:
            first_day, last_day = calendar_edge(start, 1), calendar_edge(end, -1)
            if first_day > last_day:
                return []
        for dataset in datasets:
            adjusted = dataset.get('dataset_type') == 'research_adjusted'
            if dataset['is_demo'] or symbol not in dataset['symbols'] or (adjusted and (strict or not allow_research)):
                continue
            rows = [b for b in dataset['rows'] if b['symbol'] == symbol]
            if rows and rows[0]['date'] <= first_day and rows[-1]['date'] >= last_day:
                candidates.append((adjusted, rows, dataset['name']))
        if candidates:
            adjusted, rows, name = max(candidates, key=lambda x: (x[0], len(x[1])))
            if adjusted:
                run.update(execution_model='adjusted_research', price_basis='forward_adjusted',
                           quantity_unit='synthetic_unit', warnings=list(research.LIMITATIONS))
            run['data_source'] = name
            return [bar for bar in rows if bar['date'] <= end]
        if self.history_store is not None:
            if strict:
                raise ValueError('已有沪深300回测库为前复权日线，所选策略需要未复权行情或官方涨跌停价')
            raise ValueError(f'已有沪深300回测行情缺少 {symbol} 在所选日期的覆盖')
        data = feeds.fetch(symbol, start_date=days_before(date.fromisoformat(start), 1100), end_date=end)
        run['data_source'] = data['source']
        return data['rows']

    def history(self, run, start, end, allow_research=True):
        if run['timeframe'] == 'daily':
            return self.daily_history(run, start, end, allow_research)
        if self.history_store is not None or self.replay_market is not None:
            raise ValueError('已有沪深300历史行情仅提供日线，请选择日线策略')
        run['data_source'] = 'Tushare 历史 5 分钟日内行情和每日限价'
        run['execution_model'] = 'strict_intraday'
        selected = self.provider.history(run['symbol'], start, end)
        return self.warm_minutes(run, date.fromisoformat(start)) + selected

    def warm_minutes(self, run, before):
        start = days_before(before, 40)
        end = days_before(before, 1)
        if end >= before.isoformat():
            return []
        try:
            return self.provider.history(run['symbol'], start, end)
        except ValueError:
            warning = '起日前 5 分钟数据不足，指标会用可取得的行情继续预热'
            if warning not in run['warnings']:
                run['warnings'].append(warning)
            return []

    def run_history(self, body, portfolio, timeframe, kind):
        if not body.end_date:
            raise HTTPException(400, '请填写结束日期')
        if body.end_date > self.current().date().isoformat():
            raise HTTPException(400, '历史运行结束日期不能在未来')
        run = self.ledger(body, portfolio, timeframe, kind)
        try:
            rows = self.history(run, body.start_date, body.end_date, allow_research=(kind == BACKTEST))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        active = [bar for bar in rows if body.start_date <= trading_date(bar) <= body.end_date]
        if not active:
            raise HTTPException(400, '所选股票与日期没有可用行情')
        run['_history'] = [bar for bar in rows if trading_date(bar) < body.start_date]
        run['_display_from'] = len(run['_history'])
        advance = research.advance if run['execution_model'] == 'adjusted_research' else engine.advance
        previous = None
        for bar in active:
            if timeframe == '5m':
                same_day = previous and trading_date(previous) == trading_date(bar)
                advance(run, portfolio, bar, run['costs'], body.symbol, body.initial_cash,
                        execute_pending=bool(same_day))
                previous = bar
            else:
                advance(run, portfolio, bar, run['costs'], body.symbol, body.initial_cash)
        run.update(status='completed', feed_status='exhausted', message='历史行情已处理完成',
                   actual_start_date=trading_date(active[0]), actual_end_date=trading_date(active[-1]),
                   initial_equity=body.initial_cash, final_equity=run['equity'][-1]['equity'])
        run['pnl'] = engine.money(run['final_equity'] - body.initial_cash)
        return run

    def backtest(self, body: WorkstationInput):
        run = self.run_history(body, *self.setup(body), BACKTEST)
        with self.store.transaction() as c:
            self.store.put(c, BACKTEST, run)
        return public(run)

    def create_paper(self, body: WorkstationInput):
        portfolio, timeframe = self.setup(body)
        current = self.current()
        today = current.date().isoformat()
        if self.replay_market is not None:
            run = self.create_market_replay(body, portfolio, timeframe, current)
        elif body.end_date and (body.end_date < today or (body.end_date == today and current.time() >= time(15))):
            run = self.run_history(body, portfolio, timeframe, PAPER)
            run['mode'] = 'replay'
        else:
            run = self.ledger(body, portfolio, timeframe, PAPER)
            run.update(mode='incremental', _activated_at=current.isoformat(), _preheated=False,
                       execution_model='strict_intraday' if timeframe == '5m' else 'strict_daily',
                       message='等待已完成行情和信号之后的可用报价')
        with self.store.transaction() as c:
            self.store.put(c, PAPER, run)
        return public(run)

    def create_market_replay(self, body, portfolio, timeframe, current):
        if timeframe != 'daily':
            raise HTTPException(400, '沪深300模拟盘仅提供历史日线，请选择日线策略')
        if raw_only_indicators(portfolio):
            raise HTTPException(400, '沪深300模拟盘历史源没有官方涨跌停价，请选择无需涨跌停指标的策略')
        end = body.end_date or demo_market.END_DATE
        if not demo_market.START_DATE <= body.start_date <= end <= demo_market.END_DATE:
            raise HTTPException(400, f'模拟盘日期须在 {demo_market.START_DATE} 至 {demo_market.END_DATE} 内')
        run = self.ledger(body, portfolio, timeframe, PAPER)
        run.update(mode=MARKET_REPLAY, end_date=end, execution_model='raw_replay',
                   quantity_unit='synthetic_unit', data_source=demo_market.SOURCE,
                   warnings=list(demo_market.LIMITATIONS))
        try:
            self.advance_market_replay(run, demo_market.simulated_time(current))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return run

    def advance_market_replay(self, run, simulated_at):
        cutoff = demo_market.completed_through(simulated_at)
        end = min(run['end_date'], cutoff)
        rows = self.replay_market.visible_history(run['symbol'], end)
        if run['_history'] and run['_history'][-1]['date'] > end:
            # Rebuild all derived output if the system clock moves backwards.
            run.update(engine.new_ledger(run['initial_cash']), _display_from=0)
            for key in ('_indicator_cache', '_research_peak', 'actual_start_date', 'actual_end_date'):
                run.pop(key, None)
        last = run['_history'][-1]['date'] if run['_history'] else ''
        for bar in rows:
            if bar['date'] <= last:
                continue
            if bar['date'] < run['start_date']:
                run['_history'].append(bar)
                run['_display_from'] += 1
                continue
            research.advance(run, run['portfolio_snapshot'], bar, run['costs'],
                             run['symbol'], run['initial_cash'])
            run.setdefault('actual_start_date', bar['date'])
            run['actual_end_date'] = bar['date']
        run.update(simulated_at=simulated_at.isoformat(), updated_at=now())
        if cutoff >= run['end_date']:
            run.update(status='completed', feed_status='exhausted', _pending=None, message='已到模拟盘结束日期')
        else:
            run.update(status='running', feed_status='fresh' if run['signals'] else 'waiting',
                       message='随模拟时钟更新，完整日线在收盘后可见')

    def check_paper_mode(self, run):
        if self.replay_market is not None and run.get('mode') != MARKET_REPLAY:
            raise KeyError('交易资源不存在')

    def public_paper(self, run):
        if self.replay_market is not None:
            self.check_paper_mode(run)
            simulated_at = demo_market.simulated_time(self.current())
            if simulated_at < datetime.fromisoformat(run['simulated_at']):
                paused = run['status'] == 'paused'
                self.advance_market_replay(run, simulated_at)
                if paused:
                    run.update(status='paused', feed_status='paused', message='已暂停')
        return public(run)

    def get(self, kind, ident):
        with self.store.transaction() as c:
            return self.store.get(c, kind, ident)

    def paper(self, ident: str):
        return self.public_paper(self.get(PAPER, ident))

    def list(self, kind):
        keys = ('id', 'name', 'symbol', 'timeframe', 'status', 'start_date', 'end_date', 'mode',
                'portfolio_id', 'portfolio_revision', 'created_at')
        with self.store.transaction() as c:
            return [{key: run.get(key) for key in keys} for run in self.store.list(c, kind)
                    if kind != PAPER or self.replay_market is None or run.get('mode') == MARKET_REPLAY]

    def recover(self):
        with self.store.transaction() as c:
            for run in self.store.list(c, PAPER):
                if run['status'] == 'running':
                    run.update(status='paused', feed_status='paused', _pending=None, message='程序已重启，请启动恢复')
                    self.store.put(c, PAPER, run)

    def action(self, ident, action):
        with self.store.transaction() as c:
            run = self.store.get(c, PAPER, ident)
            self.check_paper_mode(run)
            if run['status'] == 'completed' or (action == 'start' and run['status'] == 'running'):
                return self.public_paper(run)
            if run.get('mode') == MARKET_REPLAY:
                if action == 'start':
                    run.update(status='running', feed_status='waiting', message='已启动，等待模拟行情')
                else:
                    run.update(status='paused', feed_status='paused', message='已暂停')
            elif action == 'start':
                run.update(status='running', feed_status='waiting', _activated_at=self.current().isoformat(),
                           _pending=None, _observed_signal_at=None, message='已启动，等待新行情')
            else:
                run.update(status='paused', feed_status='paused', _pending=None, message='已暂停')
            run['_generation'] = run.get('_generation', 0) + 1
            self.store.put(c, PAPER, run)
        return self.public_paper(run)

    def live_rows(self, run, current):
        if run['timeframe'] == 'daily':
            run['data_source'] = 'Tushare 未复权日线和每日限价'
            return feeds.fetch(run['symbol'])['rows']
        if not run['_preheated']:
            run['_history'] = self.warm_minutes(run, current.date())
            run['_display_from'] = next((i for i, row in enumerate(run['_history'])
                                         if trading_date(row) >= run['start_date']), len(run['_history']))
            run['_preheated'] = True
        elif run.get('_live_day') and run['_live_day'] < current.date().isoformat() and run['_history']:
            last = run['_history'][-1]
            # A restart or a provider outage can leave an incomplete earlier session.
            # Only resume today after checking the intervening history for continuity.
            yesterday = (current.date() - timedelta(days=1)).isoformat()
            recovered = self.provider.history(run['symbol'], trading_date(last), yesterday)
            run['_history'].extend(row for row in recovered if row['date'] > last['date'])
            run['_pending'] = None
            run['_observed_signal_at'] = None
        run['_live_day'] = current.date().isoformat()
        run['data_source'] = 'Tushare 盘中 5 分钟行情和每日限价'
        slot = current.replace(minute=current.minute // 5 * 5, second=0, microsecond=0)
        if current.time() >= time(15):
            slot = slot.replace(hour=15, minute=0)
        elif time(11, 30) <= current.time() < time(13):
            slot = slot.replace(hour=11, minute=30)
        if self.minute_slot != slot:
            self.minute_slot = slot
            self.minute_rows.clear()
        symbol = run['symbol']
        if symbol not in self.minute_rows:
            rows = self.provider.latest(symbol)
            if rows:
                self.minute_rows[symbol] = rows
            return rows
        return self.minute_rows[symbol]

    def execute_quote(self, run, quote, current):
        pending = run['_pending']
        observed = run.get('_observed_signal_at')
        if run['timeframe'] != '5m' or not (pending and observed and quote and quote.get('source_time') and quote.get('received_at')):
            return
        if quote.get('symbol') != run['symbol'] or quote.get('feed_status') == 'error' or not quote.get('price'):
            return
        stamp = datetime.fromisoformat(quote['source_time'])
        received = datetime.fromisoformat(quote['received_at'])
        observed = datetime.fromisoformat(observed)
        if not inside_session(stamp) or not (observed < stamp <= current and observed < received <= current):
            return
        recent = run['_history'][-1]
        opening = eligible_open(recent)
        if not (opening <= stamp < opening + timedelta(minutes=5) and current < opening + timedelta(minutes=5)
                and current - stamp <= timedelta(seconds=75)):
            return
        price = quote['price']
        execution_time = max(stamp, received).isoformat()
        trade_bar = dict(recent, date=execution_time, execution_time=execution_time,
                         open=price, high=recent['limit_up'], low=recent['limit_down'], close=price,
                         volume=quote.get('volume_lots', 0) * 100)
        order_count, fill_count = len(run['orders']), len(run['fills'])
        engine.execute(run, trade_bar, pending, run['costs'], run['symbol'])
        timing = dict(signal_observed_at=observed.isoformat(), quote_time=stamp.isoformat(), quote_received_at=received.isoformat())
        if len(run['orders']) > order_count:
            run['orders'][-1].update(timing)
        if len(run['fills']) > fill_count:
            run['fills'][-1].update(timing)
        engine.mark_equity(run, trade_bar, run['initial_cash'])
        run['_pending'] = None

    def advance_live(self, run):
        current = self.current()
        today = current.date().isoformat()
        if today < run['start_date']:
            run.update(feed_status='waiting', message='等待所选开始日期')
            return
        if run['end_date'] and today > run['end_date']:
            run.update(status='completed', feed_status='exhausted', _pending=None, message='已到结束日期')
            return
        activated = datetime.fromisoformat(run['_activated_at'])
        quote = self.quote(run['symbol'])
        run['quote'] = quote
        rows = self.live_rows(run, current)
        last = run['_history'][-1]['date'] if run['_history'] else ''
        for bar in rows:
            if bar['date'] <= last:
                continue
            stamp = (datetime.fromisoformat(bar['date']) if run['timeframe'] == '5m'
                     else datetime.combine(date.fromisoformat(bar['date']), time(15), CN_TZ))
            if stamp > current:
                continue
            if stamp <= activated:
                run['_history'].append(bar)
                if run['timeframe'] == 'daily' and not run['signals']:
                    run['_display_from'] = max(0, len(run['_history']) - 60)
                continue
            allow_open = False
            if run['timeframe'] == 'daily' and run.get('_observed_signal_at') and run['_pending']:
                open_time = datetime.combine(stamp.date(), time(9, 30), CN_TZ)
                allow_open = open_time > datetime.fromisoformat(run['_observed_signal_at'])
            engine.advance(run, run['portfolio_snapshot'], bar, run['costs'], run['symbol'],
                           run['initial_cash'], execute_pending=allow_open)
            run['_observed_signal_at'] = self.current().isoformat()
        self.execute_quote(run, quote, self.current())
        if run['end_date'] == today and rows and current.time() >= time(15) and trading_date(rows[-1]) == today:
            last_end = 'T15:00:00' in rows[-1]['date'] if run['timeframe'] == '5m' else True
            if last_end:
                run.update(status='completed', feed_status='exhausted', _pending=None, message='已到结束日期',
                           updated_at=now())
                return
        if run['timeframe'] == 'daily':
            message = '日线行情已同步，按已收盘数据记录下一交易日开盘模拟' if rows else '等待已完成日线'
        else:
            message = '行情已同步，等待下一次信号或可用报价' if rows else '等待已完成行情'
        run.update(feed_status='fresh' if rows else 'waiting',
                   message=message, updated_at=now())

    def tick(self):
        with self.store.transaction() as c:
            running = [run for run in self.store.list(c, PAPER) if run['status'] == 'running'
                       and (run.get('mode') == MARKET_REPLAY) == (self.replay_market is not None)]
        for run in running:
            generation = run.get('_generation', 0)
            try:
                if self.replay_market is not None:
                    self.advance_market_replay(run, demo_market.simulated_time(self.current()))
                else:
                    self.advance_live(run)
            except ValueError as exc:
                if self.replay_market is not None:
                    run = self.get(PAPER, run['id'])
                run.update(feed_status='error', message=str(exc), updated_at=now())
            except Exception:
                logging.getLogger(__name__).exception('Workstation session update failed')
                run = self.get(PAPER, run['id'])
                run.update(feed_status='error', message='行情或撮合处理失败，系统会继续重试', updated_at=now())
            with self.store.transaction() as c:
                latest = self.store.get(c, PAPER, run['id'])
                if latest['status'] == 'running' and latest.get('_generation', 0) == generation:
                    self.store.put(c, PAPER, run)


class WorkstationWorker:
    def __init__(self, service):
        self.service = service
        self.stop = Event()
        self.thread = Thread(target=self.run, name='market-workstation', daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.wait(15):
            try:
                self.service.tick()
            except Exception:
                logging.getLogger(__name__).exception('Workstation update failed')

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)


def router(service):
    api = APIRouter(prefix='/api/trading/workstation', tags=['行情工作台'])
    api.post('/backtests', status_code=201)(service.backtest)
    api.post('/paper/sessions', status_code=201)(service.create_paper)
    api.get('/paper/sessions/{ident}')(service.paper)

    @api.get('/backtests')
    def backtests():
        return service.list(BACKTEST)

    @api.get('/backtests/{ident}')
    def backtest(ident: str):
        return public(service.get(BACKTEST, ident))

    @api.get('/paper/sessions')
    def sessions():
        return service.list(PAPER)

    @api.post('/paper/sessions/{ident}/start')
    def start(ident: str):
        return service.action(ident, 'start')

    @api.post('/paper/sessions/{ident}/pause')
    def pause(ident: str):
        return service.action(ident, 'pause')

    return api
