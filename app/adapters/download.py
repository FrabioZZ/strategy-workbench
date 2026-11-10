import ipaddress
import math
import os
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit, parse_qs, urlunsplit
from app.adapters.download_network import NetworkAddressError, public_address, install_public_dns

HOSTS = {"www.bilibili.com", "bilibili.com", "m.bilibili.com", "b23.tv", "www.douyin.com", "douyin.com", "v.douyin.com"}


def extract_shared_url(text):
    """Extract exactly one normalized video; no network work on the request thread."""
    candidates = re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>\"'，。！？；、【】（）「」《》]+", text)
    if not candidates:
        raise ValueError("未找到完整 HTTPS 视频链接，请粘贴 B站或抖音的单视频链接或分享文案。")
    urls = {validate_url(candidate.rstrip('.,!;:)]}'), resolve=False) for candidate in candidates}
    if len(urls) != 1:
        raise ValueError("检测到多个不同链接，请每次只导入一个视频；不同分P也需分别导入。")
    return urls.pop()


def validate_url(url, resolve=True):
    try:
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname not in HOSTS or p.username or p.password or p.port not in (None, 443) or p.fragment:
            raise ValueError()
        if "\\" in url or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError()
        if p.hostname in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}:
            valid_path = re.fullmatch(r"/video/(?:BV[0-9A-Za-z]{10}|av[1-9][0-9]*)/?", p.path)
        elif p.hostname in {"www.douyin.com", "douyin.com"}:
            valid_path = re.fullmatch(r"/video/[0-9]+/?", p.path)
        else:
            valid_path = re.fullmatch(r"/[0-9A-Za-z_-]+/?", p.path)
        if not valid_path:
            raise ValueError()
        query = ''
        host, path = p.hostname, p.path
        if host in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}:
            host, path = 'www.bilibili.com', path.rstrip('/')
            parts = parse_qs(p.query, keep_blank_values=True).get('p', [])
            if parts:
                if len(parts) != 1 or not re.fullmatch(r'[0-9]{1,5}', parts[0]) or not 1 <= int(parts[0]) <= 10000:
                    raise ValueError()
                query = f'p={int(parts[0])}'
        elif host in {'douyin.com', 'www.douyin.com'}:
            host, path = 'www.douyin.com', path.rstrip('/')
    except ValueError:
        raise ValueError("仅支持 HTTPS 的 Bilibili/抖音单视频或分享短链接，请使用完整视频链接。") from None
    if resolve:
        try:
            for entry in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM):
                public_address(entry[4][0])
        except OSError:
            raise ValueError("视频域名解析失败，请检查网络或改用本地上传。") from None
    return urlunsplit(('https', host, path, query, ''))


def install_network_guard():
    """Worker-only: validate actual connect destination, including redirects and CDN URLs."""
    install_public_dns()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def safe_address(address):
        if not isinstance(address, tuple):
            raise ValueError("不支持本地套接字")
        host, port = address[:2]
        try:
            public_address(host)
        except ValueError:
            # Named destination resolves once; pin the checked IP for this connect.
            try:
                ipaddress.ip_address(host.split("%")[0])
            except ValueError:
                resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                for entry in resolved:
                    public_address(entry[4][0])
                return resolved[0][4]
            raise
        return address

    def connect(sock, address):
        return original_connect(sock, safe_address(address))

    def connect_ex(sock, address):
        return original_connect_ex(sock, safe_address(address))

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


class MediaDownloadError(ValueError):
    """Only fixed, application-owned messages may cross the worker boundary."""


def safe_download_error(exc):
    if isinstance(exc, MediaDownloadError):
        return str(exc)
    if isinstance(exc, NetworkAddressError):
        return str(exc)
    detail = str(exc).lower()
    if '保留' in detail or '内网' in detail:
        return '网络地址检查拒绝内网或保留地址，请检查网络解析后重试；也可上传本地文件。'
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(x in detail for x in ('timed out', 'timeout', 'resolve', 'connection', 'network', 'getaddrinfo', '域名解析', 'ssl', 'tls', 'certificate')):
        return '网络连接或域名解析失败，请检查网络后重试；也可上传本地文件。'
    if any(x in detail for x in ('403', '401', '429', '412', 'login', 'cookie', 'captcha', 'rate limit', 'geo-restrict', 'private', 'pay', 'premium', 'supporter')):
        return '平台限制：可能需要登录、验证、权限或稍后重试。应用不会读取浏览器凭据，请改用有权使用的本地文件。'
    if any(x in detail for x in ('404', 'not found', 'removed', 'deleted', 'unavailable')):
        return '视频不可用或链接已失效，请检查原页面，或上传本地文件。'
    return '平台解析或下载失败：页面可能已改版或没有支持的单文件音视频格式，请改用本地上传。'


