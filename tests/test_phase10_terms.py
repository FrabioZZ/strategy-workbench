import copy

import pytest

from app.ai.capabilities import parse_condition, split_daily_clauses


def resolve(text, options=None):
    from app.ai.terms import resolve_terms

    segments = [{'id': 's1', 'text': text, 'start': 0, 'end': 12}]
    before = copy.deepcopy(segments)
    pending = resolve_terms(segments)
    assert segments == before
    if options is None:
        return pending
    answers = []
    for question in pending['clarifications']:
        selected = options.get(question['field'])
        if isinstance(selected, dict):
            answers.append({'question_id': question['id'], 'option_id': 'custom', 'values': selected})
        elif selected:
            answers.append({'question_id': question['id'], 'option_id': selected})
    result = resolve_terms(segments, answers)
    assert segments == before
    return result


def test_volume_question_preserves_the_whole_buy_clause_and_uses_prior_average():
    text = '大家好。收盘价上穿五日均线，且放量时买入。感谢观看。'
    original = '收盘价上穿五日均线，且放量时买入'
    pending = resolve(text)
    assert pending['segments'][0]['text'] == text
    question, = pending['clarifications']
    assert question['quote'] == original and question['segment_id'] == 's1'
    assert question['id'] == resolve(text)['clarifications'][0]['id']
    assert question['id'] != resolve(text.replace('五日', '四日'))['clarifications'][0]['id']
    assert any('不含当日' in option['label'] for option in question['options'])

    mapped = resolve(text, {'volume_ratio': {'period': 12, 'multiple': 1.75}})
    assert not mapped['clarifications']
    replacement, = mapped['replacements']
    assert replacement['original_clause'] == original
    effective = replacement['effective_clause']
    assert mapped['segments'][0]['text'] == text.replace(original, effective)
    assert mapped['segments'][0]['start'] == 0 and mapped['segments'][0]['end'] == 12
    assert mapped['decisions'][0]['original_clause'] == original
    assert mapped['decisions'][0]['term_version'] == mapped['version']
    expression = parse_condition(effective.removesuffix('时买入'))
    cross, volume = expression['conditions']
    assert cross['op'] == 'cross_above' and cross['right']['params']['period'] == 5
    assert volume['op'] == 'gt'
    assert volume['left']['indicator'] == 'VOLUME_RATIO' and volume['left']['params']['period'] == 12
    assert volume['right']['value'] == 1.75


@pytest.mark.parametrize('option, operator', [('above', 'gt'), ('cross_above', 'cross_above')])
def test_standing_above_requires_a_choice_between_state_and_event(option, operator):
    text = '当收盘价站上二十日均线，就买入'
    resolved = resolve(text, {'ma_stand_above': option})
    replacement, = resolved['replacements']
    assert replacement['original_clause'] == text
    condition = replacement['effective_clause'].removeprefix('当').removesuffix('就买入').rstrip(',')
    parsed = parse_condition(condition)
    assert parsed['op'] == operator and parsed['right']['params']['period'] == 20


@pytest.mark.parametrize('option, offsets', [('state', [0, 1, 2]), ('first', [0, 1, 2, 3])])
def test_rsi_threshold_and_period_preserved_with_optional_first_hit(option, offsets):
    text = '14日RSI低于20且钝化时买入'
    assert {q['field'] for q in resolve(text)['clarifications']} == {'rsi_bars', 'rsi_trigger'}
    result = resolve(text, {'rsi_bars': 'bars_3', 'rsi_trigger': option})
    condition = parse_condition(result['replacements'][0]['effective_clause'].removesuffix('时买入'))
    comparisons = condition['conditions']
    assert [item['left']['offset'] for item in comparisons] == offsets
    assert all(item['right']['value'] == 20 and item['left']['params']['period'] == 14 for item in comparisons)
    assert [item['op'] for item in comparisons] == ['lt'] * 3 + (['gte'] if option == 'first' else [])


def test_rsi_missing_period_and_inclusive_boundary_are_confirmed_without_guessing():
    text = 'RSI在20以下钝化时买入'
    partial = resolve(text, {'rsi_period': 'period_14', 'rsi_trigger': 'first'})
    assert {q['field'] for q in partial['clarifications']} == {'rsi_comparison', 'rsi_bars'}
    assert partial['segments'][0]['text'] == text and partial['replacements'] == []
    result = resolve(text, {'rsi_period': {'period': 9}, 'rsi_trigger': 'first',
                            'rsi_comparison': 'lte', 'rsi_bars': {'bars': 1}})
    condition = parse_condition(result['replacements'][0]['effective_clause'].removesuffix('时买入'))
    comparisons = condition['conditions']
    assert [item['op'] for item in comparisons] == ['lte', 'gt']
    assert all(item['right']['value'] == 20 and item['left']['params']['period'] == 9 for item in comparisons)


@pytest.mark.parametrize('text', ['股价站上20日均线时买入', '盘中放量时买入', '不放量时买入',
                                  '收盘价站上20日均线时不要买入', '14日RSI钝化时买入',
                                  '收盘价上穿5日均线且放量且低于预期时买入',
                                  '收盘价上穿5日均线且放量时买入？',
                                  '收盘价上穿5日均线且放量且盘中大单明显时买入'])
def test_unbound_unsupported_and_negated_language_is_not_rewritten(text):
    result = resolve(text)
    assert result['clarifications'] == [] and result['replacements'] == []
    assert result['segments'][0]['text'] == text


def test_reject_unknown_duplicate_and_invalid_answers():
    from app.ai.terms import resolve_terms

    segments = [{'id': 's1', 'text': '放量时买入'}]
    question, = resolve_terms(segments)['clarifications']
    valid = {'question_id': question['id'], 'option_id': 'previous_20_x1_5'}
    bad = [[{**valid, 'question_id': 'another'}], [valid, valid], [{**valid, 'option_id': 'bad'}],
           [{**valid, 'values': {'period': 10}}], [{**valid, 'option_id': 'custom'}],
           [{**valid, 'option_id': 'custom', 'values': {'period': True, 'multiple': 1.5}}],
           [{**valid, 'option_id': 'custom', 'values': {'period': 251, 'multiple': 1.5}}],
           [{**valid, 'option_id': 'custom', 'values': {'period': 20, 'multiple': float('inf')}}]]
    for answers in bad:
        with pytest.raises(ValueError):
            resolve_terms(segments, answers)


def test_repeated_identical_citations_cannot_receive_conflicting_interpretations():
    from app.ai.terms import resolve_terms

    segments = [{'id': 's1', 'text': '收盘价站上5日均线时买入。收盘价站上5日均线时买入。'}]
    first, second = resolve_terms(segments)['clarifications']
    assert first['id'] != second['id']
    with pytest.raises(ValueError, match='同一段的相同原句'):
        resolve_terms(segments, [{'question_id': first['id'], 'option_id': 'above'},
                                 {'question_id': second['id'], 'option_id': 'cross_above'}])


def test_boolean_pause_preserves_rule_boundaries_and_exceptions():
    text = '收盘价上穿5日均线，且日线量比(20)大于1.5时买入，除非次日停牌。'
    assert split_daily_clauses(text) == ['收盘价上穿5日均线，且日线量比(20)大于1.5时买入', '除非次日停牌']
    assert parse_condition('收盘价上穿5日均线，且日线量比(20)大于1.5')['op'] == 'and'
    assert parse_condition('收盘价上穿5日均线，且不放量') is None
    assert split_daily_clauses('放量时买入，同时清仓') == ['放量时买入', '同时清仓']
