"""Optional server-side Tushare adapter; no brokerage API or credentials in responses."""
import csv
import io
import os
from datetime import timedelta
import httpx
from app.trading.datasets import COLUMNS, completed_date, build_dataset
from app.trading.models import DatasetInput


def configured():
    return bool(os.getenv('TUSHARE_TOKEN','').strip())


def fetch(symbol, start_date=None, end_date=None):
    token=os.getenv('TUSHARE_TOKEN','').strip()
    if not token:
        if start_date or end_date:
            raise ValueError('缺少覆盖所选区间的历史日线行情。请配置服务端 TUSHARE_TOKEN，'
                             '或在回测工作区导入覆盖该区间的未复权日线 CSV。')
        raise ValueError('未配置TUSHARE_TOKEN，等待导入增量CSV')
    end=completed_date(); start=end-timedelta(days=550)
    params=dict(ts_code=symbol, start_date=start_date.replace('-', '') if start_date else start.strftime('%Y%m%d'),
                end_date=end_date.replace('-', '') if end_date else end.strftime('%Y%m%d'))
    def call(name, fields):
        # Never forward vendor errors: they may echo request credentials.
        try:
            with httpx.Client(timeout=8,follow_redirects=False) as client:
                r=client.post('https://api.tushare.pro',json=dict(api_name=name,token=token,params=params,fields=fields))
                r.raise_for_status(); payload=r.json()
            if payload.get('code')!=0: raise ValueError('行情服务拒绝请求，请检查令牌与daily/stk_limit权限')
            data=payload['data']
            return [dict(zip(data['fields'],r)) for r in data['items']]
        except (httpx.HTTPError,KeyError,TypeError,ValueError):
            raise ValueError('行情请求失败或缺少daily/stk_limit权限；连接尚未验证') from None
    daily=call('daily','ts_code,trade_date,open,high,low,close,pre_close,vol')
    limits={r['trade_date']:r for r in call('stk_limit','ts_code,trade_date,up_limit,down_limit')}
    out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=COLUMNS); writer.writeheader()
    for r in sorted(daily,key=lambda x:x['trade_date']):
        limit=limits.get(r['trade_date'])
        if not limit: raise ValueError('缺少官方每日限价，拒绝撮合')
        d=r['trade_date']
        writer.writerow(dict(date=f'{d[:4]}-{d[4:6]}-{d[6:]}',symbol=symbol,open=r['open'],high=r['high'],low=r['low'],
                             close=r['close'],volume=float(r['vol'])*100,prev_close=r['pre_close'],
                             limit_up=limit['up_limit'],limit_down=limit['down_limit'],suspended=0))
    return build_dataset(DatasetInput(name=symbol+' Tushare盘后日线',source='Tushare daily + stk_limit（外部连接未验收）',
                                     csv_text=out.getvalue(),ordinary_stock_confirmed=True,corporate_actions_confirmed_absent=True))
