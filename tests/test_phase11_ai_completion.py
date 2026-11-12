import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_ai_backend import model_transport, poll, settings
from test_phase10_mapping import volume_backtest_dataset


def extract(client, monkeypatch, *, extra_rule=None, explicit_buy=False):
    texts = ['600000.SH，日线。', '收盘价站上5日均线且放量时买入。',
             '收盘价跌破5日均线时全部卖出。', '目标仓位20%。']
    if extra_rule:
        texts.append(extra_rule)
    if explicit_buy:
        texts.append('收盘价上穿5日均线且日线量比(20)大于1.5时买入。')

    def ref(index):
        return [{'segment_id': f's{index+1}', 'quote': texts[index]}]

    draft = {
        'title': '日线站上放量策略',
        'asset': {'value': '600000.SH', 'evidence': ref(0)},
        'timeframe': {'value': '日线', 'evidence': ref(0)},
        'rules': [{'kind': kind, 'text': texts[index], 'evidence': ref(index)}
                  for index, kind in [(1, 'buy'), (2, 'sell'), (3, 'position')]],
        'questions': [],
    }
    calls = model_transport(monkeypatch, [{'changes': [], 'questions': []}, draft])
    document = client.post('/api/documents/text', json={'title': '映射样例', 'text': '\n'.join(texts)}).json()
    job = client.post(f'/api/documents/{document["id"]}/extract').json()
    completed = poll(client, job['id'])
    assert completed['status'] == 'succeeded', completed
    source = client.get('/api/trading/strategies').json()[0]
    assert len(calls) == 2
    return document, source, f'/api/ai/strategies/{source["id"]}/mapping'


def chooser(calls, *, change=None):
    def complete(settings, messages, schema):
        payload = json.loads(messages[-1]['content'])
        calls.append(payload)
        selections = {'ma_stand_above': 'cross_above', 'volume_ratio': 'previous_20_x1_5'}
        decisions = [{'question_id': q['id'], 'option_id': selections[q['field']],
                      'reason': '按日线收盘信号的语境选择此解释。'} for q in payload['clarifications']]
        if change:
            change(decisions)
        return json.dumps({'decisions': decisions})

    return complete


