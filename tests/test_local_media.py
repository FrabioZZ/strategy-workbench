"""Local playback regression: real files and real isolated PyAV worker, no models."""
import io
import json
import wave

import av
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.jobs import Jobs
from app.models import Segment
from app.adapters import download
from test_app import FakeExtractor


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        out.writeframes(b'\x00\x00' * 24000)
    return buffer.getvalue()


def write_video(path):
    # Silent H.264 is browser playable, even though it cannot be transcribed.
    with av.open(str(path), 'w') as out:
        stream = out.add_stream('libx264', rate=10)
        stream.width, stream.height, stream.pix_fmt = 160, 90, 'yuv420p'
        for _ in range(30):
            frame = av.VideoFrame(160, 90, 'yuv420p')
            for plane in frame.planes:
                plane.update(bytes([128]) * plane.buffer_size)
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


@pytest.mark.parametrize('filename', ['course.wav', 'audio-disguised.mp4'])
def test_upload_probes_real_audio_without_asr_in_child_process(tmp_path, monkeypatch, filename):
    def forbidden(*args, **kwargs):
        raise AssertionError('media inspection must not run in service process')
    monkeypatch.setattr(download, 'inspect_media', forbidden)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        content = wav_bytes()
        response = client.post('/api/documents/upload', files={'file': (filename, content)})
        assert response.status_code == 202
        d = response.json()
        assert d['media_metadata'].get('media_type') == 'audio'
        assert d['media_metadata']['duration_seconds'] == 3
        assert d['media_metadata']['size_bytes'] == len(content)
        assert d['jobs'] == [] and d['segments'] == [] and d['revision'] == 1
        assert d['media_status'] == 'awaiting_transcription'
        assert client.get(f'/api/documents/{d["id"]}/media').content == content
        assert client.post(f'/api/documents/{d["id"]}/transcribe').status_code == 409


def test_upload_silent_video_is_video_not_audio_or_unknown(tmp_path):
    fixture = tmp_path / 'silent.mp4'
    write_video(fixture)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        d = client.post('/api/documents/upload', files={'file': ('silent.mp4', fixture.read_bytes())}).json()
        assert d['media_metadata'].get('media_type') == 'video'
        assert d['media_metadata']['duration_seconds'] == pytest.approx(3)
        assert d['media_metadata']['has_audio'] is False


def test_legacy_media_recovers_without_changing_saved_work(tmp_path, monkeypatch):
    app = create_app(Settings(data_dir=tmp_path))
    store = app.state.store
    store.init()
    cache = tmp_path / 'legacy.wav'
    cache.write_bytes(wav_bytes())
    d = store.create_document('旧校对资料', 'upload', media_path=str(cache))
    d = store.edit(d['id'], 1, [{'id': 's1', 'text': '校对后买入', 'start': 1, 'end': 2}])
    store.save_strategy(d, FakeExtractor().extract([Segment(**d['segments'][0])]), 'test', 'test-only')
    job = store.create_job(d['id'], 'transcribe')
    store.update_job(job['id'], 'succeeded', '旧转写完成')
    # Exercise the real legacy schema migration, including existing related rows.
    with store.connect() as conn:
        conn.execute('ALTER TABLE documents DROP COLUMN media_metadata')
        saved = {table: [tuple(r) for r in conn.execute(f'SELECT * FROM {table}')] for table in ('documents', 'jobs', 'strategies')}
    with TestClient(app) as client:
        recovered = client.get(f'/api/documents/{d["id"]}').json()
        assert recovered['media_metadata'].get('media_type') == 'audio'
        assert recovered['revision'] == 2 and not recovered['strategy_stale']
        with store.connect() as conn:
            assert [tuple(r)[:-1] for r in conn.execute('SELECT * FROM documents')] == saved['documents']
            for table in ('jobs', 'strategies'):
                assert [tuple(r) for r in conn.execute(f'SELECT * FROM {table}')] == saved[table]
        exported = client.get(f'/api/documents/{d["id"]}/export').json()
        assert exported['transcript'][0]['text'] == '校对后买入'
        assert exported['strategy']['rules'][0]['evidence'][0]['start'] == 1
    def no_reprobe(*args, **kwargs):
        raise AssertionError('persisted metadata should be reused')
    monkeypatch.setattr(Jobs, 'worker', no_reprobe)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get(f'/api/documents/{d["id"]}').json()['media_metadata'] == recovered['media_metadata']


@pytest.mark.parametrize('case', ['invalid', 'too_long', 'timeout', 'oversize_legacy'])
def test_probe_failure_keeps_cache_and_does_not_repeat(tmp_path, monkeypatch, case):
    config = Settings(data_dir=tmp_path)
    if case == 'too_long': config.max_duration_seconds = 1
    if case == 'timeout': config.task_timeout_seconds = 0
    if case == 'oversize_legacy': config.max_upload_mb = 0
    app = create_app(config)
    content = b'invalid-media' if case == 'invalid' else wav_bytes()
    with TestClient(app) as client:
        if case == 'oversize_legacy':
            cache = tmp_path / 'old.wav'; cache.write_bytes(content)
            d = app.state.store.create_document('old', 'upload', media_path=str(cache))
            d = client.get(f'/api/documents/{d["id"]}').json()
        else:
            d = client.post('/api/documents/upload', files={'file': ('course.wav', content)}).json()
        assert d['media_metadata'].get('probe_status') == 'unavailable'
        assert not d['media_metadata'].get('media_type')
        assert d['jobs'] == [] and d['has_media']
        assert client.get(f'/api/documents/{d["id"]}/media').content == content
        retries = []
        def no_retry(*args, **kwargs):
            retries.append(True)
            raise AssertionError('failed probe should not repeat on every GET')
        monkeypatch.setattr(Jobs, 'worker', no_retry)
        assert client.get(f'/api/documents/{d["id"]}').json()['media_metadata'] == d['media_metadata']
        assert retries == []


def test_uploaded_network_playlist_cannot_make_native_requests(tmp_path):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_error(404)
        def log_message(self, *args): pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    playlist = f'#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:{server.server_port}/secret.ts\n#EXT-X-ENDLIST\n'.encode()
    try:
        with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
            d = client.post('/api/documents/upload', files={'file': ('mislabelled.wav', playlist)}).json()
            assert d['media_metadata'].get('probe_status') == 'unavailable'
            assert requests == []
            assert 'http://' not in json.dumps(d['media_metadata'])
    finally:
        server.shutdown(); server.server_close(); thread.join()
