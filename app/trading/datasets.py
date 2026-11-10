import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timedelta, timezone, date
from fastapi import HTTPException
from app.trading.store import identity

CN_TZ = timezone(timedelta(hours=8))
COLUMNS = ['date','symbol','open','high','low','close','volume','prev_close','limit_up','limit_down','suspended']
LIMITATIONS = ['仅沪深主板普通股票日线、单标的、只做多；不支持ST、上市初期、复权成交价及公司行为',
               '日线收盘产生信号，下一根开盘本地撮合；非盘中实时、非券商回报',
               '停牌、零量、开盘触及任一限价保守拒单；不模拟盘口与排队',
               '费用为用户可调假设；未建完整历史税费表、财报PIT和交易日历']


def completed_date():
    current=datetime.now(CN_TZ)
    # Daily providers may finalize between 15:00 and 17:00; conservatively wait until 18:00.
    return current.date() if current.hour >= 18 else current.date()-timedelta(days=1)


def number(value, name, zero=False):
    try: value=float(value)
    except (TypeError,ValueError): raise ValueError(name+'必须是数字') from None
    if not math.isfinite(value) or value < 0 or (not zero and value==0): raise ValueError(name+'必须为有限正数（成交量可为零）')
    if (not zero and (value<0.01 or value>10000000)) or (zero and value>1e12):
        raise ValueError(name+'超出本执行器支持的价格/成交量范围')
    return value


def parse_rows(text, is_demo=False):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    required=set(COLUMNS[:-1])
    if not required.issubset(set(reader.fieldnames or [])): raise ValueError('CSV缺少必填列：'+','.join(sorted(required-set(reader.fieldnames or []))))
    rows=[]; last_key=None; previous={}
    for raw in reader:
        if len(rows)>=10000: raise ValueError('最多10000行')
        if None in raw: raise ValueError('CSV列数不一致')
        try:
            day=date.fromisoformat(raw['date'])
            if day.isoformat()!=raw['date'] or day>completed_date(): raise ValueError('日期必须为已完成日线，不能是未来或今日未收盘数据')
            if day.weekday()>=5: raise ValueError('不支持周末交易日')
            symbol=raw['symbol'].strip().upper()
            if not re.fullmatch(r'(60[0135]\d{3}\.SH|00[0123]\d{3}\.SZ)',symbol): raise ValueError('仅支持沪深主板普通股票代码')
            key=(raw['date'],symbol)
            if last_key and key<=last_key: raise ValueError('CSV须按date,symbol升序且不得重复')
            row={'date':raw['date'],'symbol':symbol}
            for field in COLUMNS[2:-1]: row[field]=number(raw[field],field,field=='volume')
            suspended=(raw.get('suspended') or '0').strip()
            if suspended not in ('0','1'): raise ValueError('suspended必须为0或1')
            row['suspended']=suspended=='1'
            if not row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']: raise ValueError('OHLC关系不合法')
            if not row['limit_down']<row['prev_close']<row['limit_up']: raise ValueError('每日限价不合法')
            if abs(row['limit_up']-round(row['prev_close']*1.1,2))>0.021 or abs(row['limit_down']-round(row['prev_close']*.9,2))>0.021:
                raise ValueError('限价不属于普通主板10%范围，请核实ST/新股等超范围证券')
            if row['high']>row['limit_up']+0.011 or row['low']<row['limit_down']-0.011: raise ValueError('OHLC超出官方每日限价')
            if symbol in previous and abs(previous[symbol]-row['prev_close'])>0.011: raise ValueError('昨收与上一根收盘不一致，存在公司行为/缺失交易日，不能直接撮合')
            previous[symbol]=row['close']; last_key=key; rows.append(row)
        except (ValueError,TypeError) as exc: raise ValueError(f'CSV第{len(rows)+2}行：{exc}') from None
    if not rows: raise ValueError('CSV无数据')
    return rows


def build_dataset(body):
    if not body.ordinary_stock_confirmed or not body.corporate_actions_confirmed_absent:
        raise HTTPException(400,'需确认普通主板股票范围且数据无公司行为；否则无法安全撮合')
    try: rows=parse_rows(body.csv_text,body.is_demo)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    value={**identity(),'name':body.name,'source':body.source,'market':body.market,'price_basis':body.price_basis,
           'is_demo':body.is_demo,'version':1,'rows':rows,'row_count':len(rows),
           'start_date':rows[0]['date'],'end_date':rows[-1]['date'],'symbols':sorted({r['symbol'] for r in rows}),
           'warnings':(['演示合成数据，不是实际行情'] if body.is_demo else [])+LIMITATIONS}
    value['hash']=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value


def demo_input():
    from app.trading.models import DatasetInput
    out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=COLUMNS); writer.writeheader()
    day=date(2026,1,5); previous=10.0
    for n in range(80):
        while day.weekday()>=5: day+=timedelta(days=1)
        close=round(10+1.25*math.sin(n/6),2)
        opening=previous
        writer.writerow(dict(date=day.isoformat(),symbol='600000.SH',open=opening,high=round(max(opening,close)+.05,2),
                             low=round(min(opening,close)-.05,2),close=close,volume=1000000,prev_close=previous,
                             limit_up=round(previous*1.1,2),limit_down=round(previous*.9,2),suspended=0))
        previous=close; day+=timedelta(days=1)
    return DatasetInput(name='日线演示数据',source='本地确定性合成，仅用于演示',csv_text=out.getvalue(),is_demo=True,
                        ordinary_stock_confirmed=True,corporate_actions_confirmed_absent=True)


def summary(dataset):
    value={k:v for k,v in dataset.items() if k!='rows'}
    value.setdefault('dataset_type','strict_daily')
    value.setdefault('allowed_modes',['backtest','replay','incremental'] if not dataset['is_demo'] else ['backtest','replay'])
    return value
