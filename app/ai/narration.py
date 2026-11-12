"""Project the original clauses relevant to compiling a strategy."""
import re

from app.ai.capabilities import split_daily_clauses
from app.ai.mapping_language import is_plain_narration


_TOPIC = r'(?:换手率|题材|板块|盘口|分时|竞价|量比|RSI|MACD|均线|成交量)'
_NARRATION = re.compile(
    r'(?:大家好|各位好)?(?:(?:我是|我叫)(?:基友|基哥)|我是机构)'
    r'|(?:我的)?(?:昵称|网名)(?:是|叫)[\u3400-\u9fffA-Za-z0-9_]{1,16}'
    r'|(?:欢迎(?:大家)?|记得|别忘了|喜欢(?:的话)?(?:就|请)?)(?:给我)?(?:点个赞|点赞|关注|点赞关注|点赞收藏|点赞收藏关注)'
    rf'|欢迎(?:大家)?在评论区(?:交流|讨论)(?:有关|关于)?{_TOPIC}(?:和{_TOPIC})*(?:的)?话题',
    re.IGNORECASE,
)
_CONTEXT = re.compile(r'例子|示例|(?:日线|双均线|均线|阈值)(?:方法|策略)')
_SEGMENT_ID = re.compile(r'(?<![A-Za-z0-9_])s[1-9][0-9]*(?![A-Za-z0-9_])', re.IGNORECASE)
_RULE_QUESTION = re.compile(
    r'买入|买卖|卖出|清仓|仓位|加仓|减仓|止盈|止损|标的|股票代码|周期|阈值|比例|'
    r'过滤|筛选|条件|收盘|开盘|限制|例外|缺少|未提取|未说明|(?<![A-Za-z0-9_])\d'
)


def is_strategy_narration(clause: str) -> bool:
    clause = ''.join(clause.split())
    return is_plain_narration(clause) or _NARRATION.fullmatch(clause) is not None


def _strategy_text(text: str) -> str:
    # Topic or example introductions can qualify an adjacent rule.
    clauses = [(clause, is_strategy_narration(clause) and not _CONTEXT.search(clause))
               for clause in split_daily_clauses(text)]
    if not any(excluded for _, excluded in clauses):
        return text

    ranges = []
    previous_end = 0
    retained_start = None
    for clause, excluded in clauses:
        start = text.index(clause, previous_end)
        previous_end = start + len(clause)
        if excluded:
            if retained_start is not None:
                ranges.append(text[retained_start:start].rstrip())
                retained_start = None
        elif retained_start is None:
            retained_start = start

    if retained_start is not None:
        ranges.append(text[retained_start:])
    return '\n'.join(ranges)


def strategy_segments(segments: list[dict]) -> list[dict]:
    """Keep exact rule spans and segment metadata without changing the source."""
    projected = []
    for segment in segments:
        text = _strategy_text(segment['text'])
        if text:
            projected.append({**segment, 'text': text})
    return projected


def strategy_review_questions(report: dict | None, segments: list[dict]) -> list[str]:
    """Keep review questions whose effect on strategy meaning is unresolved."""
    report = report or {}
    narration_ids = {segment['id'] for segment in segments if not _strategy_text(segment['text'])}
    for change in report.get('rejected_changes', []):
        if _strategy_text(change['corrected']):
            narration_ids.discard(change['segment_id'])

    questions = []
    for question in report.get('questions', []):
        segment_ids = {match.lower() for match in _SEGMENT_ID.findall(question)}
        if not segment_ids or not segment_ids <= narration_ids or _RULE_QUESTION.search(question):
            questions.append(question)
    return questions
