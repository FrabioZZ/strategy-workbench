import json
import os
import re
import threading
from typing import Literal
from pydantic import Field, SecretStr
from app.models import StrictModel
from app.ai.configuration import DPAPI

MODEL = 'qwen-audio-3.1-asr-flash-filetrans'
FINANCE_WORDS = '市盈率 市净率 净资产收益率 现金流 资产负债率 毛利率 净利润 沪深300 中证500 均线 放量 缩量 止损 止盈 仓位 回撤 复权 涨停 跌停 换手率 成交量 MACD KDJ ETF'.split()


class ASRConfigInput(StrictModel):
    provider: Literal['local', 'qwen'] = 'local'
    model: Literal['qwen-audio-3.1-asr-flash-filetrans'] = MODEL
    region: Literal['beijing', 'singapore'] = 'beijing'
    workspace_id: str = Field(default='', max_length=80, pattern=r'^[a-zA-Z0-9-]*$')
    api_key: SecretStr | None = None
    cloud_enabled: bool = False
    finance_vocabulary: bool = True
    hotwords: str = Field(default='', max_length=2000)
    topic: str = Field(default='', max_length=200)


def vocabulary(config):
    words = (FINANCE_WORDS if config.get('finance_vocabulary', True) else []) + re.split(r'[,，、\s]+', config.get('hotwords', ''))
    return {w: 4 for w in words if w and len(w) <= 40}


def context_text(config, title):
    return (f"资料主题：{title}。{config.get('topic', '')}。参考词汇：" + '、'.join(vocabulary(config)))[:400]


class ASRConfiguration:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.data_dir / 'asr-config.json'
        self.protector = DPAPI()
        self.lock = threading.RLock()

    def current(self):
        with self.lock:
            try:
                record = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
                key = self.protector.unprotect(record.pop('protected_key')) if record.get('protected_key') else ''
                record.pop('protected_key', None)
                config = ASRConfigInput(**record).model_dump(exclude={'api_key'})
                return {**config, 'api_key': key}
            except (ValueError, TypeError, OSError):
                raise ValueError('ASR 配置无法读取或解密，请重新保存独立 ASR 配置。') from None

    def ready(self):
        try:
            c = self.current()
            return self.settings.asr_ready() if c['provider']=='local' else bool(c['cloud_enabled'] and c['api_key'])
        except ValueError:
            return False

    def public(self):
        error = ''
        try: c = self.current()
        except ValueError as exc:
            c = {**ASRConfigInput().model_dump(exclude={'api_key'}), 'api_key': ''}
            error = str(exc)
        key = c.pop('api_key')
        local = c['provider']=='local'
        ready = not error and (self.settings.asr_ready() if local else bool(c['cloud_enabled'] and key))
        local_note = '本地 faster-whisper，无需联网' if ready else '未配置本地 ASR 模型；可保存媒体，待配置后继续转写'
        return {**c, 'has_api_key':bool(key), 'configured':ready,
                'local_model': self.settings.asr_model and os.path.basename(self.settings.asr_model),
                'note': error or (local_note if local else f"Qwen / {c['model']} · {c['region']} · 需联网、上传音频及上下文，按 Token 计费；以百炼账单为准"),
                'storage_note':'独立 ASR Key 用当前 Windows 用户 DPAPI 加密；不复用文本 AI Key。保存配置不验证连接。临时 OSS 文件48小时有效，官方不推荐生产或高并发使用。'}

    def save(self, body):
        with self.lock:
            c = body.model_dump(exclude={'api_key'})
            key = body.api_key.get_secret_value().strip() if body.api_key else ''
            if key and (len(key)>8192 or any(ord(x)<33 or ord(x)>126 for x in key)):
                raise ValueError('ASR Key 格式无效')
            if body.provider=='qwen':
                if not body.cloud_enabled: raise ValueError('请明确同意上传音频、上下文和云端计费后保存')
                if not key:
                    old = self.current()
                    if any(old[k]!=c[k] for k in ('provider','region','workspace_id')):
                        raise ValueError('ASR 地域或空间已变化，请重新填写独立 Key')
                    key = old['api_key']
                if not key: raise ValueError('请填写独立 ASR Key')
            else:
                c['cloud_enabled'] = False
            c['protected_key'] = self.protector.protect(key) if body.provider=='qwen' else ''
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            try:
                temporary.write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
            return self.public()
