import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

from app.strategy_names import unique_strategy_name


MAX_DRAFT_TITLE_LENGTH = 120


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, folder):
        self.folder = folder
        self.path = folder / "workspace.sqlite3"

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def init(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, source_type TEXT NOT NULL,
                source_url TEXT, media_path TEXT, is_demo INTEGER DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 1, segments TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(document_id)
                WHERE status IN ('queued', 'running');
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                revision INTEGER NOT NULL, result TEXT NOT NULL, transcript TEXT NOT NULL,
                provider TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
            c.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in c.execute('PRAGMA table_info(documents)')}
            if 'media_metadata' not in columns:
                c.execute("ALTER TABLE documents ADD COLUMN media_metadata TEXT NOT NULL DEFAULT '{}'")
            for column, declaration in (('parent_document_id','TEXT'), ('asr_metadata',"TEXT NOT NULL DEFAULT '{}'"), ('original_segments',"TEXT NOT NULL DEFAULT '[]'"), ('asr_raw',"TEXT NOT NULL DEFAULT '{}'")):
                if column not in columns:
                    c.execute(f'ALTER TABLE documents ADD COLUMN {column} {declaration}')
            if 'deleted_at' not in columns:
                c.execute('ALTER TABLE documents ADD COLUMN deleted_at TEXT')
            strategy_columns = {r['name'] for r in c.execute('PRAGMA table_info(strategies)')}
            for column in ('corrected_transcript', 'ai_review', 'ai_mapping'):
                if column not in strategy_columns:
                    c.execute(f'ALTER TABLE strategies ADD COLUMN {column} TEXT')
            if 'display_title' not in strategy_columns:
                c.execute('ALTER TABLE strategies ADD COLUMN display_title TEXT')
                self._backfill_strategy_titles(c)

    @staticmethod
    def _backfill_strategy_titles(connection):
        rows = connection.execute('''SELECT s.id,s.result,d.title AS source_title
            FROM strategies s JOIN documents d ON d.id=s.document_id ORDER BY s.created_at,s.rowid''')
        titles = [(row['id'], (json.loads(row['result']).get('title') or '').strip() or row['source_title'])
                  for row in rows]
        # Reserve literal names first so a duplicate never takes an existing name with a suffix.
        occupied = {title.casefold() for _, title in titles}
        seen = set()
        for ident, title in titles:
            key = title.casefold()
            display = unique_strategy_name(title, occupied, MAX_DRAFT_TITLE_LENGTH) if key in seen else title
            connection.execute('UPDATE strategies SET display_title=? WHERE id=?', (display, ident))
            seen.add(key)

    def recover(self):
        with self.connect() as c:
            c.execute("UPDATE jobs SET status='interrupted',stage='任务中断',error=?,updated_at=? WHERE status IN ('running','queued')",
                      ("服务已重启，上次任务未完成。可点击重试。", now()))

    def create_document(self, title, source_type, segments=None, source_url=None, media_path=None, is_demo=False):
        ident = uuid.uuid4().hex
        with self.connect() as c:
            c.execute("INSERT INTO documents(id,title,source_type,source_url,media_path,is_demo,segments,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (ident, title.strip(), source_type, source_url, media_path, int(is_demo), json.dumps(segments or [], ensure_ascii=False), now(), now()))
        return self.document(ident)

    def document(self, ident):
        with self.connect() as c:
            row = c.execute('''SELECT d.*, EXISTS (
                SELECT 1 FROM documents parent
                WHERE parent.id=d.parent_document_id AND parent.deleted_at IS NOT NULL
            ) AS parent_document_deleted
                FROM documents d WHERE d.id=? AND d.deleted_at IS NULL''', (ident,)).fetchone()
            if not row:
                raise KeyError("资料不存在")
            result = dict(row)
            result.pop('deleted_at')
            result['parent_document_deleted'] = bool(result['parent_document_deleted'])
            result["segments"] = json.loads(result["segments"])
            result['media_metadata'] = json.loads(result['media_metadata'])
            for column in ('asr_metadata','original_segments','asr_raw'):
                result[column] = json.loads(result[column])
            result['has_media'] = bool(result['media_path'] and Path(result['media_path']).is_file())
            result["is_demo"] = bool(result["is_demo"])
            jobs = c.execute("SELECT * FROM jobs WHERE document_id=? ORDER BY created_at DESC", (ident,)).fetchall()
            result["jobs"] = [dict(j) for j in jobs]
            media_job = next((j for j in result['jobs'] if j['kind'] in ('download', 'transcribe')), None)
            if media_job and media_job['status'] in ('queued', 'running'):
                result['media_status'] = 'downloading' if media_job['kind'] == 'download' else 'transcribing'
            elif result['segments']:
                result['media_status'] = 'transcribed'
            elif media_job and media_job['status'] in ('failed', 'interrupted'):
                result['media_status'] = 'transcription_failed' if result['has_media'] else 'download_failed'
            else:
                result['media_status'] = 'awaiting_transcription' if result['has_media'] else 'not_acquired'
            strategy = c.execute("SELECT * FROM strategies WHERE document_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (ident,)).fetchone()
            result["strategy"] = json.loads(strategy["result"]) if strategy else None
            if strategy:
                result['strategy']['title'] = strategy['display_title']
            result["strategy_id"] = strategy["id"] if strategy else None
            result["strategy_revision"] = strategy["revision"] if strategy else None
            result["strategy_stale"] = bool(strategy and strategy["revision"] != result["revision"])
            result["strategy_provider"] = strategy["provider"] if strategy else None
            result["strategy_model"] = strategy["model"] if strategy else None
            result["strategy_created_at"] = strategy["created_at"] if strategy else None
            result['ai_review'] = json.loads(strategy['ai_review']) if strategy and strategy['ai_review'] else None
            result['corrected_segments'] = json.loads(strategy['corrected_transcript']) if strategy and strategy['corrected_transcript'] else None
            result['ai_mapping'] = json.loads(strategy['ai_mapping']) if strategy and strategy['ai_mapping'] else None
            if result['ai_review']:
                result['ai_review']['stale'] = result['strategy_stale']
        return result

    def list_documents(self):
        with self.connect() as c:
            rows = c.execute('''SELECT id,title,source_type,is_demo,revision,created_at,updated_at
                FROM documents WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 500''')
            return [dict(row) for row in rows]

    def delete_document(self, ident):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM jobs WHERE document_id=? AND status IN ('queued','running')", (ident,)).fetchone():
                raise ValueError('任务执行中，完成后再删除资料')
            # Existing strategies retain their evidence and re-transcribed copies may share the media.
            removed = c.execute('UPDATE documents SET deleted_at=? WHERE id=? AND deleted_at IS NULL', (now(), ident))
            if removed.rowcount != 1:
                raise KeyError('资料不存在')

    def edit(self, ident, revision, segments):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM jobs WHERE document_id=? AND status IN ('queued','running')", (ident,)).fetchone():
                raise ValueError("任务执行中，完成后再编辑")
            updated = c.execute("UPDATE documents SET segments=?,revision=revision+1,updated_at=? WHERE id=? AND revision=? AND deleted_at IS NULL",
                                (json.dumps(segments, ensure_ascii=False), now(), ident, revision))
            if updated.rowcount != 1:
                raise ValueError("转写版本已变化，请刷新资料后重试")
        return self.document(ident)

    def set_media(self, ident, media_path, metadata=None):
        with self.connect() as c:
            c.execute("UPDATE documents SET media_path=?,media_metadata=?,updated_at=? WHERE id=?", (media_path, json.dumps(metadata or {}, ensure_ascii=False), now(), ident))
            if metadata and metadata.get('title'):
                c.execute("UPDATE documents SET title=? WHERE id=? AND title='视频资料'", (metadata['title'][:120], ident))

    def set_transcript(self, ident, segments, metadata=None, raw=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT segments FROM documents WHERE id=?',(ident,)).fetchone()
            if not row or json.loads(row['segments']): raise ValueError('已有原文，必须创建副本重转写')
            c.execute("UPDATE documents SET segments=?,original_segments=?,asr_metadata=?,asr_raw=?,revision=revision+1,updated_at=? WHERE id=?", (json.dumps(segments, ensure_ascii=False),json.dumps(segments,ensure_ascii=False),json.dumps(metadata or {},ensure_ascii=False),json.dumps(raw or {},ensure_ascii=False), now(), ident))

    def retranscription_copy(self, ident):
        source = self.document(ident)
        if not source['has_media']: raise ValueError('没有可复用的媒体缓存，请重新上传')
        if any(j['status'] in ('running','queued') for j in source['jobs']): raise ValueError('请等待当前任务完成再创建副本')
        copy_id, timestamp = uuid.uuid4().hex, now()
        title = source['title'][:114]+' · 重转写'
        with self.connect() as c:
            copied = c.execute('''INSERT INTO documents
                (id,title,source_type,source_url,media_path,is_demo,created_at,updated_at,parent_document_id,media_metadata)
                SELECT ?,?,source_type,source_url,media_path,is_demo,?,?,id,media_metadata
                FROM documents WHERE id=? AND deleted_at IS NULL''',
                (copy_id, title, timestamp, timestamp, ident))
            if copied.rowcount != 1:
                raise KeyError('资料不存在')
        return self.document(copy_id)

    def supplement_media_metadata(self, ident, media_path, metadata):
        # Recovery changes metadata only; preserve all original user work and timestamps.
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT media_metadata FROM documents WHERE id=? AND media_path=? AND deleted_at IS NULL', (ident, media_path)).fetchone()
            if row:
                current = json.loads(row['media_metadata'])
                if current.get('media_type') not in ('audio', 'video'):
                    c.execute('UPDATE documents SET media_metadata=? WHERE id=?',
                              (json.dumps({**current, **metadata}, ensure_ascii=False), ident))

    def create_job(self, ident, kind):
        jid = uuid.uuid4().hex
        try:
            with self.connect() as c:
                queued = c.execute('''INSERT INTO jobs
                    SELECT ?,id,?,'queued','等待处理',NULL,?,?
                    FROM documents WHERE id=? AND deleted_at IS NULL''', (jid, kind, now(), now(), ident))
                if queued.rowcount != 1:
                    raise KeyError('资料不存在')
        except sqlite3.IntegrityError:
            raise ValueError("已有任务正在执行，请等待完成") from None
        return self.job(jid)

    def job(self, ident, *, visible_only=False):
        with self.connect() as c:
            row = c.execute('''SELECT j.* FROM jobs j JOIN documents d ON d.id=j.document_id
                WHERE j.id=? AND (d.deleted_at IS NULL OR NOT ?)''', (ident, visible_only)).fetchone()
            if not row:
                raise KeyError("任务不存在")
            return dict(row)

    def update_job(self, ident, status, stage, error=None):
        with self.connect() as c:
            c.execute("UPDATE jobs SET status=?,stage=?,error=?,updated_at=? WHERE id=?", (status, stage, error, now(), ident))

    def save_strategy(self, document, result, provider, model, corrected_segments=None, ai_review=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            occupied = {row['display_title'].casefold() for row in c.execute('SELECT display_title FROM strategies')}
            title = (result.get('title') or '').strip() or document['title']
            display_title = unique_strategy_name(title, occupied, MAX_DRAFT_TITLE_LENGTH)
            c.execute('''INSERT INTO strategies
                (id,document_id,revision,result,transcript,provider,model,created_at,corrected_transcript,ai_review,display_title)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                      (uuid.uuid4().hex, document['id'], document['revision'], json.dumps(result, ensure_ascii=False),
                       json.dumps(document['segments'], ensure_ascii=False), provider, model, now(),
                       json.dumps(corrected_segments, ensure_ascii=False) if corrected_segments is not None else None,
                       json.dumps(ai_review, ensure_ascii=False) if ai_review is not None else None, display_title))
            c.execute("UPDATE documents SET updated_at=? WHERE id=?", (now(), document["id"]))

    def current_ai_mapping(self, source_id, mapping=None, *, expected_version=None):
        """Read or initialize the current draft mapping, or replace an observed version."""
        with self.connect() as c:
            if mapping is not None:
                c.execute('BEGIN IMMEDIATE')
            row = c.execute('''SELECT s.ai_mapping FROM strategies s
                JOIN documents d ON d.id=s.document_id AND d.revision=s.revision
                WHERE s.id=? AND s.id=(SELECT id FROM strategies
                    WHERE document_id=d.id ORDER BY created_at DESC,rowid DESC LIMIT 1)''', (source_id,)).fetchone()
            if row is None:
                raise ValueError('映射期间原文或草案已变化，请刷新后重试。')
            current = json.loads(row['ai_mapping']) if row['ai_mapping'] else None
            if expected_version is not None:
                if current is None or current.get('mapping_version') != expected_version:
                    raise ValueError('执行规则版本已变化，请载入最新规则后重试。')
            elif current is not None:
                return current
            if mapping is not None:
                c.execute('UPDATE strategies SET ai_mapping=? WHERE id=?',
                          (json.dumps(mapping, ensure_ascii=False), source_id))
            return mapping if mapping is not None else current
