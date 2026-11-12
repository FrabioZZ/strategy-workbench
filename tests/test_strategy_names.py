import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.store import Store


def draft(title, quote):
    return {'title': title, 'rules': [{'kind': 'buy', 'text': quote,
                                     'evidence': [{'segment_id': 's1', 'quote': quote}]}]}


def test_repeated_draft_titles_are_unique_and_keep_their_evidence(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    base = '测' * 120
    with TestClient(app) as client:
        store = app.state.store
        documents = []
        for number in range(3):
            quote = f'证据 {number}'
            doc = store.create_document(quote, 'text', segments=[{'id': 's1', 'text': quote}])
            store.save_strategy(doc, draft(base, quote), 'test', 'fixture')
            documents.append(doc)

        expected = [base, base[:116] + ' (2)', base[:116] + ' (3)']
        candidates = {item['document_id']: item for item in client.get('/api/trading/strategies').json()}
        for number, (doc, title) in enumerate(zip(documents, expected)):
            path = f'/api/documents/{doc["id"]}'
            candidate = candidates[doc['id']]
            assert candidate['title'] == title
            for strategy in (client.get(path).json()['strategy'], client.get(f'{path}/export').json()['strategy'],
                             candidate['strategy']):
                assert strategy == draft(title, f'证据 {number}')


def test_legacy_duplicate_draft_titles_skip_literal_suffixes_and_stay_stable(tmp_path):
    config = Settings(data_dir=tmp_path)
    store = Store(tmp_path)
    store.init()
    documents = [store.create_document(f'证据 {n}', 'text') for n in range(4)]
    originals = [draft(name, f'证据 {n}') for n, name in enumerate(['均线', '均线', '均线 (2)', '均线'])]
    with store.connect() as connection:
        connection.execute('DROP TABLE strategies')
        connection.execute('''CREATE TABLE strategies (
            id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
            revision INTEGER NOT NULL, result TEXT NOT NULL, transcript TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL)''')
        connection.executemany('INSERT INTO strategies VALUES (?,?,1,?,?,?,?,?)', [
            (f'legacy-{n}', doc['id'], json.dumps(original, ensure_ascii=False), '[]',
             'test', 'fixture', '2026-01-01T00:00:00+00:00')
            for n, (doc, original) in enumerate(zip(documents, originals))
        ])

    expected = {'legacy-0': '均线', 'legacy-1': '均线 (3)', 'legacy-2': '均线 (2)', 'legacy-3': '均线 (4)'}
    for _ in range(2):
        with TestClient(create_app(config)) as client:
            candidates = client.get('/api/trading/strategies').json()
            assert {item['id']: item['title'] for item in candidates} == expected
            for item in candidates:
                detail = client.get(f'/api/documents/{item["document_id"]}').json()
                assert detail['strategy_id'] == item['id']
                assert detail['strategy'] == item['strategy']

    with store.connect() as connection:
        assert [json.loads(row['result']) for row in connection.execute('SELECT result FROM strategies ORDER BY rowid')] == originals
