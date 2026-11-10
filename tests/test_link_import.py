"""Phase 1B: external media/model work is replaced only at the worker boundary."""
from pathlib import Path
import threading
import pytest
from fastapi.testclient import TestClient
from app.adapters import download
from app.config import Settings
from app.jobs import Jobs
from app.main import create_app
from test_app import poll, FakeExtractor

VIDEO = 'https://www.bilibili.com/video/BV1xx411c7mD'


@pytest.mark.parametrize('text, expected', [
    (f'这是课程【分享】 {VIDEO}/?p=02&share_source=copy 。复制打开', VIDEO + '?p=2'),
    ('分享 https://v.douyin.com/AbC_12/ 复制打开抖音', 'https://v.douyin.com/AbC_12/'),
    ('【课程】https://b23.tv/Abc123，点击查看', 'https://b23.tv/Abc123'),
    (f'{VIDEO} {VIDEO}/?share_source=copy', VIDEO),
    ('https://m.bilibili.com/video/av123/?p=1', 'https://www.bilibili.com/video/av123?p=1'),
    ('https://douyin.com/video/123456?utm_source=share', 'https://www.douyin.com/video/123456'),
])
def test_share_text_normalized_without_losing_part(text, expected):
    assert download.extract_shared_url(text) == expected


@pytest.mark.parametrize('text', [
    f'{VIDEO} https://v.douyin.com/abc/', f'{VIDEO}?p=1 {VIDEO}?p=2',
    f'{VIDEO} https://evil.org/video/1', 'https://www.bilibili.com.evil.org/video/BV1xx411c7mD',
    'http://b23.tv/abc', 'https://user@b23.tv/abc', 'https://b23.tv:444/abc',
    'https://www.bilibili.com/video/BV123', VIDEO + '?p=0', VIDEO + '?p=abc',
    VIDEO + '?p=1&p=2', VIDEO + '#secret', VIDEO + '\\evil',
    '没有链接', 'https://www.douyin.com/user/123', 'https://b23.tv/%2e%2e',
])
def test_share_text_rejects_ambiguous_or_malformed_input(text):
    with pytest.raises(ValueError):
        download.extract_shared_url(text)


def test_download_without_asr_then_retry_cached_transcription(tmp_path, monkeypatch):
    config = Settings(data_dir=tmp_path)
    calls = []
    def worker(self, job, payload):
        calls.append(payload['operation'])
        if payload['operation'] == 'download':
            assert payload['url'] == VIDEO + '?p=2'
            path = tmp_path / 'source.wav'
            path.write_bytes(b'test-only-media')
            return {'path': str(path), 'metadata': {'platform': 'bilibili', 'title': '平台课程 P2',
                    'duration_seconds': 12.5, 'media_type': 'audio', 'size_bytes': path.stat().st_size,
                    'webpage_url': VIDEO + '?p=2'}}
        assert payload['path'] == str(tmp_path / 'source.wav')
        if calls.count('asr') == 1:
            raise ValueError('本地转写失败：测试专用失败')
        return [{'id': 's1', 'text': '20日线买入', 'start': 0, 'end': 2}]
    monkeypatch.setattr(Jobs, 'worker', worker)
    app = create_app(config, extractor=FakeExtractor())
    with TestClient(app) as c:
        r = c.post('/api/documents/url', json={'url': f'课程 {VIDEO}?p=2&share=1 复制打开'})
        assert r.status_code == 202, r.text
        d = r.json(); ident = d['id']
        assert d['jobs'][0]['kind'] == 'download'
        assert poll(c, d['jobs'][0]['id'])['status'] == 'succeeded'
        d = c.get(f'/api/documents/{ident}').json()
        assert d['has_media'] and d['media_status'] == 'awaiting_transcription'
        assert d['title'] == '平台课程 P2' and d['media_metadata']['media_type'] == 'audio'
        assert d['source_url'] == VIDEO + '?p=2' and d['strategy'] is None
        assert 'media_path' not in d and c.get(f'/api/documents/{ident}/media').status_code == 200
        assert c.post(f'/api/documents/{ident}/transcribe').status_code == 409
        assert len(c.get(f'/api/documents/{ident}').json()['jobs']) == 1
        model = tmp_path / 'test-model'; model.mkdir(); (model / 'model.bin').touch()
        config.asr_model = str(model)  # Marker only: model never loaded by this test.
        j = c.post(f'/api/documents/{ident}/transcribe').json()
        assert poll(c, j['id'])['status'] == 'failed'
        assert c.get(f'/api/documents/{ident}').json()['media_status'] == 'transcription_failed'
        retry = c.post(f'/api/jobs/{j["id"]}/retry').json()
        assert poll(c, retry['id'])['status'] == 'succeeded'
        assert calls == ['download', 'asr', 'asr']
        j = c.post(f'/api/documents/{ident}/extract').json()
        assert poll(c, j['id'])['status'] == 'succeeded'
        exported = c.get(f'/api/documents/{ident}/export').json()
        assert exported['media_metadata']['duration_seconds'] == 12.5
        assert exported['source_url'] == VIDEO + '?p=2'
        assert exported['strategy']['executable'] is False
        # Do not silently replace a corrected transcript from the manual start route.
        assert c.post(f'/api/documents/{ident}/transcribe').status_code == 409
    with TestClient(create_app(config)) as c:
        assert c.get(f'/api/documents/{ident}').json()['media_metadata']['title'] == '平台课程 P2'