def inspect_media(path, max_duration, require_audio=True):
    import av
    try:
        # Native libavformat sockets do not use Python's socket.connect guard.
        with av.open(str(path), options={'protocol_whitelist': 'file'}) as media:
            if require_audio and not media.streams.audio:
                raise MediaDownloadError('媒体没有可用音轨，请选择包含语音的文件。')
            if not media.streams.audio and not media.streams.video:
                raise MediaDownloadError('媒体没有可用音视频轨道，请转换后上传。')
            duration = media.duration / av.time_base if media.duration is not None else None
            if duration is None or not math.isfinite(duration) or duration <= 0:
                raise MediaDownloadError('无法确定媒体时长，请转换为标准音视频文件后导入。')
            if duration > max_duration:
                raise MediaDownloadError('媒体时长超过限制，请拆分后上传。')
            return {'duration_seconds': duration, 'media_type': 'video' if media.streams.video else 'audio',
                    'has_audio': bool(media.streams.audio)}
    except MediaDownloadError:
        raise
    except Exception:
        raise MediaDownloadError('媒体解析失败：文件可能不完整或编码不受支持，请转换后上传。') from None


def download_in_worker(url: str, folder: Path, limit: int, max_duration: int):
    try:
        return _download(url, folder, limit, max_duration)
    except Exception as exc:
        raise MediaDownloadError(safe_download_error(exc)) from None


def _douyin_browser_info(url, ydl):
    from app.adapters.download_browser import get_public_detail
    from yt_dlp.extractor.tiktok import DouyinIE
    result = get_public_detail(url)
    info = DouyinIE(ydl)._parse_aweme_video_app(result['detail'])
    info.update(webpage_url=result['url'], extractor_key='Douyin')
    return info


def _download(url: str, folder: Path, limit: int, max_duration: int):
    # yt-dlp never loads CLI config, browser cookies, user credentials or external downloaders.
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            os.environ.pop(name)
    install_network_guard()
    url = validate_url(url)
    from yt_dlp import YoutubeDL
    folder.mkdir(parents=True, exist_ok=True)

    def check_progress(d):
        if d.get("downloaded_bytes", 0) > limit or sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) > limit:
            raise MediaDownloadError("媒体文件超过大小限制，请拆分后上传。")

    def filter_media(info, *, incomplete=False):
        if info.get("duration") and (not math.isfinite(info['duration']) or info['duration'] > max_duration):
            raise MediaDownloadError("媒体时长超过限制，请拆分后上传。")
        if info.get("is_live") or info.get('live_status') in ('is_live', 'is_upcoming'):
            raise MediaDownloadError("不支持直播或尚未开始的视频，请使用已发布的单视频。")
        if info.get('filesize', 0) and info['filesize'] > limit:
            raise MediaDownloadError('媒体文件超过大小限制，请拆分后上传。')
        return None

    options = {"format": "bestaudio[protocol=https]/best[protocol=https]/bestaudio[protocol=http]/best[protocol=http]",
               "check_formats": "selected", "paths": {"temp": str(folder)},
               "outtmpl": str(folder / "source.%(ext)s"), "noplaylist": True, "playlistend": 1,
               "max_filesize": limit, "socket_timeout": 20, "retries": 1, "fragment_retries": 1,
               "progress_hooks": [check_progress], "match_filter": filter_media,
               "quiet": True, "no_warnings": True, "proxy": "", "cachedir": False,
               "enable_file_urls": False, "hls_prefer_native": True, "fixup": "never",
               "cookiefile": None, "cookiesfrombrowser": None, "usenetrc": False}
    with YoutubeDL(options) as ydl:
        if urlsplit(url).hostname in {'www.douyin.com', 'v.douyin.com'}:
            info = _douyin_browser_info(url, ydl)
        else:
            info = ydl.extract_info(url, download=False)
        if not info or info.get("_type") in ("playlist", "multi_video"):
            raise MediaDownloadError("不支持合集，请使用单个视频或明确的B站分P链接。")
        filter_media(info)
        try:
            webpage_url = validate_url(info.get('webpage_url') or url, resolve=False)
        except ValueError:
            raise MediaDownloadError('短链接未指向支持的单视频页面，请复制原视频链接。') from None
        # Keep the explicitly selected part even when the extractor omits it in metadata.
        if urlsplit(url).query.startswith('p='):
            webpage_url = url
        info = ydl.process_ie_result(info, download=True)
        path = Path(ydl.prepare_filename(info)).resolve()
    if path.parent != folder.resolve() or not path.is_file() or path.stat().st_size > limit:
        raise MediaDownloadError("下载未完成或超过大小限制，请检查链接或拆分后上传。")
    actual = inspect_media(path, max_duration)
    metadata = {**actual, 'title': str(info.get('title') or '')[:500],
                'platform': 'bilibili' if urlsplit(webpage_url).hostname in {'www.bilibili.com', 'b23.tv'} else 'douyin',
                'webpage_url': webpage_url, 'size_bytes': path.stat().st_size,
                'extension': path.suffix.lstrip('.'), 'platform_duration_seconds': info.get('duration')}
    return {'path': str(path), 'metadata': metadata}
