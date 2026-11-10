import json
import httpx
from app.ai.configuration import validate_base_url
from app.validation import _unique_pairs


def parse_json(raw):
    if not isinstance(raw, str) or len(raw)>200000: raise ValueError('模型 JSON 无效或过长')
    return json.loads(raw, object_pairs_hook=_unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('无效数值')))


def complete(settings, messages, schema=None, probe=False):
    c = settings
    if not c.ai_ready(): raise ValueError('AI 未配置：请在本机 AI 设置中选择供应商、模型并保存 API Key。')
    base = validate_base_url(c.ai_base_url)
    payload = dict(model=c.ai_model, messages=messages, stream=False)
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
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>1000000: raise ValueError('模型返回内容超出大小限制')
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
    except (httpx.HTTPError,KeyError,IndexError,TypeError,json.JSONDecodeError,UnicodeError):
        raise ValueError('模型连接失败、超时或响应格式无效；请检查本机 AI 设置。') from None
