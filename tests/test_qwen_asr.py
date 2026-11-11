import json
import os
import wave
import httpx
import pytest
from app.config import Settings
from app.asr.configuration import ASRConfiguration, ASRConfigInput
from app.adapters.qwen_asr import QwenASR, prepare_wav


@pytest.mark.skipif(os.name != 'nt', reason='production storage uses Windows DPAPI')
def test_separate_config_and_consent(tmp_path):
    settings = Settings(data_dir=tmp_path, ai_api_key='never-use-text-key')
    config = ASRConfiguration(settings)
    assert config.public()['provider'] == 'local'
    assert not config.public()['configured']
    with pytest.raises(ValueError, match='同意'):
        config.save(ASRConfigInput(provider='qwen', api_key='test-asr'))
    config.save(ASRConfigInput(provider='qwen', api_key='test-asr', cloud_enabled=True))
    assert config.current()['api_key'] == 'test-asr'
    assert 'test-asr' not in json.dumps(config.public())
    assert 'test-asr' not in config.path.read_text()
    with pytest.raises(ValueError, match='Key'):
        config.save(ASRConfigInput(provider='qwen', region='singapore', cloud_enabled=True))
    config.save(ASRConfigInput(provider='local'))
    assert config.current()['provider'] == 'local'


def test_async_contract_and_cached_result(tmp_path):
    calls = []
    def handle(request):
        calls.append(request)
        if request.url.path.endswith('/uploads'):
            assert request.url.params['model'] == 'qwen-audio-3.1-asr-flash-filetrans'
            return httpx.Response(200, json={'data':dict(upload_dir='test',upload_host='https://unit.oss-cn-beijing.aliyuncs.com',oss_access_key_id='upload-only',signature='sig',policy='policy',x_oss_object_acl='private',x_oss_forbid_overwrite='true')})
        if request.url.host.startswith('unit.'):
            assert 'authorization' not in request.headers
            return httpx.Response(200)
        if request.method == 'POST':
            body=json.loads(request.content)
            assert body['input']['file_urls'][0].startswith('oss://')
            assert body['input']['context'][0]['content'][0]['type']=='input_text'
            assert body['parameters']['vocabulary']['市盈率']==4
            assert request.headers['X-DashScope-Async']=='enable'
            return httpx.Response(200,json={'output':{'task_id':'test-task','task_status':'PENDING'}})
        if '/tasks/' in request.url.path:
            return httpx.Response(200,json={'output':{'task_status':'SUCCEEDED','results':[{'subtask_status':'SUCCEEDED','transcription_url':'https://result.oss-cn-beijing.aliyuncs.com/result'}]}})
        assert 'authorization' not in request.headers
        return httpx.Response(200,json={'transcripts':[{'sentences':[{'text':'市盈率二十倍','begin_time':120,'end_time':2300}]}]})
    config=dict(provider='qwen',model='qwen-audio-3.1-asr-flash-filetrans',region='beijing',workspace_id='',api_key='asr-only',cloud_enabled=True,finance_vocabulary=True,hotwords='',topic='估值')
    wav=tmp_path/'audio.wav';wav.write_bytes(b'fixture')
    adapter=QwenASR(config, tmp_path/'cache', client=httpx.Client(transport=httpx.MockTransport(handle)), poll_interval=0)
    result=adapter.transcribe(wav, '金融课程', prepared=True)
    assert result['segments'][0]['start']==.12
    assert result['segments'][0]['end']==2.3
    assert result['metadata']['model']==config['model']
    count=len(calls)
    assert adapter.transcribe(wav,'金融课程',prepared=True)==result
    assert len(calls)==count


