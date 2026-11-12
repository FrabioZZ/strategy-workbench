"""Daily condition mapping contracts; model transport is local and never spends a key."""
import copy
import json

import pytest

from app.ai.mapping import validate_proposal
from test_ai_backend import model_transport, settings, poll, source_fixture


def conditional_fixture(buy='RSI(14)小于30时买入', sell='收盘价低于5日均线时全部卖出'):
    texts = ['沪市主板股票，日线。', buy, sell, '目标仓位25%', '大家好，今天分享这个方法。感谢观看。']
    ref = lambda i: [{'segment_id': f's{i+1}', 'quote': texts[i]}]
    source = {'transcript': [{'id': f's{i+1}', 'text': t} for i, t in enumerate(texts)],
              'evidence_transcript_version': 'original', 'ai_review': None,
              'strategy': {'title': '日线条件确认版', 'asset': {'value': '沪市主板股票', 'evidence': ref(0)},
                           'timeframe': {'value': '日线', 'evidence': ref(0)}, 'questions': [],
                           'rules': [{'kind': kind, 'text': texts[i], 'evidence': ref(i)}
                                     for kind, i in [('buy', 1), ('sell', 2), ('position', 3)]]}}
    proposal = {'rules': {'type': 'conditional', 'target_pct': 25,
                         'buy': {'op': 'lt', 'left': {'indicator': 'RSI', 'params': {'period': 14}}, 'right': {'value': 30}},
                         'sell': {'op': 'lt', 'left': {'indicator': 'CLOSE'},
                                  'right': {'indicator': 'MA', 'params': {'period': 5}}}},
                'mapping_note': '独立日线确认版本；收盘判断，次日开盘执行。', 'questions': [],
                'evidence': [{'field': field, **ref(i)[0]} for field, i in [('buy', 1), ('sell', 2), ('target_pct', 3), ('timeframe', 0)]]}
    return source, proposal


def test_daily_indicator_rules_map_with_original_text_and_narration_preserved():
    source, proposal = conditional_fixture()
    before = copy.deepcopy(source)
    rules, _, questions, evidence = validate_proposal(proposal, source)
    assert rules is not None, questions
    assert rules['buy']['left']['indicator'] == 'RSI'
    assert rules['sell']['right']['params']['period'] == 5
    assert not questions and source == before
    assert all(e['transcript_version'] == 'original' for e in evidence)


@pytest.mark.parametrize('buy', ['RSI(14)低于30时买入', '当14日RSI小于30的时候买入', '如果RSI(14)<30则买入'])
def test_common_comparison_wording_has_identical_daily_semantics(buy):
    source, proposal = conditional_fixture(buy=buy)
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is not None, questions


@pytest.mark.parametrize('timeframe', ['日线', '日线周期'])
def test_spoken_ma_crossover_and_stop_loss_keep_corrected_citations(timeframe):
    buy = '收盘价向上突破二十日均线就买。'
    sell = '当收盘价跌破二十天均线，就清仓。'
    stop = '以入场信号收盘价为基准，日线收盘下跌百分之五就止损。'
    position = '目标仓位为百分之二十五。'
    source, proposal = conditional_fixture(buy, sell)
    source['corrected_transcript'] = copy.deepcopy(source['transcript'])
    context = '沪市主板股票，我们在日线周期观察。'
    source['corrected_transcript'][0]['text'] = context
    source['strategy']['timeframe']['value'] = timeframe
    for field in ('asset', 'timeframe'):
        source['strategy'][field]['evidence'][0]['quote'] = context
    source['corrected_transcript'][3]['text'] = position
    source['corrected_transcript'].append({'id': 's6', 'text': stop})
    source['transcript'][1]['text'] = '收盘架向上突破二十日军线就买。'
    source['evidence_transcript_version'] = 'corrected'
    source['strategy']['rules'][2].update(text=position, evidence=[{'segment_id': 's4', 'quote': position}])
    source['strategy']['rules'].append({'kind': 'stop_loss', 'text': stop,
                                        'evidence': [{'segment_id': 's6', 'quote': stop}]})
    proposal['evidence'][2]['quote'] = position
    proposal['evidence'][3]['quote'] = '我们在日线周期观察'
    proposal['evidence'].append({'field': 'stop_loss_pct', 'segment_id': 's6', 'quote': stop})
    proposal['rules'].update(
        buy={'op': 'cross_above', 'left': {'indicator': 'CLOSE'},
             'right': {'indicator': 'MA', 'params': {'period': 20}}},
        sell={'op': 'cross_below', 'left': {'indicator': 'CLOSE'},
              'right': {'indicator': 'MA', 'params': {'period': 20}}},
        stop_loss_pct=5,
    )

    rules, _, questions, evidence = validate_proposal(proposal, source)

    assert rules is not None, questions
    assert rules['buy']['op'] == 'cross_above' and rules['sell']['op'] == 'cross_below'
    assert rules['buy']['right']['params']['period'] == 20
    assert rules['target_pct'] == 25 and rules['stop_loss_pct'] == 5
    assert evidence == [{**ref, 'transcript_version': 'corrected'} for ref in proposal['evidence']]


