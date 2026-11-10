"""Real guard/resolver behavior, with only DNS and HTTP transport replaced."""
import http.client
import ipaddress
import json
import socket

import pytest

from app.adapters import download


@pytest.fixture
def network(monkeypatch):
    state = {'system': '198.18.1.81', 'answer': '8.8.4.4', 'requests': [], 'connections': []}

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        try:
            ipaddress.ip_address(host)
            address = host
        except ValueError:
            address = state['system']
            if isinstance(address, Exception):
                raise address
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (address, port))]

    class Connection:
        def __init__(self, host, **kwargs):
            self.host = host
            self.context = kwargs['context']
        def request(self, method, path, **kwargs):
            state['requests'].append((self.host, method, path))
            assert self.context.check_hostname
        def getresponse(self):
            return self
        status = 200
        def read(self, count):
            name = state['requests'][-1][2].split('name=')[1].split('&')[0]
            return json.dumps({'Status': 0, 'Question': {'name': name + '.', 'type': 1},
                               'Answer': [{'name': name + '.', 'type': 1, 'TTL': 30,
                                           'data': state['answer']}]}).encode()
        def close(self):
            pass

    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(socket.socket, 'connect', lambda self, addr: state['connections'].append(addr))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda self, addr: state['connections'].append(addr) or 0)
    monkeypatch.setattr(http.client, 'HTTPSConnection', Connection)
    download.install_network_guard()
    return state


@pytest.mark.parametrize('host', ['www.bilibili.com', 'v.douyin.com', 'upos-sz.bilivideo.com', 'v3.douyinvod.com',
                                  'upos-hz-mirrorakam.akamaized.net', 'v3-dy-o.zjcdn.com',
                                  'v5-dy-ov-experiment.zjcdn.com'])
def test_fake_dns_for_platform_or_cdn_uses_public_answer_and_pins_connect(network, host):
    resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    assert resolved[0][4] == ('8.8.4.4', 443)
    with socket.socket() as sock:
        sock.connect((host, 443))
    assert network['connections'] == [('8.8.4.4', 443)]


def test_dns_failure_can_use_platform_fallback(network):
    network['system'] = socket.gaierror('temporary resolution failure')
    assert socket.getaddrinfo('www.douyin.com', 443, type=socket.SOCK_STREAM)[0][4] == ('8.8.4.4', 443)


@pytest.mark.parametrize('host, address', [
    ('www.bilibili.com', '127.0.0.1'), ('www.douyin.com', '10.0.0.1'),
    ('evil.org', '198.18.1.1'), ('douyin.com.evil.org', '198.18.1.1'),
    ('unknown.zjcdn.com', '198.18.1.1'),
])
def test_private_or_unrelated_fake_dns_never_gets_fallback(network, host, address):
    network['system'] = address
    with pytest.raises(ValueError):
        with socket.socket() as sock:
            sock.connect((host, 443))
    assert network['requests'] == []
    assert network['connections'] == []


@pytest.mark.parametrize('address', ['127.0.0.1', '198.18.1.1', '10.0.0.1', '::ffff:127.0.0.1'])
def test_public_dns_cannot_authorize_private_answer(network, address):
    network['answer'] = address
    with pytest.raises(ValueError):
        with socket.socket() as sock:
            sock.connect_ex(('www.bilibili.com', 443))
    assert network['connections'] == []


def test_public_system_dns_keeps_existing_route(network):
    network['system'] = '1.1.1.1'
    assert socket.getaddrinfo('www.bilibili.com', 443, type=socket.SOCK_STREAM)[0][4] == ('1.1.1.1', 443)
    assert network['requests'] == []


def test_reserved_address_failure_is_not_a_platform_format_error():
    try:
        download.public_address('198.18.1.1')
    except ValueError as exc:
        message = download.safe_download_error(exc)
    assert '网络' in message and '保留' in message
