from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs import Jobs
from app.main import create_app
from test_app import FakeExtractor, poll


def test_deleting_material_hides_it_after_restart_and_preserves_strategy_evidence(tmp_path):
    config = Settings(data_dir=tmp_path)
    app = create_app(config, extractor=FakeExtractor())
    with TestClient(app) as client:
        first = client.post('/api/documents/text', json={'title': '待删除', 'text': '原文买入'}).json()
        second = client.post('/api/documents/text', json={'title': '保留', 'text': '原文卖出'}).json()
        path = f'/api/documents/{first["id"]}'
        job = client.post(f'{path}/extract').json()
        assert poll(client, job['id'])['status'] == 'succeeded'
        strategies = client.get('/api/trading/strategies').json()
        assert strategies[0]['transcript'][0]['text'] == '原文买入'

        response = client.delete(path)
        assert response.status_code == 200
        assert response.json() == {'deleted': True}
        assert client.get(path).status_code == 404
        assert client.get(f'{path}/export').status_code == 404
        assert client.get(f'/api/jobs/{job["id"]}').status_code == 404
        assert client.post(f'/api/jobs/{job["id"]}/retry').status_code == 404
        assert client.delete(path).status_code == 404
        with pytest.raises(KeyError):
            app.state.store.create_job(first['id'], 'extract')

    with TestClient(create_app(config)) as client:
        assert [item['id'] for item in client.get('/api/documents').json()] == [second['id']]
        assert client.get(path).status_code == 404
        assert client.get('/api/trading/strategies').json() == strategies


@pytest.mark.parametrize('status', ['queued', 'running'])
def test_active_job_blocks_material_deletion(tmp_path, status):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        material = client.post('/api/documents/text', json={'title': '课程', 'text': '买入'}).json()
        job = app.state.store.create_job(material['id'], 'extract')
        if status == 'running':
            app.state.store.update_job(job['id'], 'running', '处理原文')
        path = f'/api/documents/{material["id"]}'

        assert client.delete(path).status_code == 409
        assert client.get(path).json()['jobs'][0]['status'] == status


def test_deleting_parent_keeps_shared_media_available_to_retranscription_copy(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    media = tmp_path / 'sample.wav'
    media.write_bytes(b'cached media fixture')
    with TestClient(app) as client:
        parent = app.state.store.create_document('课程', 'upload', media_path=str(media))
        app.state.store.set_media(parent['id'], str(media), {'media_type': 'audio'})
        parent_path = f'/api/documents/{parent["id"]}'
        copy = client.post(f'{parent_path}/retranscribe-copy').json()
        copy_path = f'/api/documents/{copy["id"]}'

        assert client.delete(parent_path).status_code == 200
        assert client.get(f'{parent_path}/media').status_code == 404
        child = client.get(copy_path).json()
        assert child['parent_document_id'] == parent['id']
        assert child['parent_document_deleted'] is True
        assert client.get(f'{copy_path}/media').content == b'cached media fixture'


def test_deleting_during_upload_probe_preserves_media_already_shared_with_copy(tmp_path, monkeypatch):
    probe_started, release_probe = Event(), Event()

    def slow_probe(self, job, payload):
        probe_started.set()
        assert release_probe.wait(5)
        return {'media_type': 'audio'}

    monkeypatch.setattr(Jobs, 'worker', slow_probe)
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        uploaded = pool.submit(client.post, '/api/documents/upload', files={'file': ('sample.wav', b'cached audio')})
        try:
            assert probe_started.wait(5)
            parent = client.get('/api/documents').json()[0]
            parent_path = f'/api/documents/{parent["id"]}'
            copied = client.post(f'{parent_path}/retranscribe-copy')
            assert copied.status_code == 201
            assert client.delete(parent_path).status_code == 200
        finally:
            release_probe.set()
        assert uploaded.result(timeout=5).status_code == 404
        copy_path = f'/api/documents/{copied.json()["id"]}'
        assert client.get(f'{copy_path}/media').content == b'cached audio'