def test_resume_timeout_and_refuse_duplicate_after_config_change(tmp_path):
    config = dict(provider='qwen', model='qwen-audio-3.1-asr-flash-filetrans', region='singapore', workspace_id='test-ws', api_key='fixture', cloud_enabled=True)
    media = tmp_path/'clip.wav'
    media.write_bytes(b'fixture')
    cache = tmp_path/'cache'
    cache.mkdir()
    import hashlib
    content = json.dumps({k:v for k,v in config.items() if k!='api_key'},sort_keys=True).encode()+b'titlefixture'
    (cache/'remote.json').write_text(json.dumps({'signature':hashlib.sha256(content).hexdigest(),'task_id':'existing-task'}))
    requests = []
    def handle(request):
        requests.append(request)
        assert request.url.host == 'test-ws.ap-southeast-1.maas.aliyuncs.com'
        assert request.method == 'GET' and request.url.path.endswith('/tasks/existing-task')
        return httpx.Response(200,json={'output':{'task_status':'RUNNING'}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        for _ in range(2):
            with pytest.raises(ValueError,match='超时'):
                QwenASR(config, cache, client=client, timeout=.1, poll_interval=.11).transcribe(media,'title',prepared=True)
        assert len(requests)==2
        with pytest.raises(ValueError,match='尚有未确认'):
            QwenASR({**config,'topic':'edited'},cache,client=client).transcribe(media,'title',prepared=True)
        assert len(requests)==2


def test_extracts_pcm_without_ffmpeg_executable(tmp_path):
    source, target = tmp_path/'source.wav', tmp_path/'audio.wav'
    with wave.open(str(source),'wb') as wav:
        wav.setparams((2,2,8000,0,'NONE','not compressed'))
        wav.writeframes(b'\x00\x20\x00\x20'*8000)
    prepare_wav(source,target,2)
    with wave.open(str(target),'rb') as wav:
        assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes()) == (1,2,16000,16000)


@pytest.mark.skipif(os.name != 'nt', reason='production storage uses Windows DPAPI')
def test_cloud_requires_manual_start_and_copy_preserves_evidence(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.jobs import Jobs
    from test_app import FakeExtractor, poll
    from test_local_media import wav_bytes
    settings = Settings(data_dir=tmp_path, ai_api_key='text-only')
    app = create_app(settings, extractor=FakeExtractor())
    actual = Jobs.worker
    calls=[]
    original = [{'id':'s1','text':'原始市盈率二十倍','start':.4,'end':2.1}]
    def worker(self,job,payload):
        if payload['operation']!='asr': return actual(self,job,payload)
        calls.append(payload)
        assert payload['asr_selection']['provider']=='qwen'
        assert 'test-qwen-secret' not in json.dumps(payload)
        if len(calls)==1: raise ValueError('Qwen测试超时')
        return {'segments':original,'metadata':{'provider':'qwen','model':'test-only'},'raw':{'fixture':True}}
    monkeypatch.setattr(Jobs,'worker',worker)
    with TestClient(app) as client:
        body={'provider':'qwen','api_key':'test-qwen-secret','cloud_enabled':True}
        response=client.put('/api/asr/config',json=body)
        assert response.status_code==200 and 'test-qwen-secret' not in response.text
        d=client.post('/api/documents/upload',files={'file':('sample.wav',wav_bytes())}).json()
        ident=d['id']
        assert d['jobs']==[] and calls==[]
        first=client.post(f'/api/documents/{ident}/transcribe').json()
        assert poll(client,first['id'])['status']=='failed'
    with TestClient(create_app(settings,extractor=FakeExtractor())) as client:
        retry=client.post(f"/api/jobs/{first['id']}/retry").json()
        assert poll(client,retry['id'])['status']=='succeeded'
        path=f'/api/documents/{ident}'
        d=client.get(path).json()
        corrected=[{**original[0],'text':'人工校对市盈率二十倍'}]
        d=client.put(path+'/transcript',json={'revision':d['revision'],'segments':corrected}).json()
        assert d['original_segments']==original
        extract=client.post(path+'/extract').json()
        assert poll(client,extract['id'])['status']=='succeeded'
        exported=client.get(path+'/export').json()
        copy=client.post(path+'/retranscribe-copy').json()
        assert copy['id']!=ident and copy['parent_document_id']==ident and copy['segments']==[] and copy['has_media']
        assert client.get(path+'/export').json()==exported
        assert client.get(f"/api/documents/{copy['id']}/media").content==wav_bytes()
        assert calls[0]['path']==calls[1]['path'] and len(calls)==2
