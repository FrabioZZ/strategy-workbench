from fastapi.testclient import TestClient

from app.demo import create_demo_app
from app.main import create_app
from app.config import Settings


def test_demo_instance_uses_its_own_settings_and_blocks_external_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'formal'))
    monkeypatch.setenv('TUSHARE_TOKEN', 'formal-market-token')
    monkeypatch.setenv('AI_API_KEY', 'formal-model-key')

    app = create_demo_app(tmp_path / 'sample', 8766)
    with TestClient(app) as client:
        demo = client.get('/api/status').json()['daily_demo']
        assert demo['symbol'] == '600000.SH'
        assert (demo['start_date'], demo['end_date']) == ('2024-01-01', '2026-11-01')
        assert (demo['replay']['start_date'], demo['replay']['end_date']) == ('2024-01-01', '2026-01-01')
        assert '沪深300' in demo['market_source']
        assert app.state.workstation_worker.thread.is_alive()
        assert app.state.settings.data_dir == tmp_path / 'sample'
        assert app.state.settings.ai_api_key != 'formal-model-key'
        assert app.state.settings.ai_base_url == 'http://127.0.0.1:8766/__phase11_model'
        assert client.get('/api/trading/capabilities').json()['feeds']['tushare_configured'] is False
        assert client.get('/api/trading/quotes/overview').status_code == 404
        assert client.post('/api/documents/url', json={'url': 'https://www.bilibili.com/video/BV1test'}).status_code == 403
        assert client.put('/api/ai/config', json={}).status_code == 403
        assert client.post('/api/trading/paper/sessions', json={}).status_code == 403
        assert client.post('/__phase11_model/chat/completions', json={}).status_code == 403
        assert client.get('/runtime-mode.js').headers['cache-control'] == 'no-store'

    assert not (tmp_path / 'formal').exists()


def test_regular_app_has_no_demo_model_route_or_defaults(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert 'daily_demo' not in client.get('/api/status').json()
        assert client.post('/__phase11_model/chat/completions', json={}).status_code == 404
        assert 'window.dailyDemo = null' in client.get('/runtime-mode.js').text
