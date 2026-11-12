"""Deterministic bar signal and execution engine with no I/O or wall clock."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from app.trading.indicators import IndicatorEngine
from app.trading.conditions import evaluate


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))


def fee(quantity, price, side, costs):
    gross=quantity*price
    return money(max(costs['min_commission'],gross*costs['commission_bps']/10000)+
                 (gross*costs['sell_tax_bps']/10000 if side=='sell' else 0))


def new_ledger(initial_cash):
    return dict(cash=money(initial_cash),positions=[],signals=[],orders=[],fills=[],equity=[],
                metrics=dict(total_return_pct=0,max_drawdown_pct=0,fees=0,trade_count=0),
                _history=[],_states={},_pending=None,_sellable_trading_day=None,_equity_peak=None)


def signal(ledger, portfolio, bar):
    history=ledger['_history']; components=[]
    indicators=IndicatorEngine(history,ledger.setdefault('_indicator_cache',{}))
    for item in portfolio['items']:
        if not item['enabled']: continue
        rule=item['rules']; state=ledger['_states'].setdefault(item['id'],{'target':0,'entry':None})
        old=state['target']; target=old; reason='保持上次目标'
        if rule['type']=='threshold':
            if bar['close']<=rule['buy_below']: target=rule['target_pct']; reason='收盘达到买入条件'
            elif bar['close']>=rule['sell_above']: target=0; reason='收盘达到卖出条件'
        elif rule['type']=='ma':
            if len(history)<rule['slow']: target=0; reason='均线预热数据不足'
            else:
                fast=sum(r['close'] for r in history[-rule['fast']:])/rule['fast']
                slow=sum(r['close'] for r in history[-rule['slow']:])/rule['slow']
                target=rule['target_pct'] if fast>slow else 0; reason='快均线高于慢均线' if target else '快均线不高于慢均线'
        elif rule['type']=='conditional':
            buy=evaluate(rule['buy'],indicators)
            sell=evaluate(rule['sell'],indicators)
            if old>0 and sell is True:
                target=0; reason='可执行卖出条件成立'
            elif old==0 and buy is True:
                target=rule['target_pct']; reason='可执行买入条件成立'
            elif buy is None or sell is None:
                reason='部分条件指标未预热或字段未知，保持上次目标'
        else:
            raise ValueError('不支持的策略规则类型：'+str(rule['type']))
        if old>0 and rule.get('stop_loss_pct') and state['entry'] and bar['close']<=state['entry']*(1-rule['stop_loss_pct']/100):
            interval='5分钟K线' if 'trading_day' in bar else '日线'
            target=0; reason=f'{interval}收盘止损（基于策略入场信号收盘价）'
        if old==0 and target>0: state['entry']=bar['close']
        if target==0: state['entry']=None
        state['target']=target
        components.append(dict(item_id=item['id'],name=item['name'],target_pct=target,
                               effective_weight=item['effective_weight'],reason=reason,rule_type=rule['type']))
        if rule['type']=='conditional':
            components[-1]['condition_results']={'buy':buy,'sell':sell}
    conflict=len({round(i['target_pct'],8) for i in components})>1
    blocked=conflict and portfolio['conflict_policy']=='block'
    target=None if blocked else sum(i['target_pct']*i['effective_weight']/100 for i in components)
    blocked_intent='本次意图' if 'trading_day' in bar else '本日意图'
    return dict(date=bar['date'],target_pct=target,conflict=conflict,
                reasons=([f'策略目标分歧，按所选冲突规则阻止{blocked_intent}'] if blocked else []),components=components)


def refresh_sellable(ledger, bar):
    trading_day = bar.get('trading_day', bar['date'])
    previous_day = ledger.get('_sellable_trading_day')
    if previous_day is None:
        # Existing ledgers may only carry a cursor in their bar history.
        history = ledger.get('_history')
        previous_day = history[-1].get('trading_day', history[-1]['date']) if history else trading_day
    if trading_day > previous_day:
        for position in ledger['positions']:
            position['available_quantity'] = position['quantity']
    ledger['_sellable_trading_day'] = max(trading_day, previous_day)


def execute(ledger, bar, pending, costs, symbol):
    if pending is None or pending['target_pct'] is None: return
    refresh_sellable(ledger,bar)
    position=ledger['positions'][0] if ledger['positions'] else None
    quantity=position['quantity'] if position else 0
    available=position['available_quantity'] if position else 0
    equity=ledger['cash']+quantity*bar['open']
    desired=int((equity*pending['target_pct']/100)/bar['open']/100)*100
    difference=desired-quantity
    if difference==0: return
    side='buy' if difference>0 else 'sell'
    price=money(bar['open']*(1+costs['slippage_bps']/10000*(1 if side=='buy' else -1)))
    qty=abs(difference); reason=''
    if bar['suspended'] or bar['volume']==0: reason='停牌或零成交量，无法撮合'
    elif bar['open']>=bar['limit_up']-.005 or bar['open']<=bar['limit_down']+.005: reason='开盘触及涨跌停，保守拒单'
    elif price>bar['limit_up'] or price<bar['limit_down'] or price>bar['high'] or price<bar['low']:
        reason='滑点成交价超出行情可交易价格范围' if 'trading_day' in bar else '滑点成交价超出当日可交易价格范围'
    if side=='buy':
        # Upper bound includes half a cent: the actual fee is rounded, so the
        # algebraic unrounded fee must not discard an otherwise affordable lot.
        affordable=min(max(0,ledger['cash']+.005-costs['min_commission'])/price,
                       (ledger['cash']+.005)/(price*(1+costs['commission_bps']/10000)))
        qty=min(qty,int(affordable/100)*100)
        while qty>0 and qty*price+fee(qty,price,side,costs)>ledger['cash']+.000001: qty-=100
        if qty==0 and not reason: reason='现金不足以购买一手及费用'
    else:
        qty=min(qty,available)
        if qty==0 and not reason: reason='无可卖持仓或受T+1限制'
    if qty>bar['volume'] and not reason:
        reason='订单数量超过行情成交量，保守拒单' if 'trading_day' in bar else '订单数量超过日成交量，保守拒单'
    charges=fee(qty,price,side,costs) if qty>0 else 0
    if side=='sell' and qty*price-charges+ledger['cash']<0 and not reason: reason='卖出所得不足支付费用'
    execution_time=bar.get('execution_time',bar['date'])
    order=dict(id=f"{pending['date']}:{execution_time}:{side}",signal_date=pending['date'],date=execution_time,symbol=symbol,
               side=side,quantity=qty,price=price,status='rejected' if reason else 'filled',reason=reason,fee=0 if reason else charges)
    ledger['orders'].append(order)
    if reason: return
    ledger['fills'].append({k:order[k] for k in ('signal_date','date','symbol','side','quantity','price','fee')} | {'order_id':order['id']})
    if side=='buy':
        average=((position['average_cost']*quantity if position else 0)+qty*price+charges)/(quantity+qty)
        ledger['cash']=money(ledger['cash']-qty*price-charges)
        ledger['positions']=[dict(symbol=symbol,quantity=quantity+qty,available_quantity=available,average_cost=round(average,6))]
    else:
        ledger['cash']=money(ledger['cash']+qty*price-charges)
        if quantity==qty: ledger['positions']=[]
        else: position.update(quantity=quantity-qty,available_quantity=available-qty)


def mark_equity(ledger, bar, initial_cash):
    equity = ledger['equity']
    if equity and bar['date'] < equity[-1]['date']:
        return

    peak = ledger.get('_equity_peak')
    if peak is None:
        # Restore the running totals once when loading a preexisting ledger.
        peak = initial_cash
        drawdown = 0
        for point in equity:
            peak = max(peak, point['equity'])
            drawdown = max(drawdown, (peak - point['equity']) / peak * 100)
        previous_fees = 0
        previous_fill_count = 0
    else:
        metrics = ledger['metrics']
        drawdown = metrics['max_drawdown_pct']
        previous_fees = metrics['fees']
        previous_fill_count = metrics['trade_count']

    market_value = sum(position['quantity'] * bar['close'] for position in ledger['positions'])
    current_equity = money(ledger['cash'] + market_value)
    equity.append(dict(date=bar['date'], cash=ledger['cash'], market_value=money(market_value), equity=current_equity))
    peak = max(peak, current_equity)
    ledger['_equity_peak'] = peak
    fills = ledger['fills']
    ledger['metrics'] = dict(
        total_return_pct=round((current_equity / initial_cash - 1) * 100, 6),
        max_drawdown_pct=round(max(drawdown, (peak - current_equity) / peak * 100), 6),
        fees=money(previous_fees + sum(fill['fee'] for fill in fills[previous_fill_count:])),
        trade_count=len(fills),
    )


def advance(ledger, portfolio, bar, costs, symbol, initial_cash, trade=True, execute_pending=True):
    if ledger['_history'] and bar['date']<=ledger['_history'][-1]['date']:
        raise ValueError('行情日期必须晚于已处理游标')
    refresh_sellable(ledger,bar)
    if trade and execute_pending: execute(ledger,bar,ledger['_pending'],costs,symbol)
    ledger['_history'].append(deepcopy(bar))
    current=signal(ledger,portfolio,bar)
    ledger['signals'].append(current); ledger['_pending']=current
    if trade: mark_equity(ledger,bar,initial_cash)


def public(value):
    return {k:v for k,v in value.items() if not k.startswith('_')}
