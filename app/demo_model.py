"""Fixed model replies for the isolated Phase 11 sample launcher."""

import json

from app.ai.client import parse_json
from app.models import Segment


DEMO_TITLE = '日线放量与均线演示'
DEMO_MODEL = 'phase-11-demo-fixture'
DEMO_TEXT = '\n'.join((
    '600000.SH，日线。',
    '收盘价站上5日均线且放量时买入。',
    '收盘价跌破5日均线时全部卖出。',
    '目标仓位20%。',
))

_UNSUPPORTED = '演示模型替身仅支持本演示的内置资料及连接探测。'
_CHOICES = {
    'ma_stand_above': ('cross_above', '把站上解释为由下向上穿越，避免持续在均线上方时重复触发。'),
    'volume_ratio': ('previous_20_x1_5', '原文没有给量比阈值，采用此前20日均量的1.5倍作为演示假设。'),
}


def _draft(segments):
    def evidence(segment, quote):
        return [{'segment_id': segment.id, 'quote': quote}]

    context, *rules = segments
    return {
        'title': '放量站上五日均线策略',
        'asset': {'value': '600000.SH', 'evidence': evidence(context, '600000.SH')},
        'timeframe': {'value': '日线', 'evidence': evidence(context, '日线')},
        'rules': [
            {'kind': kind, 'text': segment.text, 'evidence': evidence(segment, segment.text)}
            for kind, segment in zip(('buy', 'sell', 'position'), rules)
        ],
        'questions': [],
    }


def _decisions(clarifications, buy):
    if len(clarifications) != len(_CHOICES):
        raise ValueError(_UNSUPPORTED)
    seen_fields, seen_ids, decisions = set(), set(), []
    for question in clarifications:
        field, question_id = question['field'], question['id']
        option_id, reason = _CHOICES[field]
        if (field in seen_fields or not isinstance(question_id, str) or not question_id or question_id in seen_ids
                or question['segment_id'] != buy.id or question['quote'] != buy.text.removesuffix('。')
                or not any(option['id'] == option_id for option in question['options'])):
            raise ValueError(_UNSUPPORTED)
        seen_fields.add(field)
        seen_ids.add(question_id)
        decisions.append({'question_id': question_id, 'option_id': option_id, 'reason': reason})
    return {'decisions': decisions}


def demo_completion(payload: dict) -> str:
    """Return a model response for a supported prompt about the built-in text."""
    try:
        if payload['model'] != DEMO_MODEL or payload['stream'] is not False:
            raise ValueError(_UNSUPPORTED)
        messages = payload['messages']
        if messages == [{'role': 'user', 'content': 'Reply with OK only.'}]:
            return 'OK'
        system, user = messages
        if system['role'] != 'system' or user['role'] != 'user':
            raise ValueError(_UNSUPPORTED)
        source = parse_json(user['content'])
        segments = [Segment.model_validate(item, strict=True) for item in source['untrusted_transcript']]
        if ('\n'.join(segment.text for segment in segments) != DEMO_TEXT
                or len(segments) != 4 or len({segment.id for segment in segments}) != 4
                or any(segment.start is not None for segment in segments)):
            raise ValueError(_UNSUPPORTED)

        if set(source) == {'untrusted_strategy', 'untrusted_transcript', 'clarifications'}:
            response = _decisions(source['clarifications'], segments[1])
        elif set(source) == {'untrusted_transcript'} and system['content'].startswith('你是语音转写校对员。'):
            response = {'changes': [], 'questions': []}
        elif set(source) == {'untrusted_transcript'} and system['content'].startswith('你是股票教学资料的摘录助手。'):
            response = _draft(segments)
        else:
            raise ValueError(_UNSUPPORTED)
        return json.dumps(response, ensure_ascii=False)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError(_UNSUPPORTED) from None
