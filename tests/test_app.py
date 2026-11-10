import json
import time
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


class FakeExtractor:
    def extract(self, segments):
        # Test-only provider returns the real validated schema.
        from app.validation import validate_strategy
        raw = {"title": "测试草案", "asset": None, "timeframe": None, "rules": [{"kind": "buy", "text": segments[0].text, "evidence": [{"segment_id": segments[0].id, "quote": segments[0].text}]}], "questions": []}
        return validate_strategy(json.dumps(raw), segments)


def poll(client, job_id):
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "interrupted"): return job
        time.sleep(0.01)
    raise AssertionError("job timed out")


def test_import_edit_extract_persist_export(tmp_path):
    config = Settings(data_dir=tmp_path)
    app = create_app(config, extractor=FakeExtractor())
    with TestClient(app) as c:
        d = c.post("/api/documents/text", json={"title": "课程", "text": "原文买入"}).json()
        d = c.put(f'/api/documents/{d["id"]}/transcript', json={"revision": 1, "segments": [{"id": "s1", "text": "放量买入"}]}).json()
        assert d["revision"] == 2
        job = c.post(f'/api/documents/{d["id"]}/extract').json()
        assert poll(c, job["id"])["status"] == "succeeded"
        exported = c.get(f'/api/documents/{d["id"]}/export').json()
        assert exported["strategy"]["executable"] is False
        assert exported["strategy"]["rules"][0]["text"] == "放量买入"
        assert exported["transcript_revision"] == 2
        c.put(f'/api/documents/{d["id"]}/transcript', json={"revision": 2, "segments": [{"id": "s1", "text": "再次校对"}]})
        assert c.get(f'/api/documents/{d["id"]}').json()["strategy_stale"]
        assert c.get(f'/api/documents/{d["id"]}/export').status_code == 409
    with TestClient(create_app(config)) as c:
        assert c.get(f'/api/documents/{d["id"]}').json()["segments"][0]["text"] == "再次校对"


def test_unconfigured_failure_is_saved_and_retryable(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        d = c.post("/api/documents/text", json={"title": "a", "text": "买入"}).json()
        j = c.post(f'/api/documents/{d["id"]}/extract').json()
        j = poll(c, j["id"])
        assert j["status"] == "failed" and "未配置" in j["error"]
        assert c.post(f'/api/jobs/{j["id"]}/retry').status_code == 202
        assert "api_key" not in json.dumps(c.get("/api/status").json())


def test_recover_interrupted_job(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    app.state.store.init()
    d = app.state.store.create_document("a", "text", segments=[{"id": "s1", "text": "a", "start": None, "end": None}])
    app.state.store.create_job(d["id"], "extract")
    with TestClient(app) as c:
        jobs = c.get(f'/api/documents/{d["id"]}').json()["jobs"]
        assert jobs[0]["status"] == "interrupted"


def test_limits_csrf_revision_and_errors(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, max_upload_mb=1))) as c:
        assert c.post("/api/documents/text", json={"title": "a", "text": "a"}, headers={"Origin": "https://evil.org"}).status_code == 403
        assert c.get("/api/status", headers={"Host": "evil.org"}).status_code == 400
        assert c.get("/api/documents/missing").status_code == 404
        assert c.post("/api/documents/upload", files={"file": ("bad.exe", b"MZ")}).status_code == 400
        assert c.post("/api/documents/upload", files={"file": ("a.wav", b"x" * (1024 * 1024 + 1))}).status_code == 413
        d = c.post("/api/documents/text", json={"title": "a", "text": "a"}).json()
        assert c.put(f'/api/documents/{d["id"]}/transcript', json={"revision": 99, "segments": [{"id": "s1", "text": "b"}]}).status_code == 409


def test_subtitle_upload_and_media_cached_without_asr(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        subtitle = c.post('/api/documents/upload', files={'file': ('course.srt', '1\n00:00:01,000 --> 00:00:03,000\n原文'.encode('utf-8'))})
        assert subtitle.status_code == 202
        assert subtitle.json()['segments'][0]['start'] == 1
        media = c.post('/api/documents/upload', files={'file': ('course.wav', b'RIFF')}).json()
        assert media['jobs'] == []
        assert media['has_media'] and media['media_status'] == 'awaiting_transcription'
        assert c.post(f'/api/documents/{media["id"]}/transcribe').status_code == 409
        assert c.get(f'/api/documents/{media["id"]}').json()['segments'] == []


def test_no_blank_title(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        assert c.post('/api/documents/text', json={'title':'   ', 'text':'原文'}).status_code == 422
