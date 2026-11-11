from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from app.config import ROOT
from app.models import Segment


class Jobs:
    def __init__(self, store, settings, extractor, asr_configuration=None):
        self.store, self.settings, self.extractor = store, settings, extractor
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-task")
        self.stop = threading.Event()
        self.probe_lock = threading.Lock()
        from app.asr.configuration import ASRConfiguration
        self.asr_configuration = asr_configuration or ASRConfiguration(settings)

    def automatic_asr(self):
        config = self.asr_configuration.public()
        return config['configured'] and config['provider'] == 'local'

    def inspect_cached_media(self, document_id):
        def needs_probe(document):
            metadata = document['media_metadata']
            return (document['has_media'] and metadata.get('media_type') not in ('audio', 'video')
                    and metadata.get('probe_status') != 'unavailable')

        document = self.store.document(document_id)
        if not needs_probe(document):
            return document
        # Serialize local probes without creating/replacing a user's download/ASR job.
        with self.probe_lock:
            document = self.store.document(document_id)
            if needs_probe(document):
                try:
                    result = self.worker({'id': 'probe-' + uuid.uuid4().hex},
                                         {'operation': 'probe', 'path': document['media_path'],
                                          'data_dir': str(self.settings.data_dir),
                                          'limit': self.settings.max_upload_mb * 1024 * 1024,
                                          'duration': self.settings.max_duration_seconds})
                except Exception:
                    result = {'probe_status': 'unavailable'}
                self.store.supplement_media_metadata(document_id, document['media_path'], result)
            return self.store.document(document_id)

    def submit(self, document_id, kind, *, local_only=False):
        asr = None
        if kind == 'transcribe':
            document = self.store.document(document_id)
            if any(j['status'] in ('queued', 'running') for j in document['jobs']):
                raise ValueError('已有任务正在执行，请等待完成')
            if not document['has_media']:
                raise ValueError('尚无已缓存媒体，请先完成下载或重新上传文件。')
            if document['segments']:
                raise ValueError('已有转写内容，请继续校对；不会覆盖已保存的原文。')
            asr = self.asr_configuration.public()
            if local_only and asr['provider'] != 'local':
                return None
            if not asr['configured']:
                if local_only:
                    return None
                raise ValueError('媒体已获取，待转写。请在运行配置中设置本地模型或独立 Qwen ASR 凭据。')
        job = self.store.create_job(document_id, kind)
        self.pool.submit(self.run, job, asr)
        return job

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=True, cancel_futures=True)

    def worker(self, job, payload):
        folder = self.settings.data_dir / "tasks" / job["id"]
        folder.mkdir(parents=True, exist_ok=True)
        request, output = folder / "request.json", folder / "result.json"
        request.write_text(json.dumps(payload), encoding="utf-8")
        # Media processes need no model-provider secrets.
        env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
        env.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        process = subprocess.Popen([sys.executable, "-m", "app.media_worker", str(request), str(output)],
                                   cwd=ROOT, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=env, **kwargs)
        timeout = self.settings.task_timeout_seconds
        if payload['operation'] == 'probe':
            timeout = min(timeout, 30)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if self.stop.wait(0.25) or time.monotonic() > deadline:
                    raise ValueError("媒体任务中断或超时，请拆分文件后重试")
            if process.returncode or not output.is_file():
                raise ValueError("媒体进程未能完成，请检查运行环境后重试")
            result = json.loads(output.read_text(encoding="utf-8"))
            if not result["ok"]:
                raise ValueError(result["error"])
            return result["result"]
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            request.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            if payload.get('cache'):
                (Path(payload['cache'])/'audio.wav').unlink(missing_ok=True)

    def run(self, job, selected_asr=None):
        s, c = self.store, self.settings
        try:
            if self.stop.is_set():
                return
            s.update_job(job["id"], "running", "准备处理")
            document = s.document(job["document_id"])
            if job["kind"] == "extract":
                s.update_job(job["id"], "running", "检查转写、校正并提取命名策略")
                segments = [Segment(**seg) for seg in document['segments']]
                if hasattr(self.extractor, 'extract_reviewed'):
                    result = self.extractor.extract_reviewed(segments)
                    s.save_strategy(document, result['strategy'], result['provider'], result['model'],
                                    corrected_segments=result['corrected_segments'], ai_review=result['ai_review'])
                else:
                    result = self.extractor.extract(segments)
                    s.save_strategy(document, result, c.ai_provider or 'test', c.ai_model or 'test-only')
            elif job['kind'] == 'download':
                if not document['has_media']:
                    s.update_job(job['id'], 'running', '正在获取平台媒体')
                    result = self.worker(job, {'operation': 'download', 'url': document['source_url'],
                                              'folder': str(c.data_dir / 'media' / document['id'] / job['id']),
                                              'limit': c.max_upload_mb * 1024 * 1024, 'duration': c.max_duration_seconds})
                    s.set_media(document['id'], result['path'], result['metadata'])
                document = s.document(document['id'])
                if document['segments']:
                    s.update_job(job['id'], 'succeeded', '媒体已获取，保留已有转写')
                    return
                if not self.automatic_asr():
                    s.update_job(job['id'], 'succeeded', '媒体已获取，待转写（请配置 ASR；云服务需手动开始）')
                    return
                if self.stop.is_set():
                    raise ValueError('任务已中断，缓存已保留，可重试转写。')
                # Commit the finished download and queued ASR together. A reader
                # must never see "no active job" between these two stages.
                from app.store import now
                next_id, timestamp = uuid.uuid4().hex, now()
                with s.connect() as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    connection.execute("UPDATE jobs SET status='succeeded',stage=?,error=NULL,updated_at=? WHERE id=?",
                                       ('媒体已获取，已接续转写', timestamp, job['id']))
                    connection.execute("INSERT INTO jobs VALUES (?,?,'transcribe','queued',?,NULL,?,?)",
                                       (next_id, document['id'], '媒体已获取，等待本地转写', timestamp, timestamp))
                # Continue on the same serialized worker; no executor-submission
                # race with shutdown, and retry keeps the distinct ASR job kind.
                self.run(s.job(next_id), {'provider':'local'})
                if s.job(next_id)['status'] == 'queued':
                    s.update_job(next_id, 'interrupted', '任务中断', '转写未开始，缓存已保留，可重试。')
                return
            elif job['kind'] == 'transcribe':
                asr = self.asr_configuration.public()
                if not asr['configured'] or any(asr.get(k) != v for k,v in (selected_asr or {}).items()):
                    raise ValueError('ASR 配置已变化或不可用。请核对设置后，使用缓存重新开始转写。')
                path = document["media_path"]
                if not path or not Path(path).is_file():
                    raise ValueError('缓存媒体不存在，请重新导入资料；转写重试不会重新下载。')
                s.update_job(job["id"], "running", f"语音转写中：{asr['provider']} / {asr['model'] if asr['provider']=='qwen' else asr['local_model']}")
                result = self.worker(job, {"operation": "asr", "path": path, 'title':document['title'],
                                            'asr_selection':{k:asr[k] for k in ('provider','model','region','workspace_id','cloud_enabled','finance_vocabulary','hotwords','topic')},
                                            'cache':str(c.data_dir/'asr-cache'/document['id']),
                                            "settings": {'data_dir':str(c.data_dir), "asr_model": c.asr_model, "asr_device": c.asr_device,
                                                         "asr_compute_type": c.asr_compute_type, "max_duration_seconds": c.max_duration_seconds}})
                s.set_transcript(document["id"], result['segments'] if isinstance(result,dict) else result,
                                 result.get('metadata') if isinstance(result,dict) else None,
                                 result.get('raw') if isinstance(result,dict) else None)
            else:
                raise ValueError('不支持的任务类型')
            s.update_job(job["id"], "succeeded", "处理完成")
        except Exception as exc:
            # Never relay raw third-party exceptions (URLs/keys/paths may be included).
            message = str(exc) if isinstance(exc, ValueError) else "任务失败，请检查配置或输入后重试。"
            stage = {'download': '媒体获取失败', 'transcribe': '转写失败（缓存已保留）', 'extract': '策略提取失败'}.get(job['kind'], '处理失败')
            s.update_job(job["id"], "interrupted" if self.stop.is_set() else "failed", "任务中断" if self.stop.is_set() else stage, message)
