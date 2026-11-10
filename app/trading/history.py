"""Validate immutable public-history bundles and import only dataset records."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from app.trading.datasets import number, completed_date, summary
from app.trading.research import LIMITATIONS
from app.trading.store import TradingStore


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tx_code(symbol):
    return symbol[-2:].lower()+symbol[:6]


def read_prices(payload,code,adjusted):
    if payload.get('code')!=0: raise ValueError('供应商返回错误')
    item=payload.get('data',{}).get(code,{})
    # Tencent returns day when the requested adjustment makes no difference.
    values=item.get('qfqday',item.get('day',[])) if adjusted else item.get('day',[])
    if not isinstance(values,list): raise ValueError('历史数据不是数组')
    result={}; previous=None
    for value in values:
        day=date.fromisoformat(value[0])
        if day.isoformat()!=value[0] or day>completed_date() or day.weekday()>4:
            raise ValueError('历史数据日期无效或未完成')
        if previous and value[0]<=previous: raise ValueError('响应日期重复或乱序')
        opening,close,high,low=[number(v,'价格') for v in value[1:5]]
        volume=number(value[5],'成交量',zero=True)
        if not low<=min(opening,close)<=max(opening,close)<=high: raise ValueError('OHLC关系无效')
        result[value[0]]=dict(date=value[0],open=opening,high=high,low=low,close=close,volume=volume,suspended=volume==0)
        previous=value[0]
    return result


def load_bundle(folder):
    folder=Path(folder).resolve(); raw_manifest=(folder/'manifest.json').read_bytes()
    manifest=json.loads(raw_manifest)
    if manifest.get('schema_version')!=1: raise ValueError('不支持的历史包版本')
    start=manifest['requested_start_date']; end=manifest['requested_end_date_exclusive']
    if date.fromisoformat(start)>=date.fromisoformat(end): raise ValueError('请求日期范围无效')
    files={}
    for name,info in manifest['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder): raise ValueError('历史文件路径越界')
        raw=path.read_bytes()
        if digest(raw)!=info['sha256']: raise ValueError('历史文件hash校验失败：'+name)
        files[name]=raw
    members=json.loads(files[manifest['universe_file']])
    if not members or len({m['symbol'] for m in members})!=len(members): raise ValueError('股票池为空或代码重复')
    lookup={m['symbol']:m for m in members}
    for symbol in lookup:
        if not re.fullmatch(r'(6\d{5}\.SH|[03]\d{5}\.SZ)',symbol): raise ValueError('股票池含不支持代码')
    def merged(names,code,adjusted):
        result={}
        for name in names:
            for day,row in read_prices(json.loads(files[name]),code,adjusted).items():
                if day in result and row!=result[day]: raise ValueError('分段重叠行情不一致，拒绝混合复权基准')
                if start<=day<end: result[day]=row
        return dict(sorted(result.items()))
    calendar=sorted(merged(manifest['calendar_files'],'sh000300',False))
    if not calendar: raise ValueError('没有可验证的指数交易日历')
    calendar_set=set(calendar); index={d:i for i,d in enumerate(calendar)}
    rows=[]; metadata=[]; reports=[]; failures=list(manifest.get('failures',[])); seen=set()
    for security in manifest['securities']:
        symbol=security['symbol']
        if symbol not in lookup or symbol in seen: raise ValueError('证券清单与股票池不符或重复')
        seen.add(symbol)
        try:
            raw=merged(security['raw_files'],tx_code(symbol),False)
            adjusted=merged(security['adjusted_files'],tx_code(symbol),True)
            if not raw or not adjusted: raise ValueError('没有历史行情')
            if raw.keys()!=adjusted.keys(): raise ValueError('未复权与复权日期不一致')
            if set(adjusted)-calendar_set: raise ValueError('证券日期不在指数交易日历中')
            dates=sorted(adjusted); previous=None
            for day,row in adjusted.items():
                if row['volume']!=raw[day]['volume']: raise ValueError('未复权与复权成交量不一致')
            symbol_rows=[]
            for day,row in adjusted.items():
                gap=previous is not None and index[day]!=index[previous]+1
                symbol_rows.append({**row,'symbol':symbol,'gap_before':gap})
                previous=day
            missing=sorted(calendar_set-set(dates))
            item=dict(symbol=symbol,name=lookup[symbol]['name'],start_date=dates[0],end_date=dates[-1],row_count=len(dates),
                      missing_day_count=len(missing),internal_gap_count=sum(dates[0]<d<dates[-1] for d in missing),
                      missing_start=dates[0]>calendar[0],missing_tail=dates[-1]<calendar[-1])
            rows.extend(symbol_rows); metadata.append(item); reports.append({**item,'missing_dates':missing})
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            failures.append(dict(symbol=symbol,error=str(exc)))
    available={m['symbol'] for m in metadata}
    for symbol in sorted(set(lookup)-available):
        if not any(f.get('symbol')==symbol for f in failures): failures.append(dict(symbol=symbol,error='未取得完整响应文件'))
    if not rows: raise ValueError('没有有效研究行情；'+json.dumps(failures,ensure_ascii=False))
    rows.sort(key=lambda r:(r['date'],r['symbol'])); metadata.sort(key=lambda m:m['symbol'])
    missing_tail=[m['symbol'] for m in metadata if m['missing_tail']]
    partial=bool(failures or any(m['missing_day_count'] for m in metadata))
    # The index is an observed market calendar, not an official forward schedule.
    coverage=dict(status='partial' if partial else 'complete_observed_calendar',actual_start_date=rows[0]['date'],
                  actual_end_date=rows[-1]['date'],successful_symbols=len(metadata),failed_symbols=failures,
                  missing_tail_symbols=missing_tail,calendar_end_date=calendar[-1],calendar_start_date=calendar[0],
                  observed_trading_days=len(calendar),symbols_with_gaps=sum(m['missing_day_count']>0 for m in metadata),
                  calendar_source='腾讯沪深300指数实际返回日线；不是官方前瞻交易日历')
    manifest_hash=digest(raw_manifest)
    warnings=list(LIMITATIONS)+['公开接口可获取不代表获得商业使用授权；保留原始文件和来源，请按供应商条款使用',
        '股票池为单一时点快照，不能代表历史每日成分；可能含期初尚未上市股票，缺失日期不补造']
    if partial: warnings.append('数据覆盖有缺口，逐股范围/缺失日期见完整性报告；无价格填充')
    value=dict(id='history-'+manifest_hash[:24],created_at=manifest['fetched_at'],name='沪深300复权研究日线',
               source=manifest['provider'],dataset_type='research_adjusted',market='CN_A',price_basis='forward_adjusted',
               volume_unit='provider_lot',allowed_modes=['backtest'],is_demo=False,version=1,rows=rows,row_count=len(rows),
               start_date=rows[0]['date'],end_date=rows[-1]['date'],symbols=sorted(available),symbol_metadata=metadata,
               requested_start_date=start,requested_end_date_exclusive=end,expected_end_date=calendar[-1],
               universe=manifest['universe'],coverage=coverage,warnings=warnings,
               provenance=dict(provider=manifest['provider'],fetched_at=manifest['fetched_at'],manifest_hash=manifest_hash),
               hash=digest(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()))
    report=dict(manifest_hash=manifest_hash,dataset_hash=value['hash'],coverage=coverage,securities=reports,
                failures=failures,raw_files_verified=len(files),universe_count=len(members))
    return value,report


def import_bundle(folder,data_dir):
    value,report=load_bundle(folder)
    store=TradingStore(Path(data_dir)); store.folder.mkdir(parents=True,exist_ok=True)
    # Deliberately never call init(): it pauses existing paper sessions.
    with store.transaction() as c:
        c.execute('CREATE TABLE IF NOT EXISTS resources (kind TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        existing=c.execute('SELECT body FROM resources WHERE kind=? AND id=?',('dataset',value['id'])).fetchone()
        if existing:
            old=json.loads(existing['body'])
            if old['hash']!=value['hash']: raise ValueError('既有数据集hash冲突，拒绝覆盖')
            return summary(old)
        store.put(c,'dataset',value)
    return summary(value)
