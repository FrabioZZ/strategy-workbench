import json
import httpx
from app.ai.configuration import validate_base_url
from app.validation import _unique_pairs


def parse_json(raw):
    if not isinstance(raw, str) or len(raw)>200000: raise ValueError('模型 JSON 无效或过长')
    return json.loads(raw, object_pairs_hook=_unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('无效数值')))


def _deepseek_stream_content(response):
    """Read SSE through completion; reasoning is never used as the JSON result."""
    parts, data_lines = [], []
    finish, wire_size, text_size = None, 0, 0
    for line in response.iter_lines():
        wire_size += len(line.encode('utf-8')) + 1
        # SSE repeats the envelope for every token; bound that overhead separately.
        if wire_size > 64000000:
            raise ValueError('模型返回内容超出大小限制')
        if line.startswith('data:'):
            data_lines.append(line[5:].lstrip(' '))
        if line or not data_lines:
            continue
        raw = '\n'.join(data_lines)
        data_lines.clear()
        if raw == '[DONE]':
            if finish != 'stop':
                raise ValueError('模型输出被截断或拒绝，未采用结果。')
            return ''.join(parts)
        event = json.loads(raw)
        if not isinstance(event, dict) or 'error' in event:
            raise ValueError('模型流式响应无效或服务返回错误，请稍后重试；未采用结果。')
        choices = event['choices']
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError('模型流式响应格式无效，未采用结果。')
        for choice in choices:
            delta = choice['delta']
            if not isinstance(delta, dict) or choice.get('index', 0) != 0:
                raise ValueError('模型流式响应格式无效，未采用结果。')
            content = delta.get('content') or ''
            reasoning = delta.get('reasoning_content') or ''
            if not isinstance(content, str) or not isinstance(reasoning, str):
                raise ValueError('模型流式响应格式无效，未采用结果。')
            text_size += len(content.encode('utf-8')) + len(reasoning.encode('utf-8'))
            if text_size > 1000000:
                raise ValueError('模型返回内容超出大小限制')
            if finish is not None:
                raise ValueError('模型流式响应结束状态无效，未采用结果。')
            parts.append(content)
            finish = choice.get('finish_reason')
            if finish not in (None, 'stop'):
                raise ValueError('模型输出被截断或拒绝，未采用结果。')
    raise ValueError('模型响应未完整接收，连接中断；请稍后重试，未采用结果。')


def complete(settings, messages, schema=None, probe=False):
    c = settings
    if not c.ai_ready(): raise ValueError('AI 未配置：请在本机 AI 设置中选择供应商、模型并保存 API Key。')
    base = validate_base_url(c.ai_base_url)
    # DeepSeek's default thinking can leave non-streaming requests silent long
    # enough for an intermediary to close the connection. Consume its SSE while
    # preserving model behavior and validating only the final content.
    streaming = c.ai_provider == 'deepseek' and bool(schema) and not probe
    payload = dict(model=c.ai_model, messages=messages, stream=streaming)
    headers = {}
    if c.ai_provider == 'ollama':
        url = base + '/api/chat'
        if schema: payload['format'] = schema
        payload['options'] = {'temperature':0, **({'num_predict':32} if probe else {})}
    else:
        url = base + '/chat/completions'
        headers['Authorization'] = 'Bearer ' + c.ai_api_key
        if schema: payload['response_format'] = {'type':'json_object'}
        # Omit temperature: several reasoning models reject temperature=0.
        if probe: payload['max_completion_tokens' if c.ai_provider=='openai' else 'max_tokens'] = 512
    try:
        with httpx.Client(timeout=c.ai_timeout_seconds, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', url, json=payload, headers=headers) as response:
                response.raise_for_status()
                if streaming:
                    raw = _deepseek_stream_content(response)
                else:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body)>1000000: raise ValueError('模型返回内容超出大小限制')
        if not streaming:
            data = json.loads(body)
            if c.ai_provider == 'ollama':
                raw = data['message']['content']
            else:
                choice = data['choices'][0]
                if choice.get('finish_reason') not in (None, 'stop'):
                    raise ValueError('模型输出被截断或拒绝，未采用结果。')
                raw = choice['message']['content']
        if not isinstance(raw,str) or not raw.strip(): raise ValueError('模型未返回有效文本')
        return raw
    except httpx.HTTPStatusError as exc:
        raise ValueError(f'模型接口返回 HTTP {exc.response.status_code}，请检查模型名称、权限及接口兼容性。') from None
    except httpx.TimeoutException:
        raise ValueError('等待模型响应超时，请稍后重试；长资料可拆分后提取。') from None
    except httpx.ConnectError:
        raise ValueError('无法连接模型服务，请检查网络和本机 AI 接口地址后重试。') from None
    except (httpx.ReadError, httpx.RemoteProtocolError):
        raise ValueError('接收模型响应时连接中断，请稍后重试；本次未采用模型结果。') from None
    except httpx.HTTPError:
        raise ValueError('模型请求传输失败，请检查网络后重试。') from None
    except (KeyError,IndexError,TypeError,json.JSONDecodeError,UnicodeError):
        raise ValueError('模型响应格式无效，未收到兼容的完整回复；请检查接口兼容性后重试。') from None
