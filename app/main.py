from contextlib import asynccontextmanager
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
from app.adapters.download import extract_shared_url
from app.adapters.extractor import Extractor
from app.ai.configuration import AIConfiguration
from app.asr.configuration import ASRConfiguration, ASRConfigInput
from app.ai.router import router as ai_router
from app.config import Settings, ROOT
from app.jobs import Jobs
from app.models import TextImport, UrlImport, TranscriptUpdate
from app.store import Store
from app.validation import parse_transcript
from app.trading.store import TradingStore
from app.trading.service import TradingService
from app.trading.router import router as trading_router
from app.trading.worker import PaperWorker
from app.trading.paper_service import PaperService
from app.trading.paper_router import router as external_paper_router
from app.trading.quotes import QuoteService
from app.trading.quote_accounts import QuoteAccounts, QuoteWorker
from app.trading.quote_router import router as quote_router


def public_document(document):
    return {k: v for k, v in document.items() if k not in ('media_path', 'asr_raw')}


class BodyLimitMiddleware:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.limit if scope["path"] == "/api/documents/upload" else 2 * 1024 * 1024
        total = 0

        async def bounded_receive():
            nonlocal total
            msg = await receive()
            total += len(msg.get("body", b""))
            if total > limit:
                raise HTTPException(413, "请求超过大小限制")
            return msg
        await self.app(scope, bounded_receive, send)


