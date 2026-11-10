"""Explicit test-only server. Never used by scripts/run.py or production configuration."""
import sys
import wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn
from app.config import Settings
from app.main import create_app
from test_app import FakeExtractor
from app.jobs import Jobs
from app.models import Segment

real_worker = Jobs.worker


def test_only_worker(self, job, payload):
    """No internet/model access. Real WAV fixture, explicit simulated metadata."""
    if payload['operation'] == 'probe':
        return real_worker(self, job, payload)
    if payload['operation'] == 'download':
        if 'Fail123' in payload['url']:
            raise ValueError('平台限制：测试专用下载失败，缓存尚未获取。')
        folder = Path(payload['folder']); folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'test-only.wav'
        with wave.open(str(path), 'wb') as out:
            out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\x00\x00' * 8000)
        return {'path': str(path), 'metadata': {'title':'测试专用平台音轨 P2', 'platform':'bilibili',
                'webpage_url':payload['url'], 'duration_seconds':1.0, 'media_type':'audio', 'size_bytes':16044}}
    marker = self.settings.data_dir / 'test-asr-first-failure'
    if not marker.exists():
        marker.touch()
        raise ValueError('本地转写失败：测试专用首次失败；缓存已保留。')
    return [{'id':'s1', 'start':0, 'end':1, 'text':'测试转写：价格突破20日均线买入。'}]

if __name__ == "__main__":
    config = Settings(data_dir=Path(sys.argv[1]), ai_provider="ollama", ai_base_url="http://127.0.0.1:1", ai_model="TEST-ONLY / 模拟提供方")
    # This file is never imported by the production entry point.
    Jobs.worker = test_only_worker
    app = create_app(config, extractor=FakeExtractor())
    @app.post('/__test__/local-fixtures')
    def local_fixtures():
        from test_local_media import wav_bytes, write_video
        folder = config.data_dir / 'fixtures'; folder.mkdir(exist_ok=True)
        audio = folder / 'local.wav'; audio.write_bytes(wav_bytes())
        write_video(folder / 'local.mp4')
        (folder / 'invalid.wav').write_bytes(b'invalid-media')
        store = app.state.store
        d = store.create_document('测试专用历史媒体', 'upload', media_path=str(audio))
        d = store.edit(d['id'], 1, [{'id':'s1', 'start':1, 'end':2, 'text':'历史校对原文：20日线买入。'}])
        store.save_strategy(d, FakeExtractor().extract([Segment(**d['segments'][0])]), 'test', 'TEST-ONLY')
        job = store.create_job(d['id'], 'transcribe')
        store.update_job(job['id'], 'succeeded', '历史转写完成')
        return store.document(d['id'])
    @app.post('/__test__/enable-asr')
    def enable_asr():
        model = config.data_dir / 'test-only-model-marker'; model.mkdir(exist_ok=True)
        (model / 'model.bin').touch()
        config.asr_model = str(model)
        return {'test_only': True}
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]) if len(sys.argv)>2 else 8766)
