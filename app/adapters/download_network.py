"""Worker-scoped DNS compatibility; never permits a non-public connection."""
import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlencode


class NetworkAddressError(ValueError):
    pass


def public_address(address):
    ip = ipaddress.ip_address(address.split('%')[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        raise NetworkAddressError('网络地址检查拒绝内网、保留或本机地址；请检查网络解析后重试，或上传本地文件。')


# Only these platform/CDN suffixes may recover from synthetic DNS or DNS failure.
# Arbitrary redirect destinations still require public system DNS.
DNS_DOMAINS = ('bilibili.com', 'b23.tv', 'biliapi.net', 'biliapi.com',
               'bilivideo.com', 'bilivideo.cn', 'bilicdn1.com',
               'douyin.com', 'iesdouyin.com', 'amemv.com', 'douyinvod.com',
               'bytecdn.cn', 'byteimg.com', 'ibytedtos.com')
SYNTHETIC_NET = ipaddress.ip_network('198.18.0.0/15')
DNS_HOSTS = {'upos-hz-mirrorakam.akamaized.net',
             'v3-dy-o.zjcdn.com', 'v5-dy-ov-experiment.zjcdn.com'}


def _public_dns(host):
    # Fixed public bootstrap addresses, TLS hostname verification, no proxy/config,
    # no redirects, bounded response and time. No platform URLs/cookies are sent.
    for dns_host, dns_ip in (('dns.alidns.com', '223.5.5.5'), ('dns.google', '8.8.8.8')):
        conn = http.client.HTTPSConnection(dns_host, timeout=5, context=ssl.create_default_context())
        conn._create_connection = lambda address, timeout=5, source_address=None: socket.create_connection(
            (dns_ip, 443), timeout, source_address)
        try:
            conn.request('GET', '/resolve?' + urlencode({'name': host, 'type': 'A'}),
                         headers={'Accept': 'application/dns-json'})
            response = conn.getresponse()
            raw = response.read(65537)
            if response.status != 200 or len(raw) > 65536:
                raise ValueError('Invalid DNS response')
            data = json.loads(raw)
            questions = data.get('Question', [])
            if isinstance(questions, dict):
                questions = [questions]
            if data.get('Status') != 0 or data.get('TC') or not any(
                q.get('name', '').rstrip('.').lower() == host and q.get('type') == 1 for q in questions
            ):
                raise ValueError('Invalid DNS question')
            answers = data.get('Answer', [])
            addresses = []
            ttl = 60
            for answer in answers:
                ttl = min(ttl, max(0, int(answer.get('TTL', 0))))
                if answer.get('type') == 1:
                    address = str(ipaddress.IPv4Address(answer['data']))
                    public_address(address)
                    addresses.append(address)
            if not addresses:
                raise ValueError('No public DNS answer')
            return list(dict.fromkeys(addresses)), ttl
        except NetworkAddressError:
            raise
        except (OSError, ValueError, TypeError, KeyError, http.client.HTTPException):
            continue
        finally:
            conn.close()
    raise NetworkAddressError('网络域名解析失败：系统解析异常且公共 DNS 不可用，请检查网络后重试，或上传本地文件。')


def install_public_dns():
    original = socket.getaddrinfo
    if getattr(original, '_media_public_dns', False):
        return
    cache = {}

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        name = host.decode('ascii') if isinstance(host, bytes) else host
        name = name.rstrip('.').lower() if isinstance(name, str) else ''
        allowed = name in DNS_HOSTS or any(name == domain or name.endswith('.' + domain) for domain in DNS_DOMAINS)
        try:
            entries = original(host, port, family, type, proto, flags)
        except socket.gaierror:
            if not allowed:
                raise
            entries = []
        synthetic = bool(entries) and all(
            ipaddress.ip_address(entry[4][0]) in SYNTHETIC_NET for entry in entries)
        if entries and not synthetic:
            for entry in entries:
                public_address(entry[4][0])
            return entries
        if not allowed or family not in (0, socket.AF_INET) or type not in (0, socket.SOCK_STREAM):
            raise NetworkAddressError('网络解析返回保留地址或不支持的地址类型，请检查网络后重试，或上传本地文件。')
        addresses, expires = cache.get(name, ([], 0))
        if expires <= time.monotonic():
            addresses, ttl = _public_dns(name)
            if len(cache) >= 128:
                cache.clear()
            cache[name] = addresses, time.monotonic() + ttl
        result = []
        for address in addresses:
            public_address(address)
            # Numeric lookup preserves the socket API's port/service semantics.
            result.extend(original(address, port, socket.AF_INET, type or socket.SOCK_STREAM,
                                   proto, flags | socket.AI_NUMERICHOST))
        return result

    resolve._media_public_dns = True
    socket.getaddrinfo = resolve