def test_completion_compiles_and_executes_the_versioned_rule_without_another_model(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        doc, source, url = extract(client, monkeypatch)
        calls = []
        monkeypatch.setattr('app.ai.client.complete', chooser(calls))
        revision = {'source_revision': source['revision']}
        response = client.post(url + '/complete', json=revision)
        assert response.status_code == 200, response.text
        mapped = response.json()
        assert mapped['ready'] and not mapped['confirmed'], mapped
        assert mapped['resolution_method'] == 'ai' and mapped['mapping_version']
        assert mapped['rules']['target_pct'] == 20
        assert mapped['rules']['sell']['op'] == 'cross_below'
        assert mapped['rules']['sell']['right']['params']['period'] == 5
        assert {d['basis'] for d in mapped['decisions']} == {'assumption'}
        assert all(d['reason'] and '且放量' in d['quote'] for d in mapped['decisions'])
        assert any(e['field'] == 'asset' and '600000.SH' in e['quote'] for e in mapped['evidence'])
        assert calls[0]['clarifications'][1]['options'][0]['values'] == {'period': 20, 'multiple': 1.5}
        assert client.post(url + '/complete', json=revision).json() == mapped
        assert client.get(f'/api/documents/{doc["id"]}/export').json()['ai_mapping'] == mapped

        item = dict(id='item', name='日线样例', source_id=source['id'], enabled=True,
                    confirmed=False, mapping_note=mapped['mapping_note'], rules=mapped['rules'],
                    mapping_version=mapped['mapping_version'])
        unconfirmed = client.post('/api/trading/portfolios', json={'name': '待确认', 'items': [item]}).json()
        assert not unconfirmed['readiness']['ready']
        item['confirmed'] = True
        saved = client.post('/api/trading/portfolios', json={'name': '已确认', 'items': [item]}).json()
        assert saved['readiness']['ready'], saved
        dataset, fill_dates = volume_backtest_dataset(client)
        backtest = client.post('/api/trading/backtests', json={
            'portfolio_id': saved['id'], 'portfolio_revision': saved['revision'], 'dataset_id': dataset,
            'symbol': '600000.SH', 'initial_cash': 10000,
        })
        assert backtest.status_code == 201, backtest.text
        fills = backtest.json()['fills']
        assert (fills[0]['side'], fills[0]['date']) == ('buy', fill_dates[0])
        assert [(f['side'], f['date']) for f in fills if f['side'] == 'sell'] == [('sell', fill_dates[1])]
        assert len(calls) == 1

        answers = [{'question_id': d['question_id'], 'option_id': d['option_id']} for d in mapped['decisions']]
        answers[1]['option_id'] = 'previous_20_x2'
        replacement = {**revision, 'mapping_version': mapped['mapping_version'], 'answers': answers}
        response = client.post(url, json=replacement)
        assert response.status_code == 200, response.text
        manual = response.json()
        assert manual['resolution_method'] == 'manual' and manual['mapping_version'] != mapped['mapping_version']
        assert client.post(url, json=replacement).json() == manual
        assert not client.get('/api/trading/portfolios/' + saved['id']).json()['readiness']['ready']
        assert client.get('/api/trading/backtests/' + backtest.json()['id']).json()['portfolio_snapshot']['items'][0][
            'source_snapshot']['ai_mapping']['mapping_version'] == mapped['mapping_version']
        assert client.post(url + '/complete', json={**revision, 'source_revision': source['revision']+1}).status_code == 409


@pytest.mark.parametrize('variant', ['invalid_option', 'partial', 'exception', 'explicit'])
def test_completion_respects_candidate_validity_and_full_source_coverage(tmp_path, monkeypatch, variant):
    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        doc, source, url = extract(client, monkeypatch, extra_rule='但缩量时不买。' if variant == 'exception' else None,
                                   explicit_buy=variant == 'explicit')
        calls = []
        changes = {'invalid_option': lambda ds: ds[0].update(option_id='invalid'), 'partial': lambda ds: ds.pop()}
        monkeypatch.setattr('app.ai.client.complete', chooser(calls, change=changes.get(variant)))
        response = client.post(url + '/complete', json={'source_revision': source['revision']})
        if variant == 'explicit':
            assert response.status_code == 200 and response.json()['ready'], response.text
            assert {d['basis'] for d in response.json()['decisions']} == {'evidence'}
            assert all(d['support']['segment_id'] == 's5' for d in response.json()['decisions'])
        else:
            assert response.status_code == (400 if variant == 'invalid_option' else 200), response.text
            if response.status_code == 200:
                assert not response.json()['ready'] and response.json()['rules'] is None
            assert client.get(f'/api/documents/{doc["id"]}/export').json()['ai_mapping'] is None
            assert len(client.post(url).json()['clarifications']) == 2


def test_model_result_is_discarded_if_transcript_changes_during_completion(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        doc, source, url = extract(client, monkeypatch)
        calls = []
        choose = chooser(calls)

        def edit_then_complete(*args):
            edited = client.put(f'/api/documents/{doc["id"]}/transcript', json={
                'revision': doc['revision'], 'segments': doc['segments'],
            })
            assert edited.status_code == 200, edited.text
            return choose(*args)

        monkeypatch.setattr('app.ai.client.complete', edit_then_complete)
        response = client.post(url + '/complete', json={'source_revision': source['revision']})
        assert response.status_code == 409, response.text
        assert len(calls) == 1
        draft = next(s for s in client.get('/api/trading/strategies').json() if s['id'] == source['id'])
        assert draft['stale'] and draft['ai_mapping'] is None


def test_concurrent_legacy_manual_choice_wins_over_a_later_ai_result(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        _, source, url = extract(client, monkeypatch)
        calls, saved = [], []
        choose = chooser(calls)
        revision = {'source_revision': source['revision']}

        def manual_then_complete(*args):
            pending = client.post(url).json()
            answers = [{'question_id': q['id'], 'option_id': q['options'][-1]['id']}
                       for q in pending['clarifications']]
            manual = client.post(url, json={**revision, 'answers': answers})
            assert manual.status_code == 200 and manual.json()['ready'], manual.text
            saved.append(manual.json())
            return choose(*args)

        monkeypatch.setattr('app.ai.client.complete', manual_then_complete)
        assert client.post(url + '/complete', json=revision).json() == saved[0]
        assert 'mapping_version' not in saved[0] and len(calls) == 1


def test_manual_choice_still_works_with_no_configured_model(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        _, source, url = extract(client, monkeypatch)
        assert client.delete('/api/ai/config').status_code == 200
        revision = {'source_revision': source['revision']}
        unavailable = client.post(url + '/complete', json=revision)
        assert unavailable.status_code == 400 and '未配置' in unavailable.json()['detail']
        pending = client.post(url).json()
        answers = [{'question_id': q['id'], 'option_id': q['options'][0]['id']}
                   for q in pending['clarifications']]
        manual = client.post(url, json={**revision, 'answers': answers})
        assert manual.status_code == 200 and manual.json()['ready'], manual.text
