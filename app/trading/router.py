import csv
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.store import now
from app.trading import models, portfolios, datasets, feeds, research
from app.trading.engine import public
from app.trading.indicators import registry
from app.trading.conditions import OPERATORS


def indicator_capabilities():
    return dict(frequency='daily',indicators=registry(),condition_operators=OPERATORS,
                rule_schema=models.Conditional.model_json_schema())


def router(service):
    api=APIRouter(prefix='/api/trading',tags=['trading'])
    store=service.store; sources=service.sources
    @api.get('/capabilities')
    def capabilities():
        return dict(market='CN_A_MAIN',frequency='daily',supported_symbols='沪深主板普通股票（非ST、非上市初期），单标的运行',
                    rule_types=['ma','threshold','conditional'],broker=dict(connected=False,label='未接入券商，仅本地模拟撮合'),
                    feeds=dict(csv=True,tushare_configured=feeds.configured(),tushare_verified=False),limitations=datasets.LIMITATIONS,
                    research=dict(dataset_type='research_adjusted',market='CN_A',price_basis='forward_adjusted',
                                  allowed_modes=['backtest'],quantity_unit='synthetic_unit',limitations=research.LIMITATIONS),
                    indicators=registry(),condition_operators=OPERATORS,rule_schema=models.Conditional.model_json_schema(),
                    execution=dict(signal='completed_daily_close',fill='next_bar_open',
                                   crossover='previous_lte_current_gt / previous_gte_current_lt',
                                   warmup='past_bars_only_no_pre_start_signals',date_range='backtests_only'),
                    unsupported_conditions=['竞价成交额/竞价强弱','盘中封板时间/炸板回封','盘口排队/实时成交',
                                            '缺少数据的题材/板块/市值/换手率筛选'])
    @api.get('/indicators')
    def indicators(): return indicator_capabilities()
    @api.get('/strategies')
    def strategies(): return portfolios.candidates(sources)
    @api.get('/portfolios')
    def list_portfolios():
        with store.transaction() as c: return [portfolios.decorate(p,sources) for p in store.list(c,'portfolio')]
    @api.post('/portfolios',status_code=201)
    def create_portfolio(body:models.PortfolioInput):
        with store.transaction() as c: return portfolios.save_portfolio(store,c,sources,body)
    @api.get('/portfolios/{ident}')
    def get_portfolio(ident:str):
        with store.transaction() as c: return portfolios.decorate(store.get(c,'portfolio',ident),sources)
    @api.put('/portfolios/{ident}')
    def update_portfolio(ident:str,body:models.PortfolioInput):
        with store.transaction() as c: return portfolios.save_portfolio(store,c,sources,body,ident)
    @api.delete('/portfolios/{ident}')
    def delete_portfolio(ident:str):
        with store.transaction() as c: store.delete(c,'portfolio',ident)
        return {'deleted':True}
    @api.get('/portfolios/{ident}/readiness')
    def readiness(ident:str): return get_portfolio(ident)['readiness']
    @api.post('/portfolios/{ident}/normalize')
    def normalize(ident:str,body:models.Revision):
        with store.transaction() as c:
            value=store.get(c,'portfolio',ident)
            if value['revision']!=body.revision: raise HTTPException(409,'组合版本已变化')
            active=[i for i in value['items'] if i['enabled']]
            if not active: raise HTTPException(400,'至少启用一个策略')
            total=sum(i['weight'] for i in active)
            for i in active: i['weight']=i['weight']/total*100 if total else 100/len(active)
            value.update(revision=value['revision']+1,updated_at=now())
            return store.put(c,'portfolio',portfolios.decorate(value,sources))
    @api.get('/datasets/template')
    def template():
        return Response(','.join(datasets.COLUMNS)+'\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="daily-template.csv"'})
    @api.post('/datasets/import',status_code=201)
    def import_dataset(body:models.DatasetInput):
        value=datasets.build_dataset(body)
        with store.transaction() as c: store.put(c,'dataset',value)
        return datasets.summary(value)
    @api.post('/datasets/demo',status_code=201)
    def demo(): return import_dataset(datasets.demo_input())
    @api.get('/datasets')
    def list_datasets():
        with store.transaction() as c: return [datasets.summary(v) for v in store.list(c,'dataset')]
    @api.get('/datasets/{ident}')
    def get_dataset(ident:str):
        with store.transaction() as c: return store.get(c,'dataset',ident)
    @api.post('/backtests',status_code=201)
    def backtest(body:models.RunInput):
        with store.transaction() as c: return public(service.create(c,body))
    @api.get('/backtests')
    def backtests():
        with store.transaction() as c: return [public(v) for v in store.list(c,'backtest')]
    @api.get('/backtests/{ident}')
    def get_backtest(ident:str):
        with store.transaction() as c: return public(store.get(c,'backtest',ident))
    @api.post('/paper/sessions',status_code=201)
    def create_session(body:models.SessionInput):
        with store.transaction() as c: return public(service.create(c,body,True))
    @api.get('/paper/sessions')
    def sessions():
        with store.transaction() as c: return [public(v) for v in store.list(c,'paper')]
    @api.get('/paper/sessions/{ident}')
    def session(ident:str):
        with store.transaction() as c: return public(store.get(c,'paper',ident))
    @api.post('/paper/sessions/{ident}/start')
    def start(ident:str):
        with store.transaction() as c: return public(service.action(c,ident,'start'))
    @api.post('/paper/sessions/{ident}/pause')
    def pause(ident:str):
        with store.transaction() as c: return public(service.action(c,ident,'pause'))
    @api.post('/paper/sessions/{ident}/step')
    def step(ident:str,body:models.SyncInput):
        with store.transaction() as c: return public(service.action(c,ident,'step',body))
    @api.post('/paper/sessions/{ident}/sync')
    def sync(ident:str,body:models.SyncInput):
        with store.transaction() as c: return public(service.action(c,ident,'sync',body))
    return api
