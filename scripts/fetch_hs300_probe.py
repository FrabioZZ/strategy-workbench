"""Small, bounded, anonymous BaoStock connectivity probe; no production DB writes."""
import json
import socket
from pathlib import Path
from datetime import datetime, timezone

socket.setdefaulttimeout(15)
import baostock as bs


def main():
    folder=Path(__file__).resolve().parents[1]/'data/history/probe'
    folder.mkdir(parents=True,exist_ok=True)
    def save(name,result,params):
        rows=[]
        while result.error_code=='0' and result.next(): rows.append(result.get_row_data())
        value=dict(fetched_at=datetime.now(timezone.utc).isoformat(),params=params,error_code=result.error_code,
                   error_msg=result.error_msg,fields=result.fields,rows=rows)
        (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,result.error_code,len(rows),rows[:1],rows[-1:],flush=True)
    result=bs.login()
    (folder/'login.json').write_text(json.dumps(dict(fetched_at=datetime.now(timezone.utc).isoformat(),
        error_code=result.error_code,error_msg=result.error_msg)),encoding='utf-8')
    print('login',result.error_code,flush=True)
    if result.error_code!='0': return 1
    try:
        params=dict(code='sh.600000',fields='date,code,open,high,low,close,preclose,volume,amount,adjustflag,tradestatus,isST',
                    start_date='2024-01-01',end_date='2026-10-31',frequency='d',adjustflag='3')
        save('raw_sample',bs.query_history_k_data_plus(**params),params)
        save('members',bs.query_hs300_stocks(date='2026-10-30'),{'date':'2026-10-30'})
        save('calendar',bs.query_trade_dates(start_date='2024-01-01',end_date='2026-10-31'),{'start_date':'2024-01-01','end_date':'2026-10-31'})
    finally: bs.logout()
    return 0

if __name__=='__main__': raise SystemExit(main())
