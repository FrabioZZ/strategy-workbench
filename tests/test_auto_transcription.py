"""Automatic link transcription: worker fixtures, real queue/database/API."""
import threading

from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs import Jobs
from app.main import create_app
from test_app import poll

VIDEO = 'https://www.bilibili.com/video/BV1xx411c7mD'
SEGMENTS = [{'id': 's1', 'text': '价格突破20日线买入', 'start': 0, 'end': 2}]


def configured(tmp_path):
    model = tmp_path / 'test-only-model'
    model.mkdir()
    (model / 'model.bin').touch()
    return Settings(data_dir=tmp_path, asr_model=str(model))


def downloaded(tmp_path):
    path = tmp_path / 'cache.wav'
    path.write_bytes(b'test-only-media')
    return {'path': str(path), 'metadata': {'media_type': 'audio', 'title': '课程标题'}}


def test_link_automatically_transcribes_without_observable_idle_handoff(tmp_path, monkeypatch):
    app = create_app(configured(tmp_path))
    started, release = threading.Event(), threading.Event()
    calls, idle_snapshots = [], []
    store = app.state.store
    original_connect = store.connect

    # Read from a separate connection after every write commits. This catches the
    # tempting update_job(succeeded); submit(transcribe) implementation even if
    # ordinary API polling happens to miss its short idle window.
    class ObservedConnection:
        def __init__(self): self.connection = original_connect()
        def __enter__(self): return self.connection.__enter__()
        def __exit__(self, *args):
            result = self.connection.__exit__(*args)
            with original_connect() as reader:
                rows = reader.execute("""SELECT d.id FROM documents d
                    WHERE d.media_path IS NOT NULL AND d.segments='[]'
                    AND EXISTS (SELECT 1 FROM jobs j WHERE j.document_id=d.id
                                AND j.kind='download' AND j.status='succeeded')
                    AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.document_id=d.id
                                    AND j.status IN ('queued','running'))""").fetchall()
                idle_snapshots.extend(row['id'] for row in rows)
            return result

    def worker(self, job, payload):
        calls.append(payload['operation'])
        if payload['operation'] == 'download': return downloaded(tmp_path)
        started.set()
        assert release.wait(5)
        return SEGMENTS

    monkeypatch.setattr(Jobs, 'worker', worker)
    with TestClient(app) as client:
        monkeypatch.setattr(store, 'connect', ObservedConnection)
        try:
            doc = client.post('/api/documents/url', json={'url': VIDEO}).json()
            assert started.wait(2), 'download must automatically start ASR'
            current = client.get(f'/api/documents/{doc["id"]}').json()
            assert current['media_status'] == 'transcribing'
            assert current['jobs'][0]['kind'] == 'transcribe'
            assert current['jobs'][0]['status'] == 'running'
            assert current['jobs'][1]['status'] == 'succeeded'
            assert client.post(f'/api/documents/{doc["id"]}/transcribe').status_code == 409
            assert not idle_snapshots
        finally:
            release.set()
        assert poll(client, current['jobs'][0]['id'])['status'] == 'succeeded'
        final = client.get(f'/api/documents/{doc["id"]}').json()
        assert final['segments'] == SEGMENTS and final['media_status'] == 'transcribed'
        assert calls == ['download', 'asr'] and not idle_snapshots


def test_automatic_asr_failure_retries_cache_and_survives_restart(tmp_path, monkeypatch):
    config = configured(tmp_path)
    calls = []
    def worker(self, job, payload):
        calls.append(payload['operation'])
        if payload['operation'] == 'download': return downloaded(tmp_path)
        if calls.count('asr') == 1: raise ValueError('测试专用 ASR 失败')
        return SEGMENTS
    monkeypatch.setattr(Jobs, 'worker', worker)
    with TestClient(create_app(config)) as client:
        doc = client.post('/api/documents/url', json={'url': VIDEO}).json()
        download_job = next(j for j in doc['jobs'] if j['kind'] == 'download')
        assert poll(client, download_job['id'])['status'] == 'succeeded'
        current = client.get(f'/api/documents/{doc["id"]}').json()
        assert current['jobs'][0]['kind'] == 'transcribe'
        assert poll(client, current['jobs'][0]['id'])['status'] == 'failed'
        failed_id = current['jobs'][0]['id']
    with TestClient(create_app(config)) as client:
        current = client.get(f'/api/documents/{doc["id"]}').json()
        assert current['has_media'] and current['media_status'] == 'transcription_failed'
        retry = client.post(f'/api/jobs/{failed_id}/retry').json()
        assert poll(client, retry['id'])['status'] == 'succeeded'
        assert client.get(f'/api/documents/{doc["id"]}').json()['segments'] == SEGMENTS
        assert calls == ['download', 'asr', 'asr']


def test_download_retry_does_not_replace_existing_corrected_transcript(tmp_path, monkeypatch):
    config = configured(tmp_path)
    app = create_app(config)
    calls = []
    def worker(self, job, payload):
        calls.append(payload['operation'])
        return downloaded(tmp_path)
    monkeypatch.setattr(Jobs, 'worker', worker)
    with TestClient(app) as client:
        store = app.state.store
        doc = store.create_document('已校对资料', 'url', segments=SEGMENTS, source_url=VIDEO)
        job = store.create_job(doc['id'], 'download')
        store.update_job(job['id'], 'interrupted', '测试历史任务')
        retry = client.post(f'/api/jobs/{job["id"]}/retry').json()
        assert poll(client, retry['id'])['status'] == 'succeeded'
        current = store.document(doc['id'])
        assert current['segments'] == SEGMENTS and current['revision'] == doc['revision']
        assert calls == ['download']
        assert all(j['kind'] == 'download' for j in current['jobs'])
