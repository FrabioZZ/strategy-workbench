"""Model transport regressions; no real provider calls or credentials."""
import json
import time
import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.client import complete
from app.config import Settings
from app.main import create_app


def configured(provider='deepseek'):
    return Settings(ai_provider=provider, ai_base_url='https://example.test/v1',
                    ai_model='deepseek-flash', ai_api_key='test-secret')


@pytest.mark.parametrize('failure,expected', [
    (httpx.ReadError('test-secret'), '连接中断'),
    (httpx.ReadTimeout('test-secret'), '超时'),
    (httpx.ConnectError('test-secret'), '无法连接'),
    (httpx.Response(200, text='test-secret'), '响应格式无效'),
])
def test_transport_failure_explains_actionable_cause_without_secrets(monkeypatch, failure, expected):
    original = httpx.Client
    def respond(request):
        if isinstance(failure, Exception):
            raise failure
        return failure
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    with pytest.raises(ValueError) as error:
        complete(configured(), [{'role': 'user', 'content': 'Return JSON.'}])
    message = str(error.value)
    assert expected in message
    assert 'test-secret' not in message
    if isinstance(failure, httpx.ReadError):
        assert '重试' in message


def sse_event(content=None, finish=None, **delta):
    if content is not None:
        delta['content'] = content
    return 'data: ' + json.dumps({'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}, ensure_ascii=False) + '\n\n'


def install_stream(monkeypatch, body):
    original = httpx.Client
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=body, headers={'content-type': 'text/event-stream'})
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    return requests


def test_deepseek_collects_complete_stream_without_using_reasoning(monkeypatch):
    calls = install_stream(monkeypatch, ': keep-alive\n\n' + sse_event(role='assistant') +
        sse_event(reasoning_content='内部思考不属于结果') + sse_event('{"title":') +
        sse_event('"策略"}') + sse_event(finish='stop') + 'data: [DONE]\n\n')
    raw = complete(configured(), [{'role': 'user', 'content': 'Return JSON.'}], schema={'type': 'object'})
    assert json.loads(raw) == {'title': '策略'}
    payload = json.loads(calls[0].content)
    assert payload['stream'] is True
    assert payload['response_format'] == {'type': 'json_object'}
    assert 'thinking' not in payload  # Preserve the user's selected model behavior.


@pytest.mark.parametrize('body', [
    sse_event('partial', finish='length') + 'data: [DONE]\n\n',
    sse_event('partial'),
    sse_event('partial', finish='stop'),
    sse_event('partial') + 'data: [DONE]\n\n',
    sse_event(reasoning_content='only reasoning', finish='stop') + 'data: [DONE]\n\n',
    'data: invalid-json\n\n',
    'data: {"error":{"message":"test-secret"}}\n\n',
    sse_event('x' * 1000001, finish='stop') + 'data: [DONE]\n\n',
])
def test_deepseek_never_accepts_incomplete_invalid_or_oversized_stream(monkeypatch, body):
    install_stream(monkeypatch, body)
    with pytest.raises(ValueError) as error:
        complete(configured(), [{'role': 'user', 'content': 'Return JSON.'}], schema={'type': 'object'})
    assert 'test-secret' not in str(error.value)


@pytest.mark.parametrize('complete_stream', [True, False])
def test_streamed_extraction_saves_only_validated_complete_draft(tmp_path, monkeypatch, complete_stream):
    text = '收盘价低于10元买入。'
    draft = {'title': '价格买入条件', 'asset': None, 'timeframe': None, 'questions': [],
             'rules': [{'kind': 'buy', 'text': text, 'evidence': [{'segment_id': 's1', 'quote': text}]}]}
    outputs = [{'changes': [], 'questions': []}, draft]
    original = httpx.Client
    class FragmentedStream(httpx.SyncByteStream):
        def __init__(self, body):
            self.body = body.encode('utf-8')
        def __iter__(self):
            for offset in range(0, len(self.body), 7):
                yield self.body[offset:offset + 7]
    def respond(request):
        payload = json.loads(request.content)
        assert payload['stream'] is True
        output = outputs.pop(0)
        body = ': keep-alive\n\n' + sse_event(json.dumps(output, ensure_ascii=False), finish='stop')
        if complete_stream or 'changes' in output:
            body += 'data: [DONE]\n\n'
        return httpx.Response(200, stream=FragmentedStream(body), headers={'content-type': 'text/event-stream'})
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    settings = configured()
    settings.data_dir = tmp_path
    with TestClient(create_app(settings), client=('127.0.0.1', 1234)) as client:
        doc = client.post('/api/documents/text', json={'title': '资料', 'text': text}).json()
        job = client.post('/api/documents/' + doc['id'] + '/extract').json()
        for _ in range(200):
            job = client.get('/api/jobs/' + job['id']).json()
            if job['status'] in ('succeeded', 'failed'):
                break
            time.sleep(.01)
        final = client.get('/api/documents/' + doc['id']).json()
        assert final['segments'] == doc['segments']
        if complete_stream:
            assert job['status'] == 'succeeded', job
            assert final['strategy']['rules'][0]['text'] == text
            assert final['strategy']['rules'][0]['evidence'][0]['transcript_version'] == 'corrected'
        else:
            assert job['status'] == 'failed'
            assert final['strategy'] is None