def test_active_download_blocks_duplicate_transcription_and_edits(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def worker(self, job, payload):
        started.set(); release.wait(3)
        raise ValueError('平台下载失败：测试专用失败')
    monkeypatch.setattr(Jobs, 'worker', worker)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        try:
            d = c.post('/api/documents/url', json={'url': VIDEO}).json()
            assert started.wait(2)
            assert c.post(f'/api/documents/{d["id"]}/transcribe').status_code == 409
            assert c.put(f'/api/documents/{d["id"]}/transcript', json={'revision': 1, 'segments': [{'id':'s1','text':'原文'}]}).status_code == 409
        finally:
            release.set()
        assert poll(c, d['jobs'][0]['id'])['status'] == 'failed'
        assert c.get(f'/api/documents/{d["id"]}').json()['media_status'] == 'download_failed'


def test_cached_transcription_serialized_and_missing_cache_never_downloads(tmp_path, monkeypatch):
    model = tmp_path / 'test-only-model'; model.mkdir(); (model / 'model.bin').touch()
    config = Settings(data_dir=tmp_path, asr_model=str(model))
    app = create_app(config)
    started, release = threading.Event(), threading.Event()
    operations = []
    def worker(self, job, payload):
        operations.append(payload['operation']); started.set(); release.wait(3)
        raise ValueError('测试专用转写失败')
    monkeypatch.setattr(Jobs, 'worker', worker)
    with TestClient(app) as c:
        cache = tmp_path / 'test-cache.wav'; cache.write_bytes(b'test-only')
        d = app.state.store.create_document('自定义标题', 'url', source_url=VIDEO, media_path=str(cache))
        app.state.store.set_media(d['id'], str(cache), {'title':'平台标题', 'media_type':'audio'})
        assert app.state.store.document(d['id'])['title'] == '自定义标题'
        try:
            first = c.post(f'/api/documents/{d["id"]}/transcribe').json()
            assert started.wait(2)
            assert c.post(f'/api/documents/{d["id"]}/transcribe').status_code == 409
        finally: release.set()
        assert poll(c, first['id'])['status'] == 'failed'
        cache.unlink()  # This test's own isolated fixture only.
        assert c.post(f'/api/jobs/{first["id"]}/retry').status_code == 409
        assert operations == ['asr']


def test_share_errors_do_not_create_documents(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        for text in [VIDEO + ' https://b23.tv/abc', 'https://evil.org', VIDEO+'?p=no']:
            response = c.post('/api/documents/url', json={'url': text})
            assert response.status_code == 400
            assert 'https://' not in response.json()['detail']
        assert c.get('/api/documents').json() == []


def test_legacy_database_migrates_without_losing_transcript(tmp_path):
    import sqlite3
    from app.store import Store
    with sqlite3.connect(tmp_path / 'workspace.sqlite3') as c:
        c.execute('''CREATE TABLE documents (id TEXT PRIMARY KEY, title TEXT NOT NULL,
          source_type TEXT NOT NULL, source_url TEXT, media_path TEXT, is_demo INTEGER DEFAULT 0,
          revision INTEGER NOT NULL DEFAULT 1, segments TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        c.execute('''INSERT INTO documents(id,title,source_type,segments,created_at,updated_at)
          VALUES ('old','原有资料','text','[{"id":"s1","text":"保存的原文"}]','2026-11-08','2026-11-08')''')
    store = Store(tmp_path); store.init(); store.init()
    document = store.document('old')
    assert document['segments'][0]['text'] == '保存的原文'
    assert document['media_metadata'] == {} and not document['has_media']
