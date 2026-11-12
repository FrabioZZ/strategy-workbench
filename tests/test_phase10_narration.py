import json
from types import SimpleNamespace

from app.adapters import extractor
from app.ai.narration import strategy_review_questions, strategy_segments
from app.models import Segment


def test_strategy_extraction_omits_narration_and_keeps_trading_questions(monkeypatch):
    intro = '我是基友。'
    buy = '收盘价上穿五日均线且放量时买入'
    sell = '收盘价下穿五日均线时全部卖出'
    position = '目标仓位25%'
    segments = [
        Segment(id='s1', text=intro, start=0, end=1),
        Segment(id='s2', text=f'大家好，{buy}。{position}。', start=1, end=3),
        Segment(id='s3', text=f'沪深主板股票。日线。{sell}。', start=3, end=5),
        Segment(id='s4', text='欢迎在评论区交流换手率话题。', start=5, end=6),
    ]
    report = {'questions': ['s1: 我是基友是昵称还是同音词误识别？',
                            's2: 放量指哪个周期？', '另有未定位的疑点。']}

    def review_model_reply(*_args):
        return segments, report

    payload = {}

    def citation(segment_id, quote):
        return [{'segment_id': segment_id, 'quote': quote}]

    def extract_model_reply(_settings, messages, _schema):
        payload.update(json.loads(messages[-1]['content']))
        return json.dumps({
            'title': '均线放量',
            'asset': {'value': '沪深主板股票', 'evidence': citation('s3', '沪深主板股票')},
            'timeframe': {'value': '日线', 'evidence': citation('s3', '日线')},
            'rules': [
                {'kind': 'buy', 'text': buy, 'evidence': citation('s2', buy)},
                {'kind': 'sell', 'text': sell, 'evidence': citation('s3', sell)},
                {'kind': 'position', 'text': position, 'evidence': citation('s2', position)},
            ],
            'questions': [],
        }, ensure_ascii=False)

    monkeypatch.setattr(extractor, 'review_transcript', review_model_reply)
    monkeypatch.setattr(extractor, 'complete', extract_model_reply)
    config = SimpleNamespace(ai_provider='test', ai_model='test')
    result = extractor.Extractor(config).extract_reviewed(segments)

    projected = payload['untrusted_transcript']
    assert [segment['id'] for segment in projected] == ['s2', 's3']
    assert projected[0]['text'] == f'{buy}。{position}。'
    assert projected[0]['start'] == 1 and projected[0]['end'] == 3
    assert result['corrected_segments'] == [segment.model_dump() for segment in segments]
    assert result['ai_review']['questions'] == report['questions']
    assert report['questions'][0] not in result['strategy']['questions']
    assert all(question in result['strategy']['questions'] for question in report['questions'][1:])
    assert result['strategy']['rules'][0]['evidence'][0]['quote'] == buy


def test_strategy_projection_keeps_example_and_scope_context():
    text = '大家好。本期我们来讲解日线策略。接下来我们看一个例子。收盘价跌破五日均线就清仓。感谢观看。'
    projected = strategy_segments([{'id': 's1', 'text': text}])

    assert projected == [{
        'id': 's1',
        'text': '本期我们来讲解日线策略。接下来我们看一个例子。收盘价跌破五日均线就清仓。',
    }]


def test_social_call_to_action_does_not_hide_trading_exception():
    text = '大家好，欢迎点赞关注。收盘价上穿五日均线就买，但缩量时不买。喜欢的话点个赞。'
    assert strategy_segments([{'id': 's1', 'text': text}]) == [
        {'id': 's1', 'text': '收盘价上穿五日均线就买，但缩量时不买。'},
    ]


def test_review_questions_keep_possible_asr_trading_changes():
    segments = [{'id': 's1', 'text': '我是基友。'}, {'id': 's2', 'text': '大家好。'}]
    report = {
        'questions': ['s1：昵称是否识别有误？', 's2 的拟议校正未自动采用，请核对。',
                      's1：昵称是否识别有误，是否也缺少仓位？'],
        'rejected_changes': [{'segment_id': 's1', 'corrected': '我是机构。'},
                             {'segment_id': 's2', 'corrected': '大跌买入。'}],
    }

    assert strategy_review_questions(report, segments) == report['questions'][1:]
