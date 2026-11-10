from datetime import date, datetime, time, timezone
from fastapi import HTTPException
from app.store import now
from app.trading import engine, feeds, research
from app.trading.datasets import summary
from app.trading.datasets import CN_TZ, LIMITATIONS, completed_date
from app.trading.portfolios import ready_portfolio
from app.trading.store import identity
from app.trading.conditions import raw_only_indicators

class TradingService:
    def __init__(self,store,sources,clock=None):
        self.store=store; self.sources=sources
        self.clock=clock or (lambda: datetime.now(timezone.utc))

    def dataset(self,c,ident,symbol):
        ds=self.store.get(c,'dataset',ident)
        if symbol not in ds['symbols']: raise HTTPException(400,'数据集不含所选标的')
        return ds

    def create(self,c,body,paper=False):
        p=ready_portfolio(self.store,c,self.sources,body.portfolio_id,body.portfolio_revision)
        ds=self.dataset(c,body.dataset_id,body.symbol) if body.dataset_id else None
        is_research=bool(ds and ds.get('dataset_type')=='research_adjusted')
        if is_research and raw_only_indicators(p):
            raise HTTPException(400,'复权研究数据缺少可信实际涨跌停价，不能执行：'+','.join(raw_only_indicators(p)))
        if paper and (body.start_date or body.end_date):
            raise HTTPException(400,'日期区间目前仅适用于回测；模拟会话请使用完整冻结数据')
        if paper and is_research: raise HTTPException(400,'复权研究数据仅限历史回测，禁止用于模拟会话')
        if paper and body.mode=='incremental' and ds and ds['is_demo']: raise HTTPException(400,'增量跟盘禁止使用演示数据，请选择历史回放')
        if not paper and ds is None: raise HTTPException(400,'回测必须指定数据集')
        value={**identity(),**body.model_dump(),**engine.new_ledger(body.initial_cash),'kind':'paper' if paper else 'backtest',
               'status':'paused' if paper else 'completed','portfolio_snapshot':p,'dataset_hash':ds['hash'] if ds else None,
               'is_demo':bool((ds and ds['is_demo']) or any(i['source_snapshot'] and i['source_snapshot']['is_demo'] for i in p['items'] if i['enabled'])),
               'warnings':list(LIMITATIONS)+(ds['warnings'][:1] if ds and ds['is_demo'] else [])}
        value.update(execution_model='adjusted_research' if is_research else 'strict_daily',
                     price_basis=ds['price_basis'] if ds else 'raw',
                     quantity_unit='synthetic_unit' if is_research else 'share',
                     dataset_snapshot=summary(ds) if ds else None)
        if is_research: value['warnings']=list(dict.fromkeys(research.LIMITATIONS+ds['warnings']))
        if paper:
            value.update(cursor=None,last_quote_at=None,heartbeat_at=None,feed_status='paused',message='历史回放' if body.mode=='replay' else '本地日线增量模拟，等待新鲜行情',updated_at=now(),_requests={})
        else:
            rows=[bar for bar in ds['rows'] if bar['symbol']==body.symbol]
            selected=[bar for bar in rows if (not body.start_date or bar['date']>=body.start_date)
                      and (not body.end_date or bar['date']<=body.end_date)]
            if not selected:
                raise HTTPException(400,'所选日期区间没有该标的行情')
            # Pre-start prices seed indicators only: no signal, target, pending
            # order, cash movement or equity point may leak into the interval.
            value['_history']=[dict(bar) for bar in rows if bar['date']<selected[0]['date']]
            value.update(requested_start_date=body.start_date,requested_end_date=body.end_date,
                         actual_start_date=selected[0]['date'],actual_end_date=selected[-1]['date'],
                         warmup_bars=len(value['_history']),initial_equity=engine.money(body.initial_cash))
            for bar in selected:
                (research.advance if is_research else engine.advance)(value,p,bar,value['costs'],body.symbol,body.initial_cash)
            value['final_equity']=value['equity'][-1]['equity']
            value['pnl']=engine.money(value['final_equity']-value['initial_equity'])
            value['metrics'].update({key:value[key] for key in ('initial_equity','final_equity','pnl')})
        return self.store.put(c,value['kind'],value)

    def action(self,c,ident,action,body=None):
        value=self.store.get(c,'paper',ident)
        if action=='pause':
            value.update(status='paused',feed_status='paused',message='已暂停',updated_at=now())
        elif action=='start':
            if value['status']=='running': return value
            ready_portfolio(self.store,c,self.sources,value['portfolio_id'],value['portfolio_revision'])
            if value['mode']=='incremental':
                # Resume authorizes future opens only. Re-observe valid data before
                # allowing any persisted signal to trade in this activation.
                value.update(_activated_at=self.clock().isoformat(),_signal_observed_at=None)
            value.update(status='running',message='历史回放运行中' if value['mode']=='replay' else '等待新鲜盘后日线',updated_at=now())
        else:
            request_id=body.request_id if body else None
            signature={'action':action,'dataset_id':body.dataset_id if body else None}
            if request_id and request_id in value['_requests']:
                if value['_requests'][request_id]!=signature: raise HTTPException(409,'同一request_id不可用于不同操作/数据')
                return value
            if action=='step' and (value['status']!='paused' or value['mode']!='replay'): raise HTTPException(409,'单步仅适用于暂停的历史回放')
            if action=='sync' and value['status']!='running': raise HTTPException(409,'请先启动会话再同步')
            if body and body.dataset_id:
                if value['mode']=='replay' and body.dataset_id!=value['dataset_id']: raise HTTPException(409,'历史回放数据已冻结，不可更换')
                value['dataset_id']=body.dataset_id
            self.consume(c,value)
            if request_id: value['_requests'][request_id]=signature
        return self.store.put(c,'paper',value)

    def consume(self,c,value):
        value.update(heartbeat_at=now(),updated_at=now())
        if value['feed']=='tushare' and value['mode']=='incremental':
            try:
                ds=feeds.fetch(value['symbol'])
            except (ValueError,HTTPException):
                value.update(feed_status='error' if feeds.configured() else 'waiting',message='行情未就绪：请检查服务端Tushare配置、权限和数据完整性，连接未验收')
                return
            # Keep each externally fetched immutable version for audit/reproduction.
            existing=next((d for d in self.store.list(c,'dataset') if d['hash']==ds['hash'] and d['source']==ds['source']),None)
            if existing: ds=existing
            else: self.store.put(c,'dataset',ds)
            value['dataset_id']=ds['id']
        elif value['dataset_id']:
            ds=self.dataset(c,value['dataset_id'],value['symbol'])
        else:
            value.update(feed_status='waiting',message='尚无行情，请导入增量CSV或配置Tushare')
            return
        if ds.get('dataset_type')=='research_adjusted': raise HTTPException(400,'复权研究数据禁止用于模拟会话或增量同步')
        rows=[r for r in ds['rows'] if r['symbol']==value['symbol']]
        if value['mode']=='incremental' and ds['is_demo']: raise HTTPException(400,'增量跟盘不能消费演示数据')
        old={r['date']:r for r in value['_history']}
        for row in rows:
            if row['date'] in old and row!=old[row['date']]: raise HTTPException(409,'已消费行情被修订，需建立新会话，不能改写旧账本')
        fresh=[r for r in rows if not value['cursor'] or r['date']>value['cursor']]
        value['dataset_hash']=ds['hash']
        value['last_quote_at']=rows[-1]['date']+'T15:00:00+08:00'
        if value['mode']=='replay':
            if not fresh:
                value.update(feed_status='exhausted',message='历史回放已到数据末尾',status='paused')
                return
            fresh=fresh[:1]
        else:
            age=(completed_date()-date.fromisoformat(rows[-1]['date'])).days
            if age>value['max_age_days']:
                value.update(feed_status='stale',message='行情过期，不推进游标或撮合')
                return
            # Read the wall clock after obtaining/validating data, not from the
            # last complete bar. This also handles resume with no new rows and
            # older stored sessions that have no observation timestamps yet.
            observed_at=self.clock().isoformat()
            value.setdefault('_activated_at',observed_at)
            if not value.get('_signal_observed_at'):
                value['_signal_observed_at']=observed_at
            if not fresh:
                value.update(feed_status='waiting',message='没有晚于游标的新行情，未重复成交')
                return
        bootstrap=value['mode']=='incremental' and not value['_history']
        for bar in fresh:
            if value['_history'] and abs(bar['prev_close']-value['_history'][-1]['close'])>.011:
                raise HTTPException(409,'增量行情与已消费昨收不连续，可能缺交易日或存在公司行为')
            # Warm old data, but a signal must exist before the modeled 09:30 CN
            # open. A newly observed signal cannot trade earlier bars in a batch.
            age=(completed_date()-date.fromisoformat(bar['date'])).days
            pending=value.get('_pending')
            pending_age=(date.fromisoformat(bar['date'])-date.fromisoformat(pending['date'])).days if pending else 0
            trade=True
            if value['mode']=='incremental':
                opening=datetime.combine(date.fromisoformat(bar['date']),time(9,30),tzinfo=CN_TZ)
                eligible_after=max(datetime.fromisoformat(value['_activated_at']),
                                   datetime.fromisoformat(value['_signal_observed_at']))
                trade=(not bootstrap and opening>eligible_after
                       and age<=value['max_age_days'] and pending_age<=value['max_age_days'])
            engine.advance(value,value['portfolio_snapshot'],bar,value['costs'],value['symbol'],value['initial_cash'],trade=trade)
            if value['mode']=='incremental':
                value['_signal_observed_at']=self.clock().isoformat()
            value['cursor']=bar['date']
        value.update(feed_status='fresh',message='历史回放已推进' if value['mode']=='replay' else ('首批数据仅预热，等待信号生效后的下一开盘' if bootstrap else '新鲜日线已消费，仅撮合信号生效后的开盘（本地盘后模拟）'))
