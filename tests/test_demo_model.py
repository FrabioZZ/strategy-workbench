import json

import pytest

from app.adapters.extractor import build_messages
from app.ai.terms import resolve_terms
from app.validation import parse_transcript, validate_strategy


def test_demo_model_extracts_only_the_sample_transcript():
    from app.demo_model import DEMO_MODEL, DEMO_TEXT, demo_completion

    segments = parse_transcript(DEMO_TEXT)
    request = {'model': DEMO_MODEL, 'messages': build_messages(segments), 'stream': False}
    draft = validate_strategy(demo_completion(request), segments)
    assert draft['asset']['value'] == '600000.SH'
    assert draft['timeframe']['value'] == '日线'
    assert [rule['kind'] for rule in draft['rules']] == ['buy', 'sell', 'position']
    assert not draft['executable']

    edited = parse_transcript(DEMO_TEXT.replace('20%', '99%'))
    with pytest.raises(ValueError):
        demo_completion({**request, 'messages': build_messages(edited)})
    with pytest.raises(ValueError):
        demo_completion({**request, 'model': 'different-model'})


def test_demo_model_selects_only_supported_fixture_options():
    from app.demo_model import DEMO_MODEL, DEMO_TEXT, demo_completion

    segments = [segment.model_dump() for segment in parse_transcript(DEMO_TEXT)]
    questions = resolve_terms(segments)['clarifications']
    assert {question['field'] for question in questions} == {'ma_stand_above', 'volume_ratio'}
    source = {'untrusted_transcript': segments, 'untrusted_strategy': {}, 'clarifications': questions}
    system = {'role': 'system', 'content': '只选择给定的术语口径。'}

    def request(payload):
        return {'model': DEMO_MODEL, 'stream': False, 'messages': [
            system, {'role': 'user', 'content': json.dumps(payload)},
        ]}

    decisions = json.loads(demo_completion(request(source)))['decisions']
    lookup = {question['id']: question['field'] for question in questions}
    assert {lookup[item['question_id']]: item['option_id'] for item in decisions} == {
        'ma_stand_above': 'cross_above', 'volume_ratio': 'previous_20_x1_5',
    }

    questions[0]['options'] = []
    with pytest.raises(ValueError):
        demo_completion(request(source))