@pytest.mark.parametrize('buy', ['股价站上二十日均线就买', '收盘价站上二十日均线就买'])
def test_spoken_ma_phrase_with_ambiguous_cross_is_unresolved(buy):
    source, proposal = conditional_fixture(buy=buy)
    proposal['rules']['buy'] = {'op': 'cross_above', 'left': {'indicator': 'CLOSE'},
                                'right': {'indicator': 'MA', 'params': {'period': 20}}}
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is None and questions


def test_spoken_stop_loss_without_basis_is_unresolved():
    source, proposal = conditional_fixture()
    text = '跌破百分之五止损'
    source['transcript'].append({'id': 's6', 'text': text})
    source['strategy']['rules'].append({'kind': 'stop_loss', 'text': text,
                                        'evidence': [{'segment_id': 's6', 'quote': text}]})
    proposal['evidence'].append({'field': 'stop_loss_pct', 'segment_id': 's6', 'quote': text})
    proposal['rules']['stop_loss_pct'] = 5
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is None and questions


@pytest.mark.parametrize('bad', ['indicator', 'parameter', 'direction', 'incomplete', 'position', 'unproved', 'minute', 'omitted', 'implicit_period'])
def test_unknown_incomplete_or_invented_conditions_cannot_become_ready(bad):
    source, proposal = conditional_fixture()
    if bad == 'indicator': proposal['rules']['buy']['left']['indicator'] = 'MAGIC_ALPHA'
    if bad == 'parameter': proposal['rules']['buy']['left']['params']['invented'] = 3
    if bad == 'direction': proposal['rules']['buy']['op'] = 'gt'
    if bad == 'incomplete': del proposal['rules']['sell']
    if bad == 'position': proposal['rules']['target_pct'] = 50
    if bad == 'unproved': proposal['evidence'][0]['quote'] = '大家好'
    if bad == 'minute': source['strategy']['timeframe']['value'] = '5分钟'
    if bad == 'omitted': source['transcript'].append({'id': 's6', 'text': '还要求ROE高于15%才能买入'})
    if bad == 'implicit_period':
        source['transcript'][1]['text'] = source['strategy']['rules'][0]['text'] = 'RSI小于30时买入'
        proposal['evidence'][0]['quote'] = 'RSI小于30时买入'
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is None and questions


def test_first_limit_up_confirmation_is_daily_and_requires_both_conditions():
    source, proposal = conditional_fixture(buy='前一日首板且当日涨幅大于0%时买入')
    proposal['rules']['buy'] = {'op': 'and', 'conditions': [
        {'op': 'eq', 'left': {'indicator': 'FIRST_LIMIT_UP', 'offset': 1}, 'right': {'value': 1}},
        {'op': 'gt', 'left': {'indicator': 'CHANGE_PCT'}, 'right': {'value': 0}},
    ]}
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is not None, questions
    proposal['rules']['buy'] = proposal['rules']['buy']['conditions'][0]
    assert validate_proposal(proposal, source)[0] is None


def test_legacy_model_mapper_receives_live_capabilities_and_always_requires_confirmation(tmp_path, monkeypatch):
    from app.ai.mapping import map_strategy
    source, proposal = source_fixture()
    requests = model_transport(monkeypatch, [proposal])
    result = map_strategy(settings(tmp_path), source)
    assert result['ready'] and result['confirmed'] is False, result
    system = json.loads(requests[0].content)['messages'][0]['content']
    for required in ('FIRST_LIMIT_UP', 'MACD_DIF', 'RSI', 'cross_above', 'warmup', 'period'):
        assert required in system


