"""Causal daily indicators. Cached prefixes contain no future or cross-symbol data.

The registry is the validation/API source of truth. Initialization conventions
are explicit; this is not a promise of bitwise parity with a vendor terminal.
"""
from copy import deepcopy
import json
import math


def period(default=14, minimum=1):
    return dict(type='integer', default=default, minimum=minimum, maximum=250)


REGISTRY = {}


def register(name, label, params=None, warmup='1', formula='', raw_only=False):
    REGISTRY[name] = dict(name=name, label=label, params=params or {}, warmup=warmup,
                          formula=formula, raw_only=raw_only, frequency='daily')


for name, label in [('OPEN','开盘价'),('HIGH','最高价'),('LOW','最低价'),('CLOSE','收盘价'),
                    ('VOLUME','成交量（股）'),('PREV_CLOSE','昨收价')]:
    register(name,label,formula='当前已完成日线字段 '+name.lower())
REGISTRY['PREV_CLOSE']['formula']='优先使用数据昨收；复权研究字段缺失时使用无缺口的前一根收盘；首根/缺口后未知'

for name,label in [('MA','简单移动平均'),('EMA','指数移动平均')]:
    register(name,label,{'period':period(20), 'field':dict(type='string',default='close',
        enum=['open','high','low','close','volume'])},'period',
        'N根均值' if name=='MA' else '以首N根均值初始化，alpha=2/(N+1)，之后递归平滑')

for suffix,label in [('DIF','快慢EMA差'),('DEA','DIF信号线'),('HIST','双倍MACD柱')]:
    register('MACD_'+suffix,label,{'fast':period(12),'slow':period(26,2),'signal':period(9)},
        'slow' if suffix=='DIF' else 'slow+signal-1',
        'DIF=EMA(fast)-EMA(slow)；DEA以首signal个DIF均值初始化后EMA；HIST=2*(DIF-DEA)')

for suffix,label in [('K','K值'),('D','D值'),('J','J值')]:
    register('KDJ_'+suffix,label,{'period':period(9),'k_period':period(3),'d_period':period(3)},'period',
        'RSV=100*(close-LLV)/(HHV-LLV)；平坦区间RSV=50；K/D初值50，按1/k_period和1/d_period平滑；J=3K-2D')

for suffix,label in [('MID','布林中轨'),('UPPER','布林上轨'),('LOWER','布林下轨')]:
    register('BOLL_'+suffix,label,{'period':period(20,2),'stddev':dict(type='number',default=2,minimum=.1,maximum=10)},
        'period','中轨=N根收盘均值，上下轨=均值±stddev*总体标准差(ddof=0)')

register('RSI','相对强弱指标',{'period':period(14)},'period+1',
         '首N个收盘差的涨/跌均值初始化，后按Wilder 1/N平滑；100*平均涨/(平均涨+平均跌)，均为0时50')
register('ATR','平均真实波幅',{'period':period(14)},'period',
         'TR=max(high-low,abs(high-prev_close),abs(low-prev_close))；首根无昨收用high-low；首N个TR均值后Wilder平滑；缺口后昨收未知则重新预热')
register('CCI','顺势指标',{'period':period(14,2)},'period',
         'TP=(H+L+C)/3；(TP-N根TP均值)/(0.015*N根TP平均绝对偏差)，零偏差时0')
register('WR','威廉指标（-100至0）',{'period':period(14)},'period',
         '-100*(HHV-close)/(HHV-LLV)；平坦区间为-50')
register('OBV','能量潮',formula='首根为成交量；后续按收盘涨跌加减当日量，平盘不变；绝对值依赖历史起点')
register('VOLUME_RATIO','日成交量/此前均量',{'period':period(5)},'period+1',
         '当日成交量/此前N根成交量均值（不含当日）；分母0时未知；不是盘中盘口量比')
