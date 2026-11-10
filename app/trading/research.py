"""Adjusted-price research ledger. Synthetic units, never executable stock orders."""
from copy import deepcopy
from math import floor
from app.trading import engine

LIMITATIONS = [
    '复权研究回测：价格为供应商前复权序列，数量为可分割虚拟份额，不是实际成交价格或股票股数',
    '初始资金、现金、净值为研究计价单位；分红送转只经复权序列反映，不另计股息现金或新增股数',
    '沿用所选策略，收盘信号下一根开盘调仓；阈值参数须按本数据的复权价格尺度配置',
    '未模拟官方涨跌停、盘口、整手、公司行为现金流；费用和滑点为用户假设，结果不可视为可成交收益',
    '前复权基准可能含回测时点之后的公司行为、事后修订，存在未来信息局限；当前成分股存在存活偏差',
    '停牌/零量和缺失交易日后的首根不执行调仓，不补造价格；只允许历史研究，禁止模拟跟盘',
    '均线按实际可用日线根数预热和计算，缺失日期不补入均线；前复权收益不是精确的实际股息再投资现金流',
]


def execute(ledger, bar, pending, costs, symbol):
    if pending is None or pending['target_pct'] is None:
        return
    position=ledger['positions'][0] if ledger['positions'] else None
    quantity=position['quantity'] if position else 0
    equity=ledger['cash']+quantity*bar['open']
    desired=floor(equity*pending['target_pct']/100/bar['open']*1e8)/1e8
    delta=desired-quantity
    if abs(delta)*bar['open']<.01:
        return
    side='buy' if delta>0 else 'sell'
    price=bar['open']*(1+costs['slippage_bps']/10000*(1 if side=='buy' else -1))
    qty=abs(delta); reason=''
    if bar.get('gap_before'): reason='存在缺失交易日，禁止跨缺口执行旧信号'
    elif bar['suspended'] or bar['volume']==0: reason='停牌或零成交量，研究账户不调仓'
    elif price>bar['high']+1e-8 or price<bar['low']-1e-8: reason='假设滑点价超出复权日线范围'
    if side=='buy':
        affordable=min(max(0,ledger['cash']-costs['min_commission'])/price,
                       ledger['cash']/(price*(1+costs['commission_bps']/10000)))
        qty=floor(min(qty,affordable)*1e8)/1e8
        charges=engine.fee(qty,price,side,costs)
        # Rounded fees may exceed the algebraic bound by less than half a cent.
        if qty*price+charges>ledger['cash']:
            qty=floor(max(0,(ledger['cash']-charges)/price)*1e8)/1e8
        if qty<=0 and not reason: reason='研究现金不足支付调仓和费用'
    else:
        qty=min(qty,quantity)
    charges=engine.fee(qty,price,side,costs) if qty>0 else 0
    if side=='sell' and ledger['cash']+qty*price-charges<0 and not reason:
        reason='卖出所得不足支付假设费用'
    order=dict(id=f"{pending['date']}:{bar['date']}:{side}",signal_date=pending['date'],date=bar['date'],
               symbol=symbol,side=side,quantity=round(qty,8),price=price,status='rejected' if reason else 'filled',
               reason=reason,fee=0 if reason else charges,execution_model='adjusted_research',quantity_unit='synthetic_unit')
    ledger['orders'].append(order)
    if reason: return
    ledger['fills'].append({k:order[k] for k in ('signal_date','date','symbol','side','quantity','price','fee','execution_model','quantity_unit')} | {'order_id':order['id']})
    if side=='buy':
        total=quantity+qty
        average=((position['average_cost']*quantity if position else 0)+qty*price+charges)/total
        ledger['cash']=engine.money(ledger['cash']-qty*price-charges)
        ledger['positions']=[dict(symbol=symbol,quantity=round(total,8),available_quantity=round(total,8),average_cost=average,quantity_unit='synthetic_unit')]
    else:
        ledger['cash']=engine.money(ledger['cash']+qty*price-charges)
        remaining=round(quantity-qty,8)
        if remaining<=0: ledger['positions']=[]
        else: position.update(quantity=remaining,available_quantity=remaining)


def advance(ledger,portfolio,bar,costs,symbol,initial_cash):
    if ledger['_history'] and bar['date']<=ledger['_history'][-1]['date']:
        raise ValueError('研究行情日期必须递增')
    execute(ledger,bar,ledger['_pending'],costs,symbol)
    ledger['_history'].append(deepcopy(bar))
    current=engine.signal(ledger,portfolio,bar)
    ledger['signals'].append(current); ledger['_pending']=current
    market_value=sum(p['quantity']*bar['close'] for p in ledger['positions'])
    point=dict(date=bar['date'],cash=ledger['cash'],market_value=engine.money(market_value),equity=engine.money(ledger['cash']+market_value))
    ledger['equity'].append(point)
    peak=max(initial_cash,ledger.get('_research_peak',initial_cash),point['equity'])
    ledger['_research_peak']=peak
    drawdown=max(ledger['metrics']['max_drawdown_pct'],(peak-point['equity'])/peak*100)
    ledger['metrics']=dict(total_return_pct=round((point['equity']/initial_cash-1)*100,6),
                           max_drawdown_pct=round(drawdown,6),fees=engine.money(sum(f['fee'] for f in ledger['fills'])),trade_count=len(ledger['fills']))