def test_intraday_teaching_sample_cannot_silently_become_a_daily_complete_strategy():
    source, proposal = conditional_fixture()
    # Artificial teaching sample; the real 282-segment transcript stays local.
    texts = ['首板次日观察竞价和题材强弱', '盘中放量并快速封板时买入',
             '炸板后5分钟仍未回封则清仓', '单票仓位不超过总资金的50%']
    source['transcript'] = [{'id': f's{i+1}', 'text': text} for i, text in enumerate(texts)]
    source['strategy']['rules'] = [
        {'kind': kind, 'text': texts[i], 'evidence': [{'segment_id': f's{i+1}', 'quote': texts[i]}]}
        for kind, i in [('buy', 1), ('sell', 2), ('position', 3)]]
    before = copy.deepcopy(source)
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is None and questions
    assert any('盘中' in q or '分时' in q or '分钟' in q or '分鐘' in q for q in questions)
    assert source == before


@pytest.mark.parametrize('text,indicator,params', [
    ('MACD_DIF(12,26,9)', 'MACD_DIF', {'fast': 12, 'slow': 26, 'signal': 9}),
    ('KDJ_K(9,3,3)', 'KDJ_K', {'period': 9, 'k_period': 3, 'd_period': 3}),
    ('布林上轨(20,2)', 'BOLL_UPPER', {'period': 20, 'stddev': 2}),
    ('14日ATR', 'ATR', {'period': 14}),
    ('日线量比(5)', 'VOLUME_RATIO', {'period': 5}),
    ('5日成交量均线', 'MA', {'period': 5, 'field': 'volume'}),
    ('MA(5,volume)', 'MA', {'period': 5, 'field': 'volume'}),
])
def test_supported_indicator_parameters_preserve_original_meaning(text, indicator, params):
    source, proposal = conditional_fixture(buy=f'{text}大于0时买入')
    proposal['rules']['buy'] = {'op': 'gt', 'left': {'indicator': indicator, 'params': params}, 'right': {'value': 0}}
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is not None, questions
    assert rules['buy']['left']['params'] == params


