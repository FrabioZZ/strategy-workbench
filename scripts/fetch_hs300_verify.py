"""Exercise the real downloaded bundle through an isolated workbench API."""
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.trading.history import import_bundle


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    bundle=ROOT/'data/history/hs300-20240101-20261101'
    target=ROOT/'.runtime'/('hs300-real-api-'+uuid4().hex[:10]); target.mkdir(parents=True)
    started=time.perf_counter()
    first=import_bundle(bundle,target); second=import_bundle(bundle,target)
    assert first['id']==second['id'] and first['hash']==second['hash']
    results=[]
    with TestClient(create_app(Settings(data_dir=target))) as client:
        listed=client.get('/api/trading/datasets').json()
        assert len(listed)==1 and 'rows' not in listed[0]
        assert len(listed[0]['symbol_metadata'])==300
        p=client.post('/api/trading/portfolios',json=dict(name='隔离API真实行情验证',mode='equal',conflict_policy='weighted',items=[
            dict(id='ma',name='人工测试均线5/20',confirmed=True,mapping_note='隔离测试参数，不修改正式用户策略',
                 rules=dict(type='ma',fast=5,slow=20,target_pct=80))]))
        assert p.status_code==201,p.text
        portfolio=p.json()
        for symbol in ['600000.SH','300750.SZ','688981.SH','302132.SZ']:
            payload=dict(portfolio_id=portfolio['id'],portfolio_revision=1,dataset_id=first['id'],symbol=symbol,initial_cash=100000)
            response=client.post('/api/trading/backtests',json=payload)
            assert response.status_code==201,response.text
            run=response.json()
            assert run['execution_model']=='adjusted_research' and run['quantity_unit']=='synthetic_unit'
            assert run['cash']>=0 and run['signals'] and run['equity']
            assert all(f['signal_date']<f['date'] for f in run['fills'])
            repeated=client.post('/api/trading/backtests',json=payload).json()
            assert repeated['fills']==run['fills'] and repeated['metrics']==run['metrics']
            results.append(dict(symbol=symbol,signals=len(run['signals']),start=run['equity'][0]['date'],
                                end=run['equity'][-1]['date'],metrics=run['metrics'],cash=run['cash']))
        payload.update(symbol='600000.SH',name='应拒绝的研究数据回放',mode='replay')
        rejection=client.post('/api/trading/paper/sessions',json=payload)
        assert rejection.status_code==400,rejection.text
        assert client.get('/api/trading/paper/sessions').json()==[]
    report=dict(dataset_id=first['id'],dataset_hash=first['hash'],row_count=first['row_count'],
                universe=first['universe'],coverage=first['coverage'],runs=results,isolated_data_dir=str(target),
                elapsed_seconds=round(time.perf_counter()-started,3),production_data_modified=False)
    evidence=ROOT/'.runtime/phase3-data-evidence';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'real-api-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
