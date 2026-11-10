"""yt-dlp is a controlled boundary; local media inspection uses real PyAV."""
import wave
import pytest
import yt_dlp
from app.adapters import download

VIDEO = 'https://www.bilibili.com/video/BV1xx411c7mD?p=2'


@pytest.fixture
def platform(monkeypatch):
    state = {'downloads': 0, 'info': {'id': 'BV1xx411c7mD_p2', 'title': '实际平台标题',
             'duration': 1, 'webpage_url': VIDEO, 'extractor_key': 'BiliBili',
             'ext': 'wav', 'vcodec': 'none', 'acodec': 'pcm_s16le'}}
    class FakeYoutubeDL:
        def __init__(self, options): state['options'] = options
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download=True):
            if download: return self.process_ie_result(state['info'], download=True)
            return state['info']
        def process_ie_result(self, info, download=True):
            state['downloads'] += 1
            path = self.prepare_filename(info)
            with wave.open(path, 'wb') as out:
                out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                out.writeframes(b'\x00\x00' * 8000)
            return info
        def prepare_filename(self, info): return state['options']['outtmpl'].replace('%(ext)s', 'wav')
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', FakeYoutubeDL)
    monkeypatch.setattr(download, 'install_network_guard', lambda: None)
    original = download.validate_url
    monkeypatch.setattr(download, 'validate_url', lambda url, **kwargs: original(url, resolve=False))
    return state


def test_download_keeps_platform_metadata_and_actual_audio_type(tmp_path, platform):
    result = download.download_in_worker(VIDEO, tmp_path / 'attempt', 1024 * 1024, 60)
    assert result['metadata']['title'] == '实际平台标题'
    assert result['metadata']['media_type'] == 'audio'
    assert result['metadata']['duration_seconds'] == 1
    assert result['metadata']['webpage_url'] == VIDEO
    assert result['metadata']['size_bytes'] == 16044
    assert platform['downloads'] == 1


def test_douyin_anonymous_session_returns_inspected_media_without_bare_api_retry(tmp_path, platform, monkeypatch):
    url = 'https://www.douyin.com/video/7664970443358489856'
    platform['info'].update(webpage_url=url, extractor_key='Douyin')
    def fresh_session(*args, **kwargs):
        raise AssertionError('Douyin must not spend the task timeout on an uninitialized API request')
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', fresh_session)
    monkeypatch.setattr(download, '_douyin_browser_info', lambda request, ydl: platform['info'], raising=False)
    result = download.download_in_worker(url, tmp_path / 'attempt', 1024 * 1024, 60)
    assert result['metadata']['platform'] == 'douyin'
    assert result['metadata']['duration_seconds'] == 1
    assert result['metadata']['webpage_url'] == url
    assert result['metadata']['size_bytes'] == 16044


def test_network_failure_does_not_start_anonymous_browser(tmp_path, platform, monkeypatch):
    def fail(*args, **kwargs): raise yt_dlp.utils.DownloadError('connection timed out')
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', fail)
    monkeypatch.setattr(download, '_douyin_browser_info', lambda *a: pytest.fail('unexpected browser'), raising=False)
    with pytest.raises(ValueError, match='网络'):
        download.download_in_worker(VIDEO,
                                    tmp_path / 'attempt', 1024 * 1024, 60)


@pytest.mark.parametrize('change', [
    {'duration': 90}, {'_type': 'playlist', 'entries': []}, {'is_live': True},
    {'webpage_url': 'https://evil.org/video/1'}, {'filesize': 2000000},
])
def test_rejects_platform_limits_and_redirects_before_downloading(tmp_path, platform, change):
    platform['info'].update(change)
    with pytest.raises(ValueError):
        download.download_in_worker(VIDEO, tmp_path / 'attempt', 1024 * 1024, 60)
    assert platform['downloads'] == 0


def test_actual_file_limits_checked_when_platform_omits_them(tmp_path, platform):
    platform['info']['duration'] = None
    with pytest.raises(ValueError, match='时长'):
        download.download_in_worker(VIDEO, tmp_path / 'attempt', 1024 * 1024, 0.5)


@pytest.mark.parametrize('error, hint', [
    (TimeoutError('https://secret/?token=secret-value'), '网络'),
    (RuntimeError('SSL UNEXPECTED_EOF_WHILE_READING secret-value'), '网络'),
    (RuntimeError('HTTP Error 403 token=secret-value'), '平台限制'),
    (RuntimeError('Unable to extract secret-value'), '解析'),
])
def test_external_errors_never_expose_request_details(tmp_path, platform, monkeypatch, error, hint):
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', fail)
    with pytest.raises(ValueError) as exc:
        download.download_in_worker(VIDEO, tmp_path / 'attempt', 1024 * 1024, 60)
    assert hint in str(exc.value)
    assert 'secret-value' not in str(exc.value) and 'https://' not in str(exc.value)


def test_media_probe_cannot_fetch_network_references(tmp_path):
    # PyAV uses native sockets, so it must not rely on Python's socket guard.
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
    path = tmp_path / 'mislabelled.wav'
    path.write_text(f'#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:{server.server_port}/segment.ts\n#EXT-X-ENDLIST\n')
    try:
        with pytest.raises(ValueError): download.inspect_media(path, 60)
        assert requests == []
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_unavailable_preferred_audio_falls_back_to_working_public_format(tmp_path, monkeypatch):
    """Exercise real yt-dlp format selection and downloads, not an option assertion."""
    import io
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\x00\x00' * 8000)
    payload = output.getvalue()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/unavailable':
                self.send_error(567)
            else:
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    info = {'id': 'sample', 'title': 'Format fallback fixture', 'webpage_url': VIDEO,
            'extractor_key': 'Generic', 'formats': [
                {'format_id': label, 'url': f'http://127.0.0.1:{server.server_port}/{label}',
                 'ext': 'wav', 'vcodec': 'none', 'acodec': 'pcm_s16le', 'abr': rate}
                for label, rate in [('working', 128), ('unavailable', 320)]]}
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', lambda *args, **kwargs: info)
    monkeypatch.setattr(download, 'install_network_guard', lambda: None)
    original = download.validate_url
    monkeypatch.setattr(download, 'validate_url', lambda url, **kwargs: original(url, resolve=False))
    try:
        result = download.download_in_worker(VIDEO, tmp_path / 'attempt', 1024 * 1024, 60)
        assert result['metadata']['size_bytes'] == 16044
        assert result['metadata']['duration_seconds'] == 1
        assert (tmp_path / 'attempt' / 'source.wav').read_bytes() == payload
    finally:
        server.shutdown(); server.server_close(); thread.join()