def create_app(settings=None, extractor=None):
    config = settings or Settings.from_env()
    config.data_dir = Path(config.data_dir).resolve()
    store = Store(config.data_dir)
    ai_configuration = AIConfiguration(config)
    asr_configuration = ASRConfiguration(config)
    trading_store = TradingStore(config.data_dir)
    trading_service = TradingService(trading_store, store)
    external_paper = PaperService(trading_store, store)
    quotes = QuoteService()
    quote_accounts = QuoteAccounts(trading_store, quotes)

    @asynccontextmanager
    async def lifespan(app):
        store.init()
        store.recover()
        app.state.jobs = Jobs(store, config, extractor or Extractor(ai_configuration), asr_configuration)
        trading_store.init()
        external_paper.recover()
        app.state.paper_worker = PaperWorker(trading_service)
        app.state.quote_worker = QuoteWorker(quote_accounts)
        try:
            yield
        finally:
            app.state.quote_worker.close()
            app.state.paper_worker.close()
            app.state.jobs.close()

    app = FastAPI(title="策略拾录", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.settings = store, config
    app.state.ai_configuration = ai_configuration
    app.state.asr_configuration = asr_configuration
    app.state.trading_service = trading_service
    app.state.external_paper = external_paper
    app.state.quotes, app.state.quote_accounts = quotes, quote_accounts
    app.include_router(trading_router(trading_service))
    app.include_router(external_paper_router(external_paper))
    app.include_router(quote_router(quote_accounts))
    app.include_router(ai_router(ai_configuration, store))
    app.add_middleware(BodyLimitMiddleware, limit=(config.max_upload_mb + 1) * 1024 * 1024)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
            p = urlsplit(origin)
            if p.scheme not in ("http", "https") or p.netloc != request.headers.get("host"):
                return JSONResponse({"detail": "拒绝跨站操作，请从本地工作台访问"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site" and request.method not in ("GET", "HEAD", "OPTIONS"):
            return JSONResponse({"detail": "拒绝跨站操作"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse({"detail": "资料或任务不存在"}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "输入格式或长度不符合要求，请检查必填项、时间与文本长度。"}, status_code=422)

    @app.get("/api/status")
    def status():
        public = config.public()
        ai = ai_configuration.public()
        public.update(ai_configured=ai['configured'], ai_provider=ai['provider'] or None,
                      ai_model=ai['model'] or None,
                      ai_note='配置已填写，连接尚未验证' if ai['configured'] else ai['storage_note'])
        asr = asr_configuration.public()
        public.update(asr_configured=asr['configured'], asr_provider=asr['provider'],asr_model=asr['model'] if asr['provider']=='qwen' else asr['local_model'],asr_note=asr['note'])
        return public

    @app.get('/api/asr/config')
    def asr_config():
        return asr_configuration.public()

    @app.put('/api/asr/config')
    def save_asr_config(body: ASRConfigInput):
        try: return asr_configuration.save(body)
        except ValueError as exc: raise HTTPException(400, str(exc)) from None

    @app.post('/api/documents/{ident}/retranscribe-copy', status_code=201)
    def retranscribe_copy(ident: str):
        try: return public_document(store.retranscription_copy(ident))
        except ValueError as exc: raise HTTPException(409,str(exc)) from None

    @app.get("/api/documents")
    def documents():
        return store.list_documents()

    @app.post("/api/documents/text", status_code=201)
    def import_text(body: TextImport):
        try:
            segments = parse_transcript(body.text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return public_document(store.create_document(body.title, "text", segments=[s.model_dump() for s in segments], is_demo=body.is_demo))

    @app.post("/api/documents/url", status_code=202)
    def import_url(body: UrlImport):
        try:
            url = extract_shared_url(body.url)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        document = store.create_document(body.title, "url", source_url=url)
        app.state.jobs.submit(document["id"], "download")
        return public_document(store.document(document["id"]))

    @app.post("/api/documents/upload", status_code=202)
    async def upload(file: UploadFile = File(...), title: str = Form("")):
        suffix = Path(file.filename or "").suffix.lower()
        text_file = suffix in {".txt", ".srt", ".vtt"}
        if suffix not in {".mp4", ".mkv", ".mov", ".webm", ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".txt", ".srt", ".vtt"}:
            await file.close()
            raise HTTPException(400, "不支持此类型，请上传音视频、TXT、SRT或VTT")
        title = (title.strip() or Path(file.filename or "本地资料").name)[:120]
        folder = config.data_dir / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}{suffix}"
        total = 0
        try:
            with path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > (512000 if text_file else config.max_upload_mb * 1024 * 1024):
                        raise HTTPException(413, "文件超过大小限制，请拆分后上传")
                    target.write(chunk)
            if total == 0:
                raise HTTPException(400, "文件为空")
            if text_file:
                try:
                    segments = parse_transcript(path.read_text(encoding="utf-8-sig"))
                except (ValueError, UnicodeError):
                    raise HTTPException(400, "字幕/文本格式无效，请使用UTF-8编码的TXT、SRT或VTT") from None
                document = store.create_document(title, "subtitle", segments=[s.model_dump() for s in segments])
                path.unlink()
            else:
                document = store.create_document(title, "upload", media_path=str(path))
                await run_in_threadpool(app.state.jobs.inspect_cached_media, document['id'])
                app.state.jobs.submit(document['id'], 'transcribe', local_only=True)
            return public_document(store.document(document["id"]))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get("/api/documents/{ident}")
    def document(ident: str):
        return public_document(app.state.jobs.inspect_cached_media(ident))

    @app.put("/api/documents/{ident}/transcript")
    def edit(ident: str, body: TranscriptUpdate):
        store.document(ident)
        try:
            return public_document(store.edit(ident, body.revision, [s.model_dump() for s in body.segments]))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post("/api/documents/{ident}/extract", status_code=202)
    def extract(ident: str):
        document = store.document(ident)
        if not document["segments"]:
            raise HTTPException(400, "尚无转写，请先完成语音转写或导入文本")
        try:
            return app.state.jobs.submit(ident, "extract")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post('/api/documents/{ident}/transcribe', status_code=202)
    def transcribe(ident: str):
        store.document(ident)
        try:
            return app.state.jobs.submit(ident, 'transcribe')
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/jobs/{ident}")
    def job(ident: str):
        return store.job(ident)

    @app.post("/api/jobs/{ident}/retry", status_code=202)
    def retry(ident: str):
        job = store.job(ident)
        if job["status"] not in ("failed", "interrupted"):
            raise HTTPException(409, "仅失败或中断任务可以重试")
        try:
            return app.state.jobs.submit(job["document_id"], job["kind"])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/documents/{ident}/export")
    def export(ident: str):
        document = store.document(ident)
        if not document["strategy"] or document["strategy_stale"]:
            raise HTTPException(409, "尚无当前转写版本的策略草案，请先提取")
        payload = {"schema_version": "1.0", "document_id": ident, "title": document["title"],
                   "source_type": document["source_type"], "source_url": document["source_url"],
                   "media_metadata": document['media_metadata'],
                   'parent_document_id':document['parent_document_id'], 'asr_metadata':document['asr_metadata'],
                   'original_asr_transcript':document['original_segments'],
                   "is_demo": document["is_demo"], "transcript_revision": document["revision"],
                   "transcript": document["segments"], "strategy": document["strategy"],
                   "corrected_transcript": document['corrected_segments'], "ai_review": document['ai_review'],
                   "evidence_transcript_version": document['strategy'].get('transcript_version','original'),
                   "provider": document["strategy_provider"], "model": document["strategy_model"],
                   "created_at": document["strategy_created_at"]}
        return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="strategy-{ident}.json"'})

    @app.get("/api/documents/{ident}/media")
    def media(ident: str):
        document = store.document(ident)
        path = Path(document["media_path"]) if document["media_path"] else None
        if not path or not path.is_file() or not path.resolve().is_relative_to(config.data_dir):
            raise HTTPException(404, "尚无本地媒体")
        return FileResponse(path)

    app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    @app.get("/api/docs", include_in_schema=False)
    def api_docs():
        return FileResponse(ROOT / "frontend" / "api.html")

    return app
