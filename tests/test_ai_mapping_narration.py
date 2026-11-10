"""Narration may accompany a strategy; omitted trading conditions may not.

These exercise the real mapper with local fixtures, without calling a model.
"""
import copy

import pytest

from app.ai.mapping import validate_proposal
from test_ai_backend import ma_fixture, source_fixture


@pytest.mark.parametrize('narration', [
    '大家好，今天和大家分享这个方法，感谢观看。',
    '各位朋友好！欢迎来到本期视频。',
    '这一期我们来讲解日线策略。接下来我们看一个例子。',
    '下面用图表来说明这个方法。为了方便理解，我把步骤写在屏幕上。',
    '刚才我们介绍了这个方法，接下来继续讲解。',
    '这里的图表只是为了方便理解。均线用于观察价格趋势。',
    '今天的讲解就到这里，谢谢大家的收看！我们下期再见。',
    '喜欢本期视频的朋友可以点赞收藏，欢迎在评论区交流。',
    '朋友们好\n本期我们来介绍这个方法\n谢谢大家',
])
def test_plain_narration_does_not_block_supported_threshold(narration):
    source, proposal = source_fixture()
    source['transcript'].append({'id': 's4', 'text': narration})
    original = copy.deepcopy(source)

    rules, _, questions, evidence = validate_proposal(proposal, source)

    assert rules == {'type': 'threshold', 'buy_below': 10, 'sell_above': 11,
                     'target_pct': 50, 'stop_loss_pct': None}, questions
    assert not questions
    assert source == original
    assert evidence == [{**ref, 'transcript_version': 'original'} for ref in proposal['evidence']]


@pytest.mark.parametrize('version', ['original', 'corrected'])
def test_rule_and_citation_can_include_adjacent_narration_without_rewriting(version):
    source, proposal = source_fixture()
    text = '接下来我们看一个例子。收盘价小于等于10元买入，目标仓位50%。感谢观看！'
    source['transcript'][1]['text'] = text
    source['strategy']['rules'][0]['text'] = text
    for ref in proposal['evidence']:
        if ref['segment_id'] == 's2':
            ref['quote'] = text
    source['evidence_transcript_version'] = version
    if version == 'corrected':
        source['corrected_transcript'] = copy.deepcopy(source['transcript'])
        source['transcript'][1]['text'] = text.replace('收盘价', '收盘架')
    original = copy.deepcopy(source)

    rules, _, questions, evidence = validate_proposal(proposal, source)

    assert rules is not None, questions
    assert not questions
    assert source == original
    assert evidence == [{**ref, 'transcript_version': version} for ref in proposal['evidence']]


def test_plain_narration_does_not_block_supported_dual_ma():
    source, proposal = ma_fixture()
    source['transcript'].append({'id': 's5', 'text': '今天我们来讲解双均线策略。感谢大家观看。'})

    rules, _, questions, _ = validate_proposal(proposal, source)

    assert rules == {'type': 'ma', 'fast': 5, 'slow': 20,
                     'target_pct': 50, 'stop_loss_pct': None}, questions


@pytest.mark.parametrize('condition', [
    'ROE需要高于15%',
    '任意指标需要高于8%',
    '指标甲需达到12％',
    '今天和大家分享ROE高于15%的方法',
    '下面用图表来说明这个方法，但还需要盈利增长率大于20%',
    '次日午后买入',
    '每周五才买入',
    '今天讲解的方法不要买入',
    '不再使用前面的卖出条件',
    '目标仓位60%',
    '这里还要等趋势转强才能买入',
    '卖出时保留一半仓位',
])
def test_narration_never_hides_an_unmapped_condition(condition):
    source, proposal = source_fixture()
    source['transcript'].append({
        'id': 's4', 'text': '大家好。' + condition + '。感谢观看。',
    })
    original = copy.deepcopy(source)

    rules, _, questions, evidence = validate_proposal(proposal, source)

    assert rules is None
    assert any('s4' in question for question in questions)
    assert source == original
    assert evidence == [{**ref, 'transcript_version': 'original'} for ref in proposal['evidence']]


def test_narration_alone_cannot_prove_a_mapping_field():
    source, proposal = source_fixture()
    source['transcript'].append({'id': 's4', 'text': '今天和大家分享这个方法'})
    proposal['evidence'][0] = {
        'field': 'buy_below', 'segment_id': 's4', 'quote': '今天和大家分享这个方法',
    }

    rules, _, questions, _ = validate_proposal(proposal, source)

    assert rules is None
    assert any('buy_below' in question for question in questions)


def test_unknown_non_numeric_sentence_still_needs_confirmation():
    source, proposal = source_fixture()
    source['transcript'].append({'id': 's4', 'text': '这个方法需要结合其他因素灵活操作。'})

    rules, _, questions, _ = validate_proposal(proposal, source)

    assert rules is None
    assert any('s4' in question for question in questions)
