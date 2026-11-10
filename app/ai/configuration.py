import base64
import ctypes
from ctypes import wintypes
from dataclasses import replace
import ipaddress
import json
import os
import threading
from urllib.parse import urlsplit, urlunsplit
from pydantic import Field, SecretStr
from app.models import StrictModel


PROVIDERS = [
    dict(id='openai', label='OpenAI', base_url='https://api.openai.com/v1', models=['gpt-5.2']),
    dict(id='deepseek', label='DeepSeek', base_url='https://api.deepseek.com', models=['deepseek-flash','deepseek-v4-pro']),
    dict(id='qwen', label='通义千问 Qwen（北京）', base_url='https://dashscope.aliyuncs.com/compatible-mode/v1', models=['qwen-plus']),
    dict(id='kimi', label='Kimi / Moonshot（国际站）', base_url='https://api.moonshot.ai/v1', models=['kimi-k3.1-pro','kimi-k2.6']),
    dict(id='glm', label='智谱 GLM', base_url='https://open.bigmodel.cn/api/paas/v4', models=['glm-5.3']),
    dict(id='custom', label='自定义 OpenAI 兼容接口', base_url='', models=[]),
    dict(id='ollama', label='本机 Ollama', base_url='http://127.0.0.1:11434', models=[]),
]


class ConfigInput(StrictModel):
    provider: str = Field(min_length=1, max_length=40)
    base_url: str = Field(min_length=1, max_length=1000)
    model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr | None = None


def is_loopback(host):
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or bool(getattr(address, 'ipv4_mapped', None) and address.ipv4_mapped.is_loopback)
    except ValueError:
        return False


def validate_base_url(value):
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or any(ch.isspace() for ch in value)
                or '\\' in value or '{' in value or '}' in value):
            raise ValueError()
        if parsed.scheme == 'http' and parsed.hostname != 'localhost' and not is_loopback(parsed.hostname):
            raise ValueError()
        host = parsed.hostname.lower()
        if ':' in host: host = '[' + host + ']'
        if port and port != (443 if parsed.scheme == 'https' else 80): host += ':' + str(port)
        return urlunsplit((parsed.scheme,host,parsed.path.rstrip('/'),'',''))
    except ValueError:
        raise ValueError('模型地址无效：远程接口须为 HTTPS，不能包含凭据、查询或片段；本机可用 HTTP。') from None


class DPAPI:
    """Windows current-user protection; UI forbidden, no machine-wide flag."""
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

    def _crypt(self, data, decrypt=False):
        if os.name != 'nt':
            raise ValueError('当前系统不支持 Windows DPAPI 安全存储，未保存 API Key。')
        buffer = ctypes.create_string_buffer(data)
        source = self.Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        target = self.Blob()
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if decrypt:
            fn = crypt.CryptUnprotectData
            fn.argtypes = [ctypes.POINTER(self.Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(self.Blob)]
            ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
        else:
            fn = crypt.CryptProtectData
            fn.argtypes = [ctypes.POINTER(self.Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(self.Blob)]
            ok = fn(ctypes.byref(source), 'quant-ai', None, None, None, 1, ctypes.byref(target))
        if not ok: raise ValueError('本机凭据加密或解密失败，请用保存时的 Windows 用户重新配置。')
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            kernel.LocalFree(target.pbData)

    def protect(self, value):
        return base64.b64encode(self._crypt(value.encode('utf-8'))).decode('ascii')

    def unprotect(self, value):
        try: return self._crypt(base64.b64decode(value, validate=True), decrypt=True).decode('utf-8')
        except (ValueError, UnicodeError):
            raise ValueError('本机凭据无法解密，请重新保存配置。') from None


class AIConfiguration:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.data_dir / 'ai-config.json'
        self.lock = threading.RLock()
        self.protector = DPAPI()

    def current(self):
        with self.lock:
            if not self.path.exists(): return replace(self.settings)
            try:
                record = json.loads(self.path.read_text(encoding='utf-8'))
                if record.get('disabled'):
                    return replace(self.settings, ai_provider='', ai_base_url='', ai_model='', ai_api_key='')
                return replace(self.settings, ai_provider=record['provider'], ai_base_url=validate_base_url(record['base_url']),
                               ai_model=record['model'], ai_api_key=self.protector.unprotect(record['protected_key']) if record.get('protected_key') else '')
            except (ValueError, KeyError, TypeError, OSError):
                raise ValueError('本机 AI 配置无法读取或解密，请重新填写配置。') from None

    def public(self):
        note = 'API Key 使用当前 Windows 用户的 DPAPI 加密，仅保存在本机；调用时发送给所选供应商。保存不代表连接已验证。'
        try: c = self.current()
        except ValueError as exc:
            c = replace(self.settings, ai_provider='', ai_base_url='', ai_model='', ai_api_key='')
            note = str(exc)
        return dict(providers=PROVIDERS, provider=c.ai_provider or '', base_url=c.ai_base_url,
                    model=c.ai_model, has_api_key=bool(c.ai_api_key), configured=c.ai_ready(), storage_note=note)

    def _write(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def save(self, body):
        with self.lock:
            if body.provider not in {p['id'] for p in PROVIDERS}: raise ValueError('不支持的供应商协议')
            url = validate_base_url(body.base_url)
            model = body.model.strip()
            if not model or any(ord(ch) < 32 for ch in model): raise ValueError('请填写有效模型 ID')
            key = body.api_key.get_secret_value().strip() if body.api_key else ''
            if len(key)>8192 or any(ord(ch)<33 or ord(ch)>126 for ch in key): raise ValueError('API Key 格式无效')
            if not key and body.provider != 'ollama':
                old = self.current()
                if old.ai_provider != body.provider or not old.ai_base_url or validate_base_url(old.ai_base_url) != url:
                    raise ValueError('供应商或地址已变化，请重新填写 API Key；不会复用旧凭据。')
                key = old.ai_api_key
            if body.provider != 'ollama' and not key: raise ValueError('请填写 API Key')
            self._write(dict(provider=body.provider, base_url=url, model=model,
                             protected_key=self.protector.protect(key) if key else ''))
            return self.public()

    def delete(self):
        with self.lock:
            self._write({'disabled': True})
            return self.public()
