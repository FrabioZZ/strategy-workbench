"""Bounded anonymous-browser connection for the public Douyin video page."""
import json
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from app.adapters.download_network import DNS_HOSTS, public_address

# Exact hosts observed on the normal public page, including its security scripts.
# No personal profile, proxy credentials, TLS interception, or signature emulation.
BROWSER_HOSTS = frozenset('''www.douyin.com v.douyin.com www-hj.douyin.com www.iesdouyin.com
lf-douyin-pc-web.douyinstatic.com lf-douyin-pc-web-back.douyinstatic.com
lf-c-flwb.bytetos.com lf-cdn-tos.bytescm.com lf-security.bytegoofy.com
lf-security-backup.bytegoofy.com lf-headquarters-speed.yhgfb-cn-static.com
lf-rc1.yhgfb-cn-static.com lf-rc2.yhgfb-cn-static.com lf-static.applogcdn.com
lf3-short.ibytedapm.com lf9-sec.bytetos.com lf3-sec.bytetos.com
privacy.zijieapi.com mon.zijieapi.com mcs.zijieapi.com vcs.zijieapi.com
mssdk.bytedance.com sf1-cdn-tos.douyinstatic.com p-pc-weboff.byteimg.com
p3-pc-weboff.byteimg.com p3-pc.douyinpic.com p3-pc-sign.douyinpic.com
p9-pc-sign.douyinpic.com fonts.bytedance.com lf-ucenter-web.yhgfb-cn-static.com
lf-zt.douyin.com lf3-effectcdn-tos.byteeffecttos.com lf6-effectcdn-tos.byteeffecttos.com
lf3-pendah.bytetos.com lf3-static.bytednsdoc.com live.douyin.com
sf1-cdn-tos.huoshanstatic.com tnc0-aliec2.zijieapi.com unpkg.byted-static.com'''.split())
MAX_RESULT = 2 * 1024 * 1024


def canonical_browser_url(url):
    """Resolve the public shortlink, then remove sharing UI parameters before browsing."""
    from app.adapters.download import validate_url
    url = validate_url(url, resolve=False)
    if urlsplit(url).hostname != 'v.douyin.com':
        return url

    class Redirect(urllib.request.HTTPRedirectHandler):
        max_redirections = 5
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            parsed = urlsplit(newurl)
            if (parsed.scheme != 'https' or parsed.hostname not in
                    {'v.douyin.com', 'www.iesdouyin.com', 'www.douyin.com'}
                    or parsed.port not in (None, 443) or parsed.username is not None
                    or parsed.password is not None):
                raise ValueError('Unexpected sharing redirect')
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect())
    with opener.open(urllib.request.Request(url), timeout=10) as response:
        canonical = validate_url(response.geturl(), resolve=False)
    if urlsplit(canonical).hostname != 'www.douyin.com':
        raise ValueError('Sharing URL did not resolve to a video')
    return canonical


def validate_result(raw, requested_url):
    from app.adapters.download import validate_url
    try:
        if len(raw) > MAX_RESULT:
            raise ValueError()
        result = json.loads(raw)
        canonical = validate_url(result['url'], resolve=False)
        target = urlsplit(canonical)
        detail = result['detail']
        if result.get('error') or target.hostname != 'www.douyin.com' or not isinstance(detail.get('video'), dict):
            raise ValueError()
        if detail.get('aweme_id') != target.path.rsplit('/', 1)[-1]:
            raise ValueError()
        requested = validate_url(requested_url, resolve=False)
        if urlsplit(requested).hostname != 'www.douyin.com' or requested != canonical:
            raise ValueError()
        return {'url': canonical, 'detail': detail}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('抖音匿名页面未提供可用媒体；请稍后重试或上传有权使用的本地文件。') from None


