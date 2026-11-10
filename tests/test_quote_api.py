from datetime import datetime
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_quotes import account, wire


def test_quote_endpoints_work_without_strategy_and_reject_invalid_symbols(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    app.state.quotes.clock = lambda: datetime.fromisoformat('2026-11-10T10:00:00+08:00')
    calls = []
    def transport(symbols): calls.append(symbols); return wire()
    app.state.quotes.transport = transport
    with TestClient(app) as client:
        assert client.get('/api/trading/quotes/catalog').json()['members'] == []
        response = client.get('/api/trading/quotes/overview?symbols=600000.SH')
        assert response.status_code == 200
        assert response.json()['accounts'] == []
        assert response.json()['quotes'][0]['price'] == 10.2
        assert client.get('/api/trading/quotes/overview?symbols=600000.SH').status_code == 200
        assert len(calls) == 1
        assert client.get('/api/trading/quotes/overview?symbols=sh600000').status_code == 400
        assert client.get('/api/trading/quotes/overview?symbols=https://other.example').status_code == 400
        assert client.get('/api/trading/portfolios').json() == []
        assert client.get('/api/trading/paper/sessions').json() == []
    assert not app.state.quote_worker.thread.is_alive()


def test_catalog_and_account_contract_keep_stock_pool_and_accounts_separate(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    app.state.quotes.clock = lambda: datetime.fromisoformat('2026-11-10T10:00:00+08:00')
    app.state.quotes.transport = lambda symbols: wire()
    with TestClient(app) as client:
        store = app.state.trading_service.store
        with store.transaction() as c:
            store.put(c, 'dataset', dict(id='research',dataset_type='research_adjusted',
                symbol_metadata=[dict(symbol='600000.SH',name='浦发银行')], universe={'name':'沪深300','as_of_date':'2026-11-09'}))
            store.put(c, 'paper', account())
            store.put(c, 'paper', account('history', mode='replay'))
        catalog = client.get('/api/trading/quotes/catalog').json()
        assert catalog['members'] == [{'symbol':'600000.SH','name':'浦发银行'}]
        result = client.get('/api/trading/quotes/overview').json()
        assert result['quotes'] == [] and result['excluded_historical_accounts'] == 1
        assert result['accounts'][0]['total_assets'] == 10040
        assert result['accounts'][0]['positions'][0]['quote']['source_time'].endswith('+08:00')