register('CHANGE_PCT','日涨跌幅（%）',formula='100*(close/prev_close-1)')
register('GAP_PCT','开盘缺口（%）',formula='100*(open/prev_close-1)，收盘信号模型中仅收盘后可用于决策')
register('AMPLITUDE_PCT','日振幅（%）',formula='100*(high-low)/prev_close')
for name,label in [('LIMIT_UP','当日涨停价'),('LIMIT_DOWN','当日跌停价'),
                    ('IS_LIMIT_UP','收盘涨停'),('IS_LIMIT_DOWN','收盘跌停'),
                    ('LIMIT_UP_STREAK','连续收盘涨停数'),('FIRST_LIMIT_UP','首个收盘涨停')]:
    register(name,label,warmup='需要实际限价；首板/连板需要已知前序非涨停日',raw_only=True,
        formula='使用导入的实际涨跌停价格，价差<=0.005；停牌/零量不算封板；未知历史不可断言首板/板数')


def registry():
    return deepcopy(list(REGISTRY.values()))


def normalize_params(name, params=None):
    if name not in REGISTRY:
        raise ValueError('不支持的指标：'+str(name))
    params=params or {}
    definitions=REGISTRY[name]['params']
    if set(params)-set(definitions):
        raise ValueError(name+'含不支持的参数：'+','.join(sorted(set(params)-set(definitions))))
    result={}
    for key, spec in definitions.items():
        value=params.get(key,spec['default'])
        if spec['type']=='string':
            if value not in spec['enum']: raise ValueError(name+'.'+key+'取值无效')
        else:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(name+'.'+key+'必须是有限数字')
            if spec['type']=='integer' and (not isinstance(value,int)):
                raise ValueError(name+'.'+key+'必须是整数')
            if not spec['minimum']<=value<=spec['maximum']:
                raise ValueError(name+'.'+key+'超出范围')
        result[key]=value
    if name.startswith('MACD_') and result['fast']>=result['slow']:
        raise ValueError('MACD慢周期必须大于快周期')
    return result


