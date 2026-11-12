"""Language gate contracts; every model response here is an explicit test double.

These exercise acceptance, rejection and audit behavior, not real model quality.
"""
import json

import pytest

from app.ai import review
from app.config import Settings
from app.models import Segment


def proposed(segment_id, original, corrected, *, certain=True):
    return dict(segment_id=segment_id, original=original, corrected=corrected,
                reason='测试替身：根据上下文提出局部识别修正', certain=certain)


def run_review(monkeypatch, changes, *, questions=(), segments=None):
    response = json.dumps(dict(changes=changes, questions=list(questions)), ensure_ascii=False)
    # Only the external model boundary is replaced. Parsing, citation validation,
    # correction decisions, immutable snapshots and reports run production code.
    monkeypatch.setattr(review, 'complete', lambda *args, **kwargs: response)
    if segments is None:
        segments = [Segment(id=c['segment_id'], text=c['original']) for c in changes]
    before = [s.model_dump() for s in segments]
    revised, audit = review.review_transcript(Settings(), segments)
    assert [s.model_dump() for s in segments] == before
    return revised, audit


@pytest.mark.parametrize('original,corrected', [
    ('本質是在和油脂比認知,衡量化拼速度', '本質是在和游資比認知,和量化拼速度'),
    ('如果你今天打手把,明天追二把,後天又去衝最高把',
     '如果你今天打首板,明天追二板,後天又去衝最高板'),
])
def test_real_transcript_examples_accept_local_model_corrections(monkeypatch, original, corrected):
    source = Segment(id='s1', start=3.25, end=8.5, text=original)
    change = proposed('s1', original, corrected)
    revised, audit = run_review(monkeypatch, [change], segments=[source])
    assert revised[0].model_dump() == dict(id='s1', start=3.25, end=8.5, text=corrected)
    assert audit['status'] == 'reviewed' and audit['questions'] == []
    assert audit['transcript_version'] == 'corrected'
    assert audit['changes'] == [{k: v for k, v in change.items() if k != 'certain'}]


@pytest.mark.parametrize('original,corrected', [
    ('这段讲解的逻缉很清晰', '这段讲解的逻辑很清晰'),
    ('市场情续需要结合背景理解', '市场情绪需要结合背景理解'),
    ('盘后复磐可以帮助整理笔记', '盘后复盘可以帮助整理笔记'),
    ('理解讲解节凑以后再整理笔记', '理解讲解节奏以后再整理笔记'),
    ('认真得整理这段录音', '认真地整理这段录音'),
    ('这段录音表达内容很清晰', '这段录音表达的内容很清晰'),
    ('整理笔记时先先梳理背景', '整理笔记时先梳理背景'),
    ('如果市场情续不稳定，不要买入。', '如果市场情绪不稳定，不要买入。'),
    ('价格高于10元时关注市场情续。', '价格高于10元时关注市场情绪。'),
    ('目标仓为50%，先复磐市场情续。', '目标仓位50%，先复盘市场情绪。'),
    ('5日均现高于20日均线时买入', '5日均线高于20日均线时买入。'),
    ('如果均现不稳定，先观察', '如果均线不稳定，先观察。'),
    ('股价高于二十日军线时买入，收盘下跌百分之五只损。',
     '股价高于二十日均线时买入，收盘下跌百分之五止损。'),
])
def test_unknown_local_recognition_and_grammar_errors_are_not_a_closed_glossary(
        monkeypatch, original, corrected):
    revised, audit = run_review(monkeypatch, [proposed('s1', original, corrected)])
    assert revised[0].text == corrected
    assert len(audit['changes']) == 1 and audit['questions'] == []


