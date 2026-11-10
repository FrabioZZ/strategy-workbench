"""Account-free historical adapter. BackBroker, not the local matcher, owns money.

Only portfolio signal semantics and the cost formula are shared with Phase 2.
No broker credentials, external account connection, or live execution path exists.
"""
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from fastapi import HTTPException
from app.trading.engine import fee, money, signal

PINNED_VERSION = '1.9.78.123'


def engine_info():
    try:
        installed = version('backtrader')
    except PackageNotFoundError:
        installed = None
    return dict(name='Backtrader BackBroker', version=installed, expected_version=PINNED_VERSION,
                installed=installed == PINNED_VERSION, license='GPL-3.0-or-later')


def replay(portfolio, rows, initial_cash, costs):
    info = engine_info()
    if not info['installed']:
        raise HTTPException(503, '请在本机安装 requirements-paper.txt 中的可选模拟引擎版本')
    import backtrader as bt

    result = dict(engine=info, cash=initial_cash, positions=[], signals=[], orders=[], fills=[], equity=[],
                  metrics=dict(total_return_pct=0, max_drawdown_pct=0, fees=0, trade_count=0))
    if not rows:
        return result

    class RowsFeed(bt.feed.DataBase):
        def start(self):
            super().start()
            self.iterator = iter(rows)

        def _load(self):
            row = next(self.iterator, None)
            if row is None:
                return False
            self.lines.datetime[0] = bt.date2num(datetime.fromisoformat(row['date']))
            for key in ('open', 'high', 'low', 'close', 'volume'):
                getattr(self.lines, key)[0] = row[key]
            self.lines.openinterest[0] = 0
            return True

    class WorkbenchCommission(bt.CommInfoBase):
        params = (('stocklike', True), ('commtype', bt.CommInfoBase.COMM_PERC))

        def _getcommission(self, size, price, pseudoexec):
            return fee(abs(size), price, 'buy' if size > 0 else 'sell', costs) if size else 0

    def market_guard(order, price, ago):
        row = rows[len(order.data) - 1]
        reason = ''
        if row['suspended'] or row['volume'] == 0:
            reason = '停牌或零成交量，无法撮合'
        elif row['open'] >= row['limit_up'] - .005 or row['open'] <= row['limit_down'] + .005:
            reason = '开盘触及涨跌停，保守拒单'
        elif not row['limit_down'] <= price <= row['limit_up']:
            reason = '滑点成交价超出每日限价'
        if reason:
            order.addinfo(block_reason=reason)
            return 0
        return abs(order.executed.remsize)

    class FrozenPortfolio(bt.Strategy):
        def __init__(self):
            self.signal_state = {'_history': [], '_states': {}}
            self.pending = None
            self.records = {}
            self.filled_ids = set()

        def record(self, order):
            ident = order.info.business_id
            record = self.records[ident]
            record['engine_status'] = order.getstatusname()
            record['status'] = {order.Submitted: 'submitted', order.Accepted: 'accepted',
                order.Completed: 'filled', order.Canceled: 'cancelled', order.Margin: 'rejected',
                order.Rejected: 'rejected', order.Expired: 'cancelled'}.get(order.status, 'accepted')
            if order.status in (order.Margin, order.Rejected):
                record.update(date=self.data.datetime.date(0).isoformat(), reason='引擎拒单：资金不足或订单不可接受')
            if order.status == order.Canceled:
                record.update(date=order.info.get('cancel_date') or self.data.datetime.date(0).isoformat(),
                              reason=order.info.get('block_reason') or '下一根未能成交，收盘撤销，不跨日排队')
            if order.status == order.Completed:
                record.update(date=bt.num2date(order.executed.dt).date().isoformat(),
                              price=float(order.executed.price), fee=money(order.executed.comm))
                if ident not in self.filled_ids:
                    self.filled_ids.add(ident)
                    result['fills'].append({k: record[k] for k in
                        ('signal_date', 'date', 'symbol', 'side', 'quantity', 'price', 'fee')} | {'order_id': ident})

        def notify_order(self, order):
            self.record(order)

        def next(self):
            row = rows[len(self.data) - 1]
            if self.pending is not None and self.pending.alive():
                self.pending.addinfo(cancel_date=row['date'])
                self.cancel(self.pending)
                self.record(self.pending)
            self.pending = None
            self.signal_state['_history'].append(row)
            sig = signal(self.signal_state, portfolio, row)
            result['signals'].append(sig)
            cash, equity = self.broker.getcash(), self.broker.getvalue()
            result['equity'].append(dict(date=row['date'], cash=money(cash),
                                        market_value=money(equity-cash), equity=money(equity)))
            if sig['target_pct'] is None:
                return
            quantity = int(self.position.size)
            desired = int(equity * sig['target_pct'] / 100 / row['close'] / 100) * 100
            difference = desired - quantity
            if difference > 0:
                # Fixed quantity is decided at the known close, with a fee reserve.
                # Gap-up execution may still be rejected by BackBroker at the open.
                low, high = 0, difference // 100
                while low < high:
                    mid = (low + high + 1) // 2
                    required = mid*100*row['close'] + fee(mid*100, row['close'], 'buy', costs)
                    if required <= cash + 1e-8:
                        low = mid
                    else:
                        high = mid - 1
                difference = low * 100
            if not difference:
                return
            side = 'buy' if difference > 0 else 'sell'
            ident = row['symbol'] + ':' + row['date'] + ':' + side
            record = dict(id=ident, signal_date=row['date'], date=None, symbol=row['symbol'], side=side,
                          quantity=abs(difference), price=None, fee=0, status='submitted',
                          reason='', engine_status='Submitted')
            self.records[ident] = record
            result['orders'].append(record)
            self.pending = (self.buy if difference > 0 else self.sell)(
                size=abs(difference), exectype=bt.Order.Market, business_id=ident)

        def stop(self):
            result['cash'] = money(self.broker.getcash())
            if self.position.size:
                today_buys = sum(f['quantity'] for f in result['fills']
                                if f['side'] == 'buy' and f['date'] == rows[-1]['date'])
                result['positions'] = [dict(symbol=rows[-1]['symbol'], quantity=int(self.position.size),
                    available_quantity=max(0, int(self.position.size)-today_buys),
                    average_cost=round(self.position.price, 6))]

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(RowsFeed())
    cerebro.addstrategy(FrozenPortfolio)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(WorkbenchCommission())
    cerebro.broker.set_filler(market_guard)
    cerebro.broker.set_slippage_perc(costs['slippage_bps']/10000, slip_open=True,
                                     slip_match=False, slip_limit=False, slip_out=False)
    cerebro.broker.set_coc(False)
    cerebro.broker.set_coo(False)
    cerebro.run(preload=False, runonce=False)
    peak, drawdown = initial_cash, 0
    for point in result['equity']:
        peak = max(peak, point['equity'])
        drawdown = max(drawdown, (peak-point['equity'])/peak*100)
    result['metrics'] = dict(total_return_pct=round((result['equity'][-1]['equity']/initial_cash-1)*100, 6),
        max_drawdown_pct=round(drawdown, 6), fees=money(sum(f['fee'] for f in result['fills'])),
        trade_count=len(result['fills']))
    return result
