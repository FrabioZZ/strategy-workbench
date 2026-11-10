"""Anonymous browser boundaries: only requested public video details may leave the bridge."""
import json
import io
import socket
import threading
import pytest
from app.adapters import download_browser as browser
import urllib.request

VIDEO = 'https://www.douyin.com/video/7664970443358489856'

def payload(video_id='7664970443358489856'):
    return {'url': VIDEO, 'detail': {'aweme_id': video_id, 'video': {'duration': 1000}}}


@pytest.mark.parametrize('destination, accepted', [(VIDEO+'?previous_page=app_code_link', True),
                                                 ('https://evil.org/video/123', False),
                                                 ('https://www.douyin.com/jingxuan', False)])
def test_shortlink_resolves_to_clean_single_video_before_browser(monkeypatch, destination, accepted):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def geturl(self): return destination
    class Opener:
        def open(self, request, **kwargs):
            assert request.full_url == 'https://v.douyin.com/aU0BxZKBvVI/'
            return Response()
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *a: Opener())
    if accepted:
        assert browser.canonical_browser_url('https://v.douyin.com/aU0BxZKBvVI/') == VIDEO
    else:
        with pytest.raises(ValueError): browser.canonical_browser_url('https://v.douyin.com/aU0BxZKBvVI/')

def test_bridge_accepts_only_requested_video():
    assert browser.validate_result(json.dumps(payload()), VIDEO)['detail']['video']['duration'] == 1000
    with pytest.raises(ValueError):
        browser.validate_result(json.dumps(payload('123')), VIDEO)


def test_result_validation_requires_resolved_identity():
    with pytest.raises(ValueError):
        browser.validate_result(json.dumps(payload()), 'https://v.douyin.com/aU0BxZKBvVI/')


@pytest.mark.parametrize('returned_id, accepted', [('7664970443358489856', True),
                                                 ('1111111111111111111', False)])
def test_shortlink_bridge_result_is_bound_to_resolved_target(monkeypatch, returned_id, accepted):
    # Replace only the browser process transport; exercise the real parent bridge/validator.
    result = payload(returned_id)
    result['url'] = 'https://www.douyin.com/video/' + returned_id
    class Process:
        stdin = io.BytesIO()
        stdout = io.BytesIO(json.dumps(result).encode())
        def wait(self, **kwargs):
            if not self.stdin.closed:
                assert json.loads(self.stdin.getvalue())['url'] == VIDEO
            return 0
        def poll(self): return 0
    class Proxy:
        port = 12345
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(browser, 'canonical_browser_url', lambda url: VIDEO)
    monkeypatch.setattr(browser.shutil, 'which', lambda name: 'node')
    monkeypatch.setattr(browser.subprocess, 'Popen', lambda *a, **k: Process())
    monkeypatch.setattr(browser, 'PublicProxy', Proxy)
    monkeypatch.setattr(browser, 'DNS_HOSTS', set(browser.DNS_HOSTS))
    if accepted:
        assert browser.get_public_detail('https://v.douyin.com/aU0BxZKBvVI/')['url'] == VIDEO
    else:
        with pytest.raises(ValueError):
            browser.get_public_detail('https://v.douyin.com/aU0BxZKBvVI/')

@pytest.mark.parametrize('change', [
    {'url': 'https://evil.org/video/7664970443358489856'},
    {'url': 'https://www.douyin.com/video/123'},
    {'detail': {'aweme_id': '7664970443358489856', 'video': None}},
    {'error': 'captcha'},
])
def test_bridge_rejects_unusable_or_unrelated_result(change):
    data = payload(); data.update(change)
    with pytest.raises(ValueError):
        browser.validate_result(json.dumps(data), VIDEO)

def test_bridge_bounds_untrusted_output():
    with pytest.raises(ValueError):
        browser.validate_result(' ' * (2 * 1024 * 1024 + 1), VIDEO)

@pytest.mark.parametrize('target', ['127.0.0.1:443', 'evil.org:443', 'www.douyin.com:80',
                                  'user@www.douyin.com:443', 'www.douyin.com:443/path'])
def test_proxy_rejects_targets_before_network(target, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('invalid target reached DNS')
    monkeypatch.setattr(socket, 'getaddrinfo', unexpected)
    with pytest.raises(ValueError):
        browser.connect_public(target)

def test_proxy_rejects_private_dns_without_connecting(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('private connection attempted'))
    with pytest.raises(ValueError):
        browser.connect_public('www.douyin.com:443')

@pytest.mark.parametrize('host', ['www.douyin.com', 'www.iesdouyin.com'])
def test_proxy_pins_public_ip_and_checks_actual_peer(monkeypatch, host):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('8.8.4.4', 443))])
    class Connection:
        closed = False
        peer = '8.8.4.4'
        def getpeername(self): return (self.peer, 443)
        def close(self): self.closed = True
    conn = Connection()
    def connect(target, **kwargs):
        assert target == ('8.8.4.4', 443)
        return conn
    monkeypatch.setattr(socket, 'create_connection', connect)
    assert browser.connect_public(host + ':443') is conn
    conn.peer = '127.0.0.1'
    with pytest.raises(ValueError): browser.connect_public(host + ':443')
    assert conn.closed

def test_proxy_refuses_plain_http_and_unknown_connect():
    with browser.PublicProxy(timeout=2) as proxy:
        for request in [b'GET http://www.douyin.com/ HTTP/1.1\r\n\r\n',
                        b'CONNECT evil.org:443 HTTP/1.1\r\n\r\n']:
            with socket.create_connection(('127.0.0.1', proxy.port), timeout=2) as conn:
                conn.sendall(request)
                assert b'403' in conn.recv(100)


def test_busy_proxy_waits_for_capacity_instead_of_dropping_page_resource(monkeypatch):
    peers = []
    def connect(target):
        upstream, peer = socket.socketpair(); peers.append(peer)
        return upstream
    monkeypatch.setattr(browser, 'connect_public', connect)
    try:
        with browser.PublicProxy(timeout=3) as proxy:
            proxy.slots = threading.BoundedSemaphore(1)
            first = socket.create_connection(('127.0.0.1', proxy.port), timeout=2)
            first.sendall(b'CONNECT www.douyin.com:443 HTTP/1.1\r\n\r\n')
            assert b'200' in first.recv(100)
            second = socket.create_connection(('127.0.0.1', proxy.port), timeout=2)
            second.sendall(b'CONNECT www.douyin.com:443 HTTP/1.1\r\n\r\n')
            threading.Timer(.15, first.close).start()
            try:
                assert b'200' in second.recv(100)
            finally:
                second.close(); first.close()
    finally:
        for peer in peers: peer.close()


def test_idle_proxy_tunnel_releases_capacity(monkeypatch):
    upstream, peer = socket.socketpair()
    monkeypatch.setattr(browser, 'connect_public', lambda target: upstream)
    try:
        with browser.PublicProxy(timeout=3) as proxy:
            proxy.idle_timeout = .1
            with socket.create_connection(('127.0.0.1', proxy.port), timeout=1) as conn:
                conn.sendall(b'CONNECT www.douyin.com:443 HTTP/1.1\r\n\r\n')
                assert b'200' in conn.recv(100)
                assert conn.recv(100) == b''
    finally:
        peer.close()