@pytest.mark.parametrize('original,corrected', [
    ('10元买入', '20元买入'),
    ('1.5元买入', '15元买入'),
    ('目标仓位50%', '目标仓位50'),
    ('目标仓位五成', '目标仓位六成'),
    ('目标半仓等待信号', '目标满仓等待信号'),
    ('价格10元时关注', '价格10美元时关注'),
    ('收盘后买入', '收盘前买入'),
    ('10元买入', '10元卖出'),
    ('股价占上均线后买入', '股价站上均线后买入'),
    ('价格跌跛20元就卖出', '价格跌破20元就卖出'),
    ('这次操作只损失五元', '这次操作止损失五元'),
    ('信号确认后加仓', '信号确认后减仓'),
    ('短线做多观察', '短线做空观察'),
    ('不要买入', '要买入'),
    ('没有信号先观察', '已有信号先观察'),
    ('价格大于10元买入', '价格小于10元买入'),
    ('价格大于10元买入', '价格大于等于10元买入'),
    ('价格>10元买入', '价格>=10元买入'),
    ('价格≥10元买入', '价格≤10元买入'),
    ('价格比均线高时观察', '价格比均线低时观察'),
    ('价格在均线上方时观察', '价格在均线下方时观察'),
    ('如果均线稳定就观察', '即使均线稳定就观察'),
    ('只有均线稳定才观察', '只要均线稳定才观察'),
    ('价格稳定并且量能充足才观察', '价格稳定或者量能充足才观察'),
    ('不要买入', '不，要买入'),
    ('如果不能买入就等待', '如果不能，买入就等待'),
    ('如果均线稳定，就观察', '如果均线，稳定就观察'),
    ('信号出现后买入？', '信号出现后买入。'),
    ('信号出现后买入吗', '信号出现后买入'),
    ('先记录市场情续，买入10元股票', '先记录市场情绪，卖出10元股票'),
])
def test_trading_meaning_and_punctuation_scope_still_require_confirmation(
        monkeypatch, original, corrected):
    revised, audit = run_review(monkeypatch, [proposed('s1', original, corrected)])
    assert revised[0].text == original
    assert not audit['changes']
    assert audit['status'] == 'needs_confirmation' and audit['questions']


@pytest.mark.parametrize('original,corrected', [
    ('这段录音讲解市场背景与观察方法', '市场背景复杂，应当耐心学习并做好记录'),
    ('这段录音详细讲解市场背景与观察方法并附有笔记',
     '这段录音详细讲解特别适合积极参与的市场背景与观察方法并附有笔记'),
    ('逻缉和情续以及节凑都写在复磐笔记里', '逻辑和情绪以及节奏都写在复盘摘要里'),
    ('甲', '乙'),
])
def test_long_or_dense_rewrites_are_not_automatic(monkeypatch, original, corrected):
    revised, audit = run_review(monkeypatch, [proposed('s1', original, corrected)])
    assert revised[0].text == original and not audit['changes'] and audit['questions']


def test_mixed_review_keeps_originals_proposals_and_questions_per_segment(monkeypatch):
    changes = [proposed('s1', '市场情续需要结合背景理解', '市场情绪需要结合背景理解'),
               proposed('s2', '目标仓位50%', '目标仓位80%'),
               proposed('s3', '盘后复磐整理笔记', '盘后复盘整理笔记', certain=False)]
    questions = ['s3 的同音词仍需听音确认', '仓位描述是否完整？']
    untouched = Segment(id='s4', text='保留这段原始说明。')
    segments = [Segment(id=c['segment_id'], text=c['original']) for c in changes] + [untouched]
    revised, audit = run_review(monkeypatch, changes, questions=questions, segments=segments)
    assert [s.text for s in revised] == ['市场情绪需要结合背景理解', '目标仓位50%',
                                       '盘后复磐整理笔记', '保留这段原始说明。']
    assert [c['segment_id'] for c in audit['changes']] == ['s1']
    assert all(q in audit['questions'] for q in questions)
    assert audit['status'] == 'needs_confirmation'
    rejected = audit['rejected_changes']
    assert [c['segment_id'] for c in rejected] == ['s2', 's3']
    for record, change in zip(rejected, changes[1:]):
        assert all(record[key] == value for key, value in change.items())
        assert record['rejection_reason']


@pytest.mark.parametrize('fault', ['unknown_segment', 'wrong_original', 'duplicate_segment'])
def test_invalid_proposal_citations_abort_the_review(monkeypatch, fault):
    change = proposed('s1', '市场情续需要结合背景理解', '市场情绪需要结合背景理解')
    segments = [Segment(id='s1', text=change['original'])]
    changes = [change]
    if fault == 'unknown_segment':
        change['segment_id'] = 's2'
    elif fault == 'wrong_original':
        change['original'] = '错误的原文'
    else:
        changes.append(dict(change))
    with pytest.raises(ValueError, match='未保存草案'):
        run_review(monkeypatch, changes, segments=segments)
