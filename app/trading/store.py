import json
import sqlite3
import uuid
from contextlib import contextmanager
from app.store import now

class TradingStore:
    def __init__(self, folder):
        self.folder = folder
        self.path = folder / 'trading.sqlite3'

    @contextmanager
    def transaction(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @contextmanager
    def readonly_transaction(self):
        uri = self.path.resolve().as_uri() + '?mode=ro'
        c = sqlite3.connect(uri, uri=True, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    def init(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with self.transaction() as c:
            c.execute('CREATE TABLE IF NOT EXISTS resources (kind TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            for row in c.execute("SELECT * FROM resources WHERE kind='paper'").fetchall():
                value=json.loads(row['body'])
                value.update(status='paused', feed_status='paused', message='服务重启，账本已保留，请显式启动恢复', updated_at=now())
                self.put(c, 'paper', value)

    def get(self, c, kind, ident):
        row = c.execute('SELECT body FROM resources WHERE kind=? AND id=?', (kind, ident)).fetchone()
        if not row: raise KeyError('交易资源不存在')
        return json.loads(row['body'])

    def list(self, c, kind):
        return [json.loads(r['body']) for r in c.execute('SELECT body FROM resources WHERE kind=? ORDER BY rowid DESC', (kind,))]

    def put(self, c, kind, value):
        c.execute('INSERT INTO resources VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                  (kind, value['id'], json.dumps(value, ensure_ascii=False, allow_nan=False)))
        return value

    def delete(self, c, kind, ident):
        self.get(c,kind,ident)
        c.execute('DELETE FROM resources WHERE kind=? AND id=?',(kind,ident))


def identity():
    return {'id':uuid.uuid4().hex,'created_at':now()}
