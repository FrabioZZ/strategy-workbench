"""Qwen file HTTP contract. Never log credentials, policy or signed URLs."""
import hashlib
import json
import re
import time
import wave
import uuid
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from app.models import Segment
from app.asr.configuration import vocabulary, context_text


def trusted_oss(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or not p.hostname.endswith('.aliyuncs.com') or '.oss-' not in p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('云端存储地址不符合预期，已停止请求。')
    return url


def prepare_wav(path, output, duration):
    import av
    count = 0
    with av.open(str(path)) as source, wave.open(str(output), 'wb') as target:
        if not source.streams.audio: raise ValueError('媒体中没有音频轨道')
        if source.duration is None or source.duration / av.time_base > duration:
            raise ValueError('无法确认媒体时长或超过时长上限，请拆分后重试')
        target.setnchannels(1); target.setsampwidth(2); target.setframerate(16000)
        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
        def write(frames):
            nonlocal count
            for frame in frames:
                count += frame.samples
                if count > duration*16000: raise ValueError('音轨超过时长上限')
                target.writeframes(frame.to_ndarray().tobytes())
        for frame in source.decode(audio=0): write(resampler.resample(frame))
        write(resampler.resample(None))
    if not count: raise ValueError('音轨为空')


class QwenASR:
    def __init__(self, config, cache, client=None, poll_interval=3, timeout=3300, duration=7200):
        self.c, self.cache = config, Path(cache)
        self.client = client
        self.interval, self.timeout, self.duration = poll_interval, timeout, duration
        region = 'cn-beijing' if config['region']=='beijing' else 'ap-southeast-1'
        host = f"{config['workspace_id']}.{region}.maas.aliyuncs.com" if config.get('workspace_id') else ('dashscope.aliyuncs.com' if config['region']=='beijing' else 'dashscope-intl.aliyuncs.com')
        self.base = 'https://' + host + '/api/v1'
        self.headers = {'Authorization':'Bearer '+config['api_key']}

    def transcribe(self, path, title, prepared=False):
        if self.c.get('provider')!='qwen' or not self.c.get('cloud_enabled') or not self.c.get('api_key'):
            raise ValueError('请先明确配置独立 Qwen ASR 凭据和上传同意')
        self.cache.mkdir(parents=True, exist_ok=True)
        own = self.client is None
        client = self.client or httpx.Client(timeout=60, follow_redirects=False)
        try:
            return self._run(client, Path(path), title, prepared)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise ValueError(f'Qwen ASR HTTP {status}：请检查独立Key、地域、额度或网络；缓存已保留。') from None
        except (httpx.HTTPError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
            raise ValueError('Qwen ASR 网络或响应异常，缓存已保留。重试会优先查询已提交任务；提交结果不明时不会自动重复提交。') from None
        finally:
            if own: client.close()
            (self.cache/'audio.wav').unlink(missing_ok=True)

    def _run(self, client, path, title, prepared):
        signature = hashlib.sha256(json.dumps({k:v for k,v in self.c.items() if k!='api_key'},sort_keys=True).encode()+title.encode())
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024), b''): signature.update(chunk)
        folder = self.cache/signature.hexdigest(); folder.mkdir(exist_ok=True)
        state_path, result_path = self.cache/'remote.json', folder/'result.json'
        def save(p, data):
            temp=p.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temp.replace(p)
        if result_path.exists(): return json.loads(result_path.read_text(encoding='utf-8'))
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state and state.get('signature') != folder.name:
            raise ValueError('Qwen配置或媒体已变化，尚有未确认的远端任务。请恢复原配置后重试查询，或核对控制台后创建副本。')
        if state.get('uncertain'):
            raise ValueError('上次提交结果不明：为避免重复计费已停止自动重提，请先在百炼控制台核对任务，再新建转写副本。')
        if not state.get('task_id'):
            audio = path if prepared else self.cache/'audio.wav'
            if not prepared: prepare_wav(path,audio,self.duration)
            response=client.get(self.base+'/uploads',params={'action':'getPolicy','model':self.c['model']},headers=self.headers)
            response.raise_for_status(); policy=response.json()['data']
            filename=uuid.uuid4().hex+'.wav'
            key=policy['upload_dir']+'/'+filename
            fields={'OSSAccessKeyId':policy['oss_access_key_id'],'Signature':policy['signature'],'policy':policy['policy'], 'x-oss-object-acl':policy['x_oss_object_acl'],'x-oss-forbid-overwrite':policy['x_oss_forbid_overwrite'],'key':key,'success_action_status':'200'}
            with audio.open('rb') as f:
                response=client.post(trusted_oss(policy['upload_host']),files={**{k:(None,v) for k,v in fields.items()},'file':(filename,f,'audio/wav')})
            response.raise_for_status()
            payload={'model':self.c['model'],'input':{'file_urls':['oss://'+key], 'context':[{'role':'user','content':[{'type':'input_text','text':context_text(self.c,title)}]}]},'parameters':{'channel_id':[0], 'vocabulary':vocabulary(self.c)}}
            save(state_path,{'uncertain':True,'signature':folder.name})
            response=client.post(self.base+'/services/audio/asr/transcription',json=payload,headers={**self.headers,'X-DashScope-Async':'enable','X-DashScope-OssResourceResolve':'enable'})
            # Explicit client rejection means no task; timeout/5xx remains ambiguous.
            if 400<=response.status_code<500: state_path.unlink(missing_ok=True)
            response.raise_for_status()
            task=response.json()['output']['task_id']
            if not re.fullmatch(r'[A-Za-z0-9-]{1,100}',task): raise ValueError('Qwen任务编号格式异常，请在控制台核对任务')
            state={'task_id':task,'signature':folder.name};save(state_path,state)
        deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            response=client.get(self.base+'/tasks/'+state['task_id'],headers=self.headers);response.raise_for_status()
            output=response.json()['output']; status=output['task_status']
            if status=='SUCCEEDED':
                results=output['results']
                if len(results)!=1 or results[0]['subtask_status']!='SUCCEEDED':
                    state_path.unlink(missing_ok=True)
                    raise ValueError('Qwen子任务失败，可检查配置后重试（会重新提交并可能计费）。')
                response=client.get(trusted_oss(results[0]['transcription_url']));response.raise_for_status()
                raw=response.json();segments=[]
                for transcript in raw['transcripts']:
                    for sentence in transcript['sentences']:
                        if not sentence['text'].strip(): continue
                        seg=Segment(id=f's{len(segments)+1}',text=sentence['text'].strip(),start=sentence['begin_time']/1000,end=sentence['end_time']/1000)
                        if seg.end>self.duration or len(segments)>=3000: raise ValueError('云转写超过时长或段落限制')
                        segments.append(seg.model_dump())
                if not segments or sum(len(s['text']) for s in segments)>120000: raise ValueError('云转写为空或超过文本上限')
                result={'segments':segments,'metadata':{'provider':'qwen','model':self.c['model'],'region':self.c['region'],'task_id':state['task_id'],'context':context_text(self.c,title),'vocabulary':vocabulary(self.c)},'raw':{'properties':raw.get('properties',{}),'transcripts':raw['transcripts']}}
                save(result_path,result)
                state_path.unlink(missing_ok=True)
                return result
            if status in ('FAILED','CANCELED','UNKNOWN'):
                if status!='UNKNOWN': state_path.unlink(missing_ok=True)
                raise ValueError('Qwen任务失败、取消或已过期，请核对控制台。已保留媒体缓存；失败后重试可能重新计费。')
            if status not in ('PENDING','RUNNING'): raise ValueError('Qwen返回未知任务状态，已停止轮询')
            time.sleep(self.interval)
        raise ValueError('Qwen转写等待超时；缓存和远端任务编号已保存，点击重试继续查询，不会自动重提。')
