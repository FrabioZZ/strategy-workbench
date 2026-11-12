import copy
from datetime import date, timedelta

from test_ai_backend import draft_fixture, model_transport, poll, settings
from test_ai_conditional_mapping import conditional_fixture
from fastapi.testclient import TestClient
from app.ai.mapping import map_strategy
from app.main import create_app


def test_user_resolution_is_versioned_and_required_for_linked_portfolio(tmp_path, monkeypatch):
    texts, draft, _ = draft_fixture()
    buy = '收盘价上穿五日均线且放量时买入'
    texts[1] = buy + '，目标仓位50%。'
    texts[2] = '收盘价下穿五日均线时全部卖出。'
    for rule, index in zip(draft['rules'], (1, 1, 2)):
        rule['evidence'] = [{'segment_id': f's{index + 1}', 'quote': texts[index]}]
    draft['rules'][0]['text'] = texts[1]
    draft['rules'][2]['text'] = texts[2]
    draft['questions'] = ['需要明确放量的定义。']
    calls = model_transport(monkeypatch, [{'changes': [], 'questions': []}, draft])

    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        doc = client.post('/api/documents/text', json={'title': '测试', 'text': '\n'.join(texts)}).json()
        job = client.post(f'/api/documents/{doc["id"]}/extract').json()
        assert poll(client, job['id'])['status'] == 'succeeded'
        src = client.get('/api/trading/strategies').json()[0]
        url = f'/api/ai/strategies/{src["id"]}/mapping'
        pending = client.post(url).json()
        assert not pending['ready'] and pending['rules'] is None
        question, = pending['clarifications']
        assert '放量' in question['quote']
        submission = {'source_revision': src['revision'], 'answers': [
            {'question_id': question['id'], 'option_id': 'custom', 'values': {'period': 20, 'multiple': 1.75}},
        ]}
        assert client.post(url, json={**submission, 'source_revision': src['revision'] + 1}).status_code == 409
        invalid = copy.deepcopy(submission)
        invalid['answers'][0]['values']['multiple'] = True
        assert client.post(url, json=invalid).status_code == 422
        adopted = client.post(url, json=submission)
        assert adopted.status_code == 200, adopted.text
        result = adopted.json()
        assert result['ready'] and not result['confirmed'], result
        assert any(ref['quote'] in texts[1] and '放量' in ref['quote'] for ref in result['evidence'])
        assert result['decisions'][0]['option_id'] == submission['answers'][0]['option_id']
        assert client.post(url, json=submission).json() == result
        wrong = copy.deepcopy(submission)
        wrong['answers'][0]['question_id'] = 'other-question'
        assert client.post(url, json=wrong).status_code in (400, 409)
        assert client.get(f'/api/documents/{doc["id"]}/export').json()['ai_mapping'] == result
        assert len(calls) == 2

        item = {'id': 'a', 'name': src['title'], 'source_id': src['id'], 'enabled': True, 'weight': 100,
                'confirmed': False, 'mapping_note': result['mapping_note'], 'rules': result['rules']}
        portfolio = lambda item: client.post('/api/trading/portfolios',
                                             json={'name': '选择题策略', 'items': [item]}).json()
        assert not portfolio(item)['readiness']['ready']
        item['confirmed'] = True
        saved = portfolio(item)
        assert saved['readiness']['ready'], saved
        assert saved['items'][0]['source_snapshot']['ai_mapping']['decisions'] == result['decisions']
        dataset, fill_dates = volume_backtest_dataset(client)
        backtest = client.post('/api/trading/backtests', json={
            'portfolio_id': saved['id'], 'portfolio_revision': saved['revision'],
            'dataset_id': dataset, 'symbol': '600000.SH', 'initial_cash': 10000,
        })
        assert backtest.status_code == 201, backtest.text
        assert [(fill['side'], fill['date']) for fill in backtest.json()['fills']] == [
            ('buy', fill_dates[0]), ('sell', fill_dates[1]),
        ]
        automatic = dict(portfolio_id=saved['id'], portfolio_revision=saved['revision'],
                         symbol='600000.SH', start_date='2026-01-05',
                         end_date=fill_dates[-1], initial_cash=10000)
        workbench = client.post('/api/trading/workstation/backtests', json=automatic)
        assert workbench.status_code == 201, workbench.text
        assert workbench.json()['fills'] == backtest.json()['fills']
        paper = client.post('/api/trading/workstation/paper/sessions', json=automatic)
        assert paper.status_code == 201, paper.text
        assert paper.json()['fills'] == workbench.json()['fills']
        assert not portfolio({**item, 'timeframe': '5m'})['readiness']['ready']
        item['rules']['target_pct'] = 65
        assert not portfolio(item)['readiness']['ready']


def volume_backtest_dataset(client):
    first = date(2026, 1, 5)
    sessions = [first + timedelta(days=offset) for offset in range(40)
                if (first + timedelta(days=offset)).weekday() < 5][:24]
    rows = ['date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down']
    prev = 10
    for index, day in enumerate(sessions):
        close = {20: 10.5, 21: 10.6, 22: 9.9, 23: 9.9}.get(index, 10)
        volume = 200000 if index == 20 else 100000
        rows.append(f'{day},600000.SH,{close},{close},{close},{close},{volume},{prev},{prev*1.1:.2f},{prev*.9:.2f}')
        prev = close
    response = client.post('/api/trading/datasets/import', json={
        'name': '放量回测样本', 'source': 'synthetic fixture', 'csv_text': '\n'.join(rows),
        'ordinary_stock_confirmed': True, 'corporate_actions_confirmed_absent': True,
    })
    assert response.status_code == 201, response.text
    return response.json()['id'], [sessions[index].isoformat() for index in (21, 23)]


def test_standard_conditions_compile_with_original_evidence_without_a_model():
    source, _ = conditional_fixture(buy='收盘价上穿五日均线时买入')
    source['transcript'] += [
        {'id': 's6', 'text': '我是基友，欢迎在评论区交流换手率话题。'},
    ]
    source['strategy']['questions'] = ['s6 的昵称是否识别有误？']
    source['ai_review'] = {'questions': ['s6 的昵称需校对']}
    result = map_strategy(None, source)
    assert result['ready'] and not result['confirmed'], result
    assert result['rules']['buy']['op'] == 'cross_above'
    assert result['rules']['sell']['op'] == 'lt'
    assert all(ref['segment_id'] != 's6' for ref in result['evidence'])


def test_daily_terms_cannot_clear_an_unmapped_trading_exception():
    source, _ = conditional_fixture(buy='收盘价上穿五日均线且放量时买入')
    source['transcript'].append({'id': 's6', 'text': '但缩量时不买。'})
    question, = map_strategy(None, source)['clarifications']
    result = map_strategy(None, source, [
        {'question_id': question['id'], 'option_id': question['options'][0]['id']},
    ])
    assert not result['ready'] and result['rules'] is None
    assert any('s6' in question for question in result['questions'])


def test_five_minute_input_stays_out_of_daily_mapping():
    source, _ = conditional_fixture(buy='5分钟收盘价上穿五根均线且放量时买入')
    source['strategy']['timeframe']['value'] = '5分钟'
    result = map_strategy(None, source)
    assert not result['ready'] and not result.get('clarifications')
    assert any('分钟' in question for question in result['questions'])
