"""Fetch public CSI300 snapshot and raw/qfq bars, validate, optionally import.

No account, broker, strategy edits or service lifecycle operations. Cached raw
responses make retries resumable; validation and import work entirely offline.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.trading.history import load_bundle, import_bundle, read_prices


def utc(): return datetime.now(timezone.utc).isoformat()


def write_json(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,sort_keys=True).encode()
    temp=path.with_suffix(path.suffix+'.part'); temp.write_bytes(raw); temp.replace(path)


def fetch(folder,name,url,params,json_response=True):
    path=folder/name; path.parent.mkdir(parents=True,exist_ok=True)
    meta_path=path.with_suffix(path.suffix+'.meta.json')
    if path.exists() and meta_path.exists():
        meta=json.loads(meta_path.read_text(encoding='utf-8'))
        if meta['url']==url and meta['params']==params and hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256']:
            raw=path.read_bytes()
            return (json.loads(raw) if json_response else raw),meta
    failures=[]
    for attempt in range(3):
        try:
            request=Request(url+'?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0 (local historical research)'})
            with urlopen(request,timeout=20) as response:
                raw=response.read(8_000_001)
                if len(raw)>8_000_000: raise ValueError('response too large')
            payload=json.loads(raw) if json_response else raw
            meta=dict(url=url,params=params,fetched_at=utc(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),attempt_errors=failures)
            temp=path.with_suffix('.part'); temp.write_bytes(raw); temp.replace(path); write_json(meta_path,meta)
            return payload,meta
        except Exception as exc:
            failures.append(dict(at=utc(),attempt=attempt+1,error=f'{type(exc).__name__}: {exc}'))
            if attempt<2: time.sleep(1+attempt)
    write_json(path.with_suffix('.failure.json'),dict(url=url,params=params,attempts=failures))
    raise ValueError(f'{name}: {failures[-1]["error"]}')


def ranges(start,end):
    last=date.fromisoformat(end)-timedelta(days=1)
    # At most two years (~490 observations), well below Tencent's 640-row cap.
    first=date.fromisoformat(start); chunks=[]
    year=first.year
    while year<=last.year:
        begin=max(first,date(year,1,1)) if not chunks else max(first,date(year-1,12,1))
        finish=min(last,date(year+1,12,31))
        chunks.append((begin.isoformat(),finish.isoformat()))
        year+=2
    return chunks


def normalize_csi_rows(rows):
    members=[]; dates=set()
    for row in rows:
        stamp=str(row[0]); code=str(row[4]).zfill(6)
        dates.add(datetime.strptime(stamp,'%Y%m%d').date().isoformat())
        if str(row[1]).zfill(6)!='000300': raise ValueError('Official table is not CSI300')
        if row[8]=='Shanghai Stock Exchange': market='SH'
        elif row[8]=='Shenzhen Stock Exchange': market='SZ'
        else: raise ValueError('Unsupported exchange in CSI table')
        members.append(dict(symbol=code+'.'+market,name=str(row[5])))
    if len(members)!=300 or len({m['symbol'] for m in members})!=300 or len(dates)!=1:
        raise ValueError('Official table must have 300 unique members and one as-of date')
    return sorted(members,key=lambda m:m['symbol']),dates.pop()


def download(folder,start,end,workers,limit,csi_file=None,retry_failed=False):
    folder.mkdir(parents=True,exist_ok=True)
    previous=None
    if (folder/'manifest.json').exists():
        previous=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if previous['requested_start_date']!=start or previous['requested_end_date_exclusive']!=end:
            raise ValueError('Use a new output directory for a different requested window')
    files={}
    url='https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000300cons.xls'
    name='universe/csi-000300.xls'
    if csi_file:
        raw=Path(csi_file).read_bytes(); path=folder/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
        meta=dict(url=url,params={},fetched_at=datetime.fromtimestamp(Path(csi_file).stat().st_mtime,timezone.utc).isoformat(),
                  sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),provided_public_file=True)
        write_json(path.with_suffix(path.suffix+'.meta.json'),meta)
    else:
        raw,meta=fetch(folder,name,url,{},json_response=False)
    import xlrd
    sheet=xlrd.open_workbook(file_contents=raw).sheet_by_index(0)
    members,as_of=normalize_csi_rows([sheet.row_values(i) for i in range(1,sheet.nrows)])
    files[name]=meta
    member_path=folder/'universe/members.json'; write_json(member_path,members)
    universe_fetched_at=meta['fetched_at']
    files['universe/members.json']=dict(sha256=hashlib.sha256(member_path.read_bytes()).hexdigest(),fetched_at=universe_fetched_at,
        url=url,params={'derived_from':[name]})
    fetched_at=universe_fetched_at
    manifest=dict(schema_version=1,provider='Tencent public daily + CSI official constituents',fetched_at=fetched_at,
        requested_start_date=start,requested_end_date_exclusive=end,universe_file='universe/members.json',
        universe=dict(name='沪深300',as_of_date=as_of,source='中证指数官方000300cons.xls',survivorship_bias=True,
                      date_semantics='官方表内日期的单时点成分，非回测期间每日历史成分'),files=files,calendar_files=[],securities=[],failures=[])
    endpoint='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    chunks=ranges(start,end)
    for index,(begin,finish) in enumerate(chunks):
        name=f'calendar/sh000300-{index}.json'
        payload,meta=fetch(folder,name,endpoint,{'param':f'sh000300,day,{begin},{finish},640,'})
        if not read_prices(payload,'sh000300',False): raise ValueError('Empty index calendar segment')
        files[name]=meta; manifest['calendar_files'].append(name)
    if retry_failed:
        if not previous or previous['universe']!=manifest['universe']: raise ValueError('Retry requires the same official universe')
        manifest['securities']=previous['securities']
        current_files=dict(files)
        manifest['files'].update(previous['files'])
        manifest['files'].update(current_files)
    manifest['fetched_at']=max(info['fetched_at'] for info in files.values())
    write_json(folder/'manifest.json',manifest)
    def security(member):
        symbol=member['symbol']; code=symbol[-2:].lower()+symbol[:6]
        result={**member,'raw_files':[],'adjusted_files':[]}; local_files={}
        try:
            for adjust in ('','qfq'):
                for index,(begin,finish) in enumerate(chunks):
                    name=f'{"bars-current" if retry_failed else "bars"}/{code}-{adjust or "raw"}-{index}.json'
                    request_endpoint='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get' if retry_failed else endpoint
                    payload,meta=fetch(folder,name,request_endpoint,{'param':f'{code},day,{begin},{finish},640,{adjust}'})
                    read_prices(payload,code,bool(adjust))
                    local_files[name]=meta; result['adjusted_files' if adjust else 'raw_files'].append(name)
                    time.sleep(.05)
            return result,local_files,None
        except Exception as exc:
            return result,local_files,dict(symbol=symbol,error=str(exc))
    selected=members[:limit] if limit else members
    if retry_failed:
        succeeded={s['symbol'] for s in manifest['securities']}
        selected=[m for m in selected if m['symbol'] not in succeeded]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks=[pool.submit(security,m) for m in selected]
        for count,task in enumerate(as_completed(tasks),1):
            result,local,error=task.result(); files.update(local)
            manifest['fetched_at']=max(info['fetched_at'] for info in files.values())
            if error: manifest['failures'].append(error)
            else: manifest['securities'].append(result)
            manifest['securities'].sort(key=lambda s:s['symbol'])
            write_json(folder/'manifest.json',manifest)
            if count%10==0 or count==len(selected) or error:
                print(json.dumps(dict(completed=count,total=len(selected),failed=len(manifest['failures']),symbol=result['symbol']),ensure_ascii=False),flush=True)
    return manifest


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data/history/hs300-20240101-20261101')
    parser.add_argument('--start',default='2024-01-01'); parser.add_argument('--end-exclusive',default='2026-11-01')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=4)
    parser.add_argument('--limit',type=int,default=0,help='Probe only; still reports all missing pool members')
    parser.add_argument('--csi-file',type=Path,help='Previously downloaded official 000300cons.xls, retaining source file mtime as retrieval time')
    parser.add_argument('--retry-failed',action='store_true',help='Retry missing constituents using the current public Tencent endpoint documented by AKShare')
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--import-data-dir',type=Path,help='Explicit target; inserts dataset only, never invokes store.init')
    args=parser.parse_args()
    if not args.validate_only: download(args.output,args.start,args.end_exclusive,args.workers,args.limit,args.csi_file,args.retry_failed)
    dataset,report=load_bundle(args.output)
    write_json(args.output/'integrity-report.json',report)
    from app.trading.datasets import summary
    write_json(args.output/'dataset-summary.json',summary(dataset))
    if args.import_data_dir:
        imported=import_bundle(args.output,args.import_data_dir)
        write_json(args.output/'import-result.json',dict(dataset_id=imported['id'],dataset_hash=imported['hash'],imported_at=utc()))
    print(json.dumps(dict(dataset_id=dataset['id'],row_count=dataset['row_count'],start=dataset['start_date'],end=dataset['end_date'],
        successful_symbols=dataset['coverage']['successful_symbols'],failed_symbols=len(dataset['coverage']['failed_symbols']),
        status=dataset['coverage']['status']),ensure_ascii=False),flush=True)

if __name__=='__main__': main()