def connect_public(target):
    parsed = urlsplit('https://' + target)
    if (parsed.hostname not in BROWSER_HOSTS or parsed.port != 443 or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('Unsupported browser destination')
    entries = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not entries:
        raise ValueError('No public address')
    for entry in entries:
        public_address(entry[4][0])
    last_error = None
    for entry in entries[:2]:
        address = entry[4][0]
        try:
            remote = socket.create_connection((address, 443), timeout=10)
        except OSError as exc:
            last_error = exc
            continue
        try:
            peer = remote.getpeername()[0]
            public_address(peer)
            if peer != address:
                raise ValueError('Peer address changed')
            return remote
        except Exception:
            remote.close()
            raise
    raise last_error or ValueError('No connection')


class PublicProxy:
    """Loopback listener, public-only fixed remote peers, encrypted-byte/time budgets."""
    def __init__(self, timeout=150, limit=80 * 1024 * 1024):
        self.deadline = time.monotonic() + timeout
        self.limit = limit
        self.idle_timeout = 5
        self.bytes = 0
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(32)
        self.connections = set()
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                if not owner.slots.acquire(timeout=max(0, min(10, owner.deadline - time.monotonic()))):
                    return
                remote = None
                try:
                    self.connection.settimeout(10)
                    line = self.rfile.readline(8193).decode('ascii').strip().split()
                    if len(line) != 3 or line[0] != 'CONNECT':
                        raise ValueError()
                    size = 0
                    while True:
                        header = self.rfile.readline(8193)
                        size += len(header)
                        if size > 16384 or not header:
                            raise ValueError()
                        if header == b'\r\n':
                            break
                    if time.monotonic() >= owner.deadline:
                        raise ValueError()
                    remote = connect_public(line[1])
                    with owner.lock:
                        owner.connections.update((remote, self.connection))
                    self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                    self.wfile.flush()
                    last_activity = time.monotonic()
                    while time.monotonic() < owner.deadline:
                        ready, _, _ = select.select([self.connection, remote], [], [], .5)
                        if not ready and time.monotonic() - last_activity >= owner.idle_timeout:
                            return
                        for stream in ready:
                            data = stream.recv(65536)
                            if not data:
                                return
                            last_activity = time.monotonic()
                            with owner.lock:
                                owner.bytes += len(data)
                                if owner.bytes > owner.limit:
                                    return
                            (remote if stream is self.connection else self.connection).sendall(data)
                except (OSError, ValueError, UnicodeError):
                    if remote is None:
                        try:
                            self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n')
                        except OSError:
                            pass
                finally:
                    with owner.lock:
                        owner.connections.discard(self.connection)
                        owner.connections.discard(remote)
                    if remote:
                        remote.close()
                    owner.slots.release()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            request_queue_size = 32
        self.server = Server(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.deadline = 0
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            connections = list(self.connections)
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        self.thread.join(timeout=2)


def get_public_detail(url):
    from app.adapters.download import MediaDownloadError, validate_url
    url = validate_url(url, resolve=False)
    if urlsplit(url).hostname not in {'www.douyin.com', 'v.douyin.com'}:
        raise ValueError('Not a Douyin page')
    node = shutil.which('node')
    if not node:
        raise MediaDownloadError('抖音匿名导入需要 Node.js、项目 npm ci 依赖及已安装的 Chrome，请先完成安装。')
    browser_url = canonical_browser_url(url)
    DNS_HOSTS.update(BROWSER_HOSTS)
    chunks = []
    with PublicProxy() as proxy:
        process = subprocess.Popen([node, str(Path(__file__).with_name('douyin_browser.cjs'))],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        reader = threading.Thread(target=lambda: chunks.append(process.stdout.read(MAX_RESULT + 1)), daemon=True)
        reader.start()
        try:
            # Keep this pipe open: its EOF tells the bridge its parent was cancelled/killed.
            process.stdin.write((json.dumps({'url': browser_url, 'port': proxy.port, 'timeout': 120000}) + '\n').encode())
            process.stdin.flush()
            process.wait(timeout=135)
            reader.join(timeout=5)
            raw = b''.join(chunks)
            if not raw or len(raw) > MAX_RESULT:
                raise MediaDownloadError('抖音匿名页面未能返回媒体详情，请检查网络后重试。')
            if b'"error":"dependency"' in raw:
                raise MediaDownloadError('抖音匿名导入需要项目 npm ci 依赖和已安装的 Chrome，请先完成安装。')
            try:
                return validate_result(raw, browser_url)
            except ValueError as exc:
                raise MediaDownloadError(str(exc)) from None
        except subprocess.TimeoutExpired:
            raise MediaDownloadError('抖音匿名页面加载超时，请检查网络后重试。') from None
        finally:
            process.stdin.close()
            if process.poll() is None:
                # EOF normally closes Chrome. Force only this bridge tree if cleanup stalls.
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                    process.kill()
            process.wait(timeout=10)
            reader.join(timeout=2)
            process.stdout.close()