def test_macd_cross_is_not_continuous_comparison_and_argument_commas_survive():
    source, proposal = conditional_fixture(buy='MACD_DIF(12,26,9)上穿MACD_DEA(12,26,9)时买入')
    proposal['rules']['buy'] = {'op': 'cross_above',
        'left': {'indicator': 'MACD_DIF', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
        'right': {'indicator': 'MACD_DEA', 'params': {'fast': 12, 'slow': 26, 'signal': 9}}}
    assert validate_proposal(proposal, source)[0] is not None
    proposal['rules']['buy']['op'] = 'gt'
    assert validate_proposal(proposal, source)[0] is None


def test_invalid_source_parameter_returns_a_question_instead_of_crashing():
    source, proposal = conditional_fixture(buy='RSI(0)小于30时买入')
    rules, _, questions, _ = validate_proposal(proposal, source)
    assert rules is None and questions


@pytest.mark.parametrize('buy,left,value', [
    ('成交量大于10%时买入', {'indicator': 'VOLUME'}, 10),
    ('昨日收盘价[0]大于10时买入', {'indicator': 'CLOSE'}, 10),
    ('RSI(14)大于30元时买入', {'indicator': 'RSI', 'params': {'period': 14}}, 30),
])
def test_conflicting_time_or_units_cannot_be_erased(buy, left, value):
    source, proposal = conditional_fixture(buy=buy)
    proposal['rules']['buy'] = {'op': 'gt', 'left': left, 'right': {'value': value}}
    assert validate_proposal(proposal, source)[0] is None


def test_deep_untrusted_condition_returns_questions():
    source, proposal = conditional_fixture(buy='(' * 1200 + 'RSI(14)小于30' + ')' * 1200 + '时买入')
    assert validate_proposal(proposal, source)[0] is None


def test_confirmed_daily_variant_maps_and_buys_then_sells_in_both_engines(tmp_path, monkeypatch):
    """This explicit fixture is NOT a faithful reproduction of the intraday video."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    source, proposal = conditional_fixture(buy='前一日首板且当日涨幅大于0%时买入', sell='收盘价低于2日均线时全部卖出')
    proposal['rules']['buy'] = {'op': 'and', 'conditions': [
        {'op': 'eq', 'left': {'indicator': 'FIRST_LIMIT_UP', 'offset': 1}, 'right': {'value': 1}},
        {'op': 'gt', 'left': {'indicator': 'CHANGE_PCT'}, 'right': {'value': 0}}]}
    proposal['rules']['sell']['right']['params']['period'] = 2
    model_transport(monkeypatch, [{'changes': [], 'questions': []}, source['strategy'], proposal])
    with TestClient(create_app(settings(tmp_path)), client=('127.0.0.1', 1234)) as client:
        doc = client.post('/api/documents/text', json={'title': '独立日线确认版契约样例',
            'text': '\n'.join(s['text'] for s in source['transcript'])}).json()
        job = client.post('/api/documents/' + doc['id'] + '/extract').json()
        assert poll(client, job['id'])['status'] == 'succeeded'
        src = client.get('/api/trading/strategies').json()[0]
        result = client.post('/api/ai/strategies/' + src['id'] + '/mapping').json()
        assert result['ready'] and result['confirmed'] is False, result
        item = {'id': 'daily', 'name': '独立日线确认版', 'source_id': src['id'],
                'confirmed': False, 'mapping_note': result['mapping_note'], 'rules': result['rules']}
        portfolio = client.post('/api/trading/portfolios', json={'name': '日线契约组合', 'items': [item]}).json()
        assert not portfolio['readiness']['ready']
        item['confirmed'] = True  # Explicit human confirmation contract.
        portfolio = client.put('/api/trading/portfolios/' + portfolio['id'], json={
            'name': portfolio['name'], 'revision': portfolio['revision'], 'items': [item]}).json()
        assert portfolio['readiness']['ready'], portfolio
        csv = 'date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down\n'
        csv += '2026-01-05,600000.SH,10,10.1,9.9,10,100000,10,11,9\n'
        csv += '2026-01-06,600000.SH,10,11,10,11,100000,10,11,9\n'
        csv += '2026-01-07,600000.SH,11.2,11.6,11.1,11.5,100000,11,12.1,9.9\n'
        csv += '2026-01-08,600000.SH,11.4,11.5,10.9,11,100000,11.5,12.65,10.35\n'
        csv += '2026-01-09,600000.SH,11,11.1,10.7,10.8,100000,11,12.1,9.9\n'
        response = client.post('/api/trading/datasets/import', json={'name': 'daily-confirmation-fixture',
            'source': 'test-only synthetic bars', 'csv_text': csv, 'ordinary_stock_confirmed': True,
            'corporate_actions_confirmed_absent': True})
        assert response.status_code == 201, response.text
        payload = {'portfolio_id': portfolio['id'], 'portfolio_revision': portfolio['revision'],
                   'dataset_id': response.json()['id'], 'symbol': '600000.SH', 'initial_cash': 10000}
        response = client.post('/api/trading/backtests', json=payload)
        assert response.status_code == 201, response.text
        backtest = response.json()
        assert [(f['side'], f['date']) for f in backtest['fills']] == [('buy', '2026-01-08'), ('sell', '2026-01-09')]
        paper = client.post('/api/trading/paper/sessions', json={**payload, 'name': 'daily-contract', 'mode': 'replay'}).json()
        for i in range(5):
            response = client.post('/api/trading/paper/sessions/' + paper['id'] + '/step', json={'request_id': str(i)})
            assert response.status_code == 200, response.text
        assert response.json()['fills'] == backtest['fills']
        response = client.post('/api/trading/external-paper/sessions', json={**payload, 'name': 'Backtrader daily contract'})
        assert response.status_code == 201, response.text
        external = response.json()
        response = client.post('/api/trading/external-paper/sessions/' + external['id'] + '/run', json={'request_id': 'run-all'})
        assert response.status_code == 200, response.text
        external = response.json()
        assert [(f['side'], f['date']) for f in external['fills']] == [('buy', '2026-01-08'), ('sell', '2026-01-09')]
        assert external['cash'] == pytest.approx(9908.9)