class IndicatorEngine:
    def __init__(self, rows, cache=None):
        self.rows=rows
        self.cache=cache if cache is not None else {}

    def series(self, name, params=None):
        p=normalize_params(name,params)
        key=json.dumps([name,p],sort_keys=True,separators=(',',':'))
        entry=self.cache.setdefault(key,{'values':[], 'state':{}})
        values=entry['values']
        for i in range(len(values),len(self.rows)):
            value=self._calculate(name,p,i,values,entry['state'])
            values.append(value if value is None or math.isfinite(value) else None)
        return values

    def value(self,name,params=None,index=None):
        index=len(self.rows)-1 if index is None else index
        if index<0 or index>=len(self.rows): return None
        return self.series(name,params)[index]

    def previous_close(self,i):
        row=self.rows[i]
        if row.get('prev_close') is not None: return row['prev_close']
        return self.rows[i-1]['close'] if i and not row.get('gap_before',False) else None

    def _calculate(self,name,p,i,values,state):
        row=self.rows[i]; n=p.get('period',1)
        if name=='PREV_CLOSE': return self.previous_close(i)
        if name in ('OPEN','HIGH','LOW','CLOSE','VOLUME','LIMIT_UP','LIMIT_DOWN'):
            return row.get(name.lower())
        if name in ('CHANGE_PCT','GAP_PCT','AMPLITUDE_PCT'):
            previous=self.previous_close(i)
            if not previous: return None
            if name=='AMPLITUDE_PCT': return 100*(row['high']-row['low'])/previous
            return 100*(row['close' if name=='CHANGE_PCT' else 'open']/previous-1)
        if name.startswith('IS_LIMIT_'):
            limit=row.get('limit_up' if name=='IS_LIMIT_UP' else 'limit_down')
            if limit is None: return None
            return int(not row.get('suspended',False) and row['volume']>0 and abs(row['close']-limit)<=.005+1e-10)
        if name in ('LIMIT_UP_STREAK','FIRST_LIMIT_UP'):
            up=self.value('IS_LIMIT_UP',index=i)
            if up is None: return None
            if not up: return 0
            if name=='FIRST_LIMIT_UP':
                count=self.value('LIMIT_UP_STREAK',index=i)
                return None if count is None else int(count==1)
            return None if i==0 or values[i-1] is None else values[i-1]+1
        if name=='OBV':
            if not i: return row['volume']
            change=row['close']-self.rows[i-1]['close']
            return values[i-1]+(row['volume'] if change>0 else -row['volume'] if change<0 else 0)
        if name=='VOLUME_RATIO':
            if i<n: return None
            avg=sum(r['volume'] for r in self.rows[i-n:i])/n
            return row['volume']/avg if avg else None
        if name.startswith('MACD_'):
            fast,slow,smoothing=p['fast'],p['slow'],p['signal']
            if name=='MACD_DIF':
                f=self.value('EMA',{'period':fast},i); s=self.value('EMA',{'period':slow},i)
                return None if f is None or s is None else f-s
            dif=self.series('MACD_DIF',p)
            if name=='MACD_DEA':
                first=slow+smoothing-2
                if i<first: return None
                if i==first: return sum(dif[slow-1:i+1])/smoothing
                return values[i-1]+2/(smoothing+1)*(dif[i]-values[i-1])
            dea=self.value('MACD_DEA',p,i)
            return None if dea is None else 2*(dif[i]-dea)
        if name=='RSI':
            if i==0: return None
            delta=row['close']-self.rows[i-1]['close']
            gain=max(0,delta); loss=max(0,-delta)
            if i<=n:
                state['gain']=state.get('gain',0)+gain/n
                state['loss']=state.get('loss',0)+loss/n
            else:
                state['gain']=(state['gain']*(n-1)+gain)/n
                state['loss']=(state['loss']*(n-1)+loss)/n
            if i<n: return None
            total=state['gain']+state['loss']
            return 100*state['gain']/total if total else 50
        if name=='ATR':
            previous=self.previous_close(i)
            if previous is None and i:
                state.clear()
                return None
            if previous is None: previous=row['close']
            tr=max(row['high']-row['low'],abs(row['high']-previous),abs(row['low']-previous))
            if state.get('count',0)<n:
                state['sum']=state.get('sum',0)+tr
                state['count']=state.get('count',0)+1
                return state['sum']/n if state['count']==n else None
            return (values[i-1]*(n-1)+tr)/n
        if i<n-1: return None
        window=self.rows[i-n+1:i+1]
        if name in ('MA','EMA'):
            if name=='MA' or i==n-1: return sum(r[p['field']] for r in window)/n
            return values[i-1]+2/(n+1)*(row[p['field']]-values[i-1])
        if name.startswith('BOLL_'):
            avg=sum(r['close'] for r in window)/n
            if name=='BOLL_MID': return avg
            std=math.sqrt(sum((r['close']-avg)**2 for r in window)/n)
            return avg+std*p['stddev']*(1 if name=='BOLL_UPPER' else -1)
        if name=='CCI':
            typical=[(r['high']+r['low']+r['close'])/3 for r in window]
            avg=sum(typical)/n; deviation=sum(abs(t-avg) for t in typical)/n
            return (typical[-1]-avg)/(.015*deviation) if deviation else 0
        high=max(r['high'] for r in window); low=min(r['low'] for r in window)
        if name=='WR': return -100*(high-row['close'])/(high-low) if high!=low else -50
        if name=='KDJ_K':
            rsv=100*(row['close']-low)/(high-low) if high!=low else 50
            previous=50 if i==n-1 else values[i-1]
            return previous+(rsv-previous)/p['k_period']
        k=self.value('KDJ_K',p,i)
        if name=='KDJ_D':
            previous=50 if i==n-1 else values[i-1]
            return previous+(k-previous)/p['d_period']
        if name=='KDJ_J': return 3*k-2*self.value('KDJ_D',p,i)
        raise ValueError('指标未实现：'+name)
