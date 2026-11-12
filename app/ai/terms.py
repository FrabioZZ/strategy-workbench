"""Versioned daily term choices. Only explicit answers change a rule projection."""

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
import json
import math
import re

from pydantic import TypeAdapter

from app.ai.capabilities import BUY_ACTION, SELL_ACTION, normalized, parse_condition, split_daily_clauses
from app.ai.mapping_language import NUMBER, normalize_rule_numbers
from app.trading.conditions import Condition, validate_tree
from app.trading.indicators import REGISTRY


TERM_VERSION = 'daily-terms-v1'

_RULE_CLAUSE = re.compile(
    rf'(?P<prefix>如果|当(?!日))?(?P<condition>.+?)(?P<suffix>,?(?:的时候|时|则|就)?(?:{BUY_ACTION}|{SELL_ACTION}))'
)
_TERMS = re.compile(
    rf'(?:(?P<rsi>\d+日RSI|RSI\(\d+\)|RSI)'
    rf'(?:(?P<comparison>不高于|小于等于|低于|小于|<=|≤|<)(?P<threshold>{NUMBER})'
    rf'(?:,?(?:且|并且|而且|同时))钝化|在(?P<boundary>{NUMBER})以下钝化))'
    r'|(?P<ma>(?:日线)?收盘价)站上(?P<average>\d+日(?:简单|指数)?均线)'
    r'|(?P<volume>放量)', re.IGNORECASE,
)
_CONDITION = TypeAdapter(Condition)


@dataclass(frozen=True)
class NumberField:
    name: str
    label: str
    min: int | float
    max: int | float | None = None
    step: int | str = 1

    def validate(self, value):
        error = f'“{self.label}”取值无效。'
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid or value < self.min or (self.max is not None and value > self.max):
            raise ValueError(error)
        if self.step == 1:
            if value != int(value):
                raise ValueError(error)
            return int(value)
        return value


@dataclass(frozen=True)
class Choice:
    label: str
    values: dict


@dataclass(frozen=True)
class Question:
    field: str
    label: str
    options: dict[str, Choice]
    custom_fields: tuple[NumberField, ...] = ()

    def describe(self, question_id, segment_id, clause):
        result = dict(id=question_id, segment_id=segment_id, quote=clause, field=self.field,
                      question=self.label, options=[dict(id=key, label=choice.label, values=choice.values)
                                                   for key, choice in self.options.items()])
        if self.custom_fields:
            result['custom_fields'] = [{k: v for k, v in asdict(field).items() if v is not None}
                                       for field in self.custom_fields]
        return result

    def answer(self, option_id, values):
        if option_id == 'custom' and self.custom_fields:
            if set(values) != {field.name for field in self.custom_fields}:
                raise ValueError(f'“{self.label}”的自定义参数不完整或包含未知字段。')
            return {field.name: field.validate(values[field.name]) for field in self.custom_fields}
        if option_id not in self.options or values:
            raise ValueError(f'“{self.label}”的选项或参数无效。')
        return dict(self.options[option_id].values)


@dataclass(frozen=True)
class Term:
    match: re.Match
    questions: tuple[Question, ...]
    expand: Callable[[dict], str]


def _period(indicator, label):
    bounds = REGISTRY[indicator]['params']['period']
    return NumberField('period', label, bounds['minimum'], bounds['maximum'])


def _term(match):
    if match['volume']:
        question = Question('volume_ratio', '“放量”如何判定？', {
            'previous_20_x1_5': Choice('当日成交量大于此前 20 根日线均量的 1.5 倍（不含当日）',
                                       dict(period=20, multiple=1.5)),
            'previous_20_x2': Choice('当日成交量大于此前 20 根日线均量的 2 倍（不含当日）',
                                     dict(period=20, multiple=2)),
        }, (_period('VOLUME_RATIO', '均量周期（不含当日）'), NumberField('multiple', '成交量倍数', 1, step='any')))

        def volume(values):
            multiple = format(Decimal(str(values['multiple'])), 'f')
            return f"日线量比({values['period']})大于{multiple}"

        return Term(match, (question,), volume)

    if match['ma']:
        question = Question('ma_stand_above', '“站上”如何判定？', {
            'above': Choice('本根收盘价高于对应均线', dict(operator='高于')),
            'cross_above': Choice('上一根在对应均线上或以下，本根在对应均线之上', dict(operator='上穿')),
        })

        def moving_average(values):
            return match['ma'] + values['operator'] + match['average']

        return Term(match, (question,), moving_average)

    return _rsi_term(match)


def _rsi_term(match):
    threshold = match['threshold'] if match['threshold'] is not None else match['boundary']
    comparison = match['comparison']
    questions = []
    if not comparison:
        questions.append(Question('rsi_comparison', f'“{threshold} 以下”包含 {threshold} 吗？', {
            'lt': Choice(f'低于 {threshold}', dict(operator='<')),
            'lte': Choice(f'低于或等于 {threshold}', dict(operator='<=')),
        }))
    if match['rsi'].upper() == 'RSI':
        questions.append(Question('rsi_period', 'RSI 用多少根日线计算？', {
            'period_14': Choice('14 根日线', dict(period=14)),
        }, (_period('RSI', 'RSI 计算周期'),)))
    questions.extend((
        Question('rsi_bars', 'RSI 需要连续几根日线满足阈值？', {
            'bars_2': Choice('连续 2 根日线', dict(bars=2)),
            'bars_3': Choice('连续 3 根日线', dict(bars=3)),
        }, (NumberField('bars', '连续满足的日线数', 1, 15),)),
        Question('rsi_trigger', '连续满足期间，何时判定条件成立？', {
            'state': Choice('达到连续根数后，每根继续满足时均成立', dict(trigger='state')),
            'first': Choice('仅在首次达到连续根数的那一根成立', dict(trigger='first')),
        }),
    ))

    def persistence(values):
        rsi = f"RSI({values['period']})" if 'period' in values else match['rsi'].upper()
        operator = values.get('operator') or ('<=' if comparison in ('不高于', '小于等于', '<=', '≤') else '<')
        bars = values['bars']
        comparisons = [f'{rsi}[{offset}]{operator}{threshold}' for offset in range(bars)]
        if values['trigger'] == 'first':
            complement = '>' if operator == '<=' else '>='
            comparisons.append(f'{rsi}[{bars}]{complement}{threshold}')
        return '(' + '且'.join(comparisons) + ')'

    return Term(match, tuple(questions), persistence)


def _expand_condition(condition, terms, values):
    parts, start = [], 0
    for term, selected in zip(terms, values):
        parts.append(condition[start:term.match.start()])
        parts.append(term.expand(selected))
        start = term.match.end()
    parts.append(condition[start:])
    return ''.join(parts)


def _valid_condition(text):
    try:
        parsed = parse_condition(text)
        if parsed is None:
            return False
        validate_tree(_CONDITION.validate_python(parsed, strict=True))
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def _find_clause_terms(clause):
    rule = _RULE_CLAUSE.fullmatch(normalize_rule_numbers(normalized(clause)))
    if rule is None:
        return None, []
    condition = rule['condition']
    terms = [_term(match) for match in _TERMS.finditer(condition)]
    if not terms:
        return None, []
    # Probe the grammar using supported options. A probe is never adopted as a decision.
    probes = [{name: value for q in term.questions for name, value in next(iter(q.options.values())).values.items()}
              for term in terms]
    if not _valid_condition(_expand_condition(condition, terms, probes)):
        return None, []
    return rule, terms


def _question_id(segment_id, clause_start, clause, term_start, field):
    identity = json.dumps((TERM_VERSION, segment_id, clause_start, clause, term_start, field), ensure_ascii=False)
    return sha256(identity.encode('utf-8')).hexdigest()[:24]


def _submitted_answers(answers):
    submitted = {}
    for answer in answers:
        if not isinstance(answer, dict) or set(answer) - {'question_id', 'option_id', 'values'}:
            raise ValueError('术语确认格式无效。')
        question_id = answer.get('question_id')
        option_id = answer.get('option_id')
        values = answer.get('values', {})
        if not isinstance(question_id, str) or not isinstance(option_id, str) or not isinstance(values, dict):
            raise ValueError('术语确认格式无效。')
        if question_id in submitted:
            raise ValueError('同一术语问题存在重复答案。')
        submitted[question_id] = (option_id, values)
    return submitted


def resolve_terms(segments: list[dict], answers: Iterable[dict] = ()) -> dict:
    """Build questions and apply answers to complete clauses with unchanged source evidence."""
    submitted = _submitted_answers(answers)
    projected, pending, decisions, replacements = [], [], [], []
    for segment in segments:
        segment_id, text = segment['id'], segment['text']
        parts, replaced_through, clause_end = [], 0, 0
        interpretations = {}
        for original in split_daily_clauses(text):
            clause_start = text.index(original, clause_end)
            clause_end = clause_start + len(original)
            rule, terms = _find_clause_terms(original)
            if not terms:
                continue
            clause_pending, clause_decisions, term_values = [], [], []
            for term in terms:
                values = {}
                for question in term.questions:
                    ident = _question_id(segment_id, clause_start, original, term.match.start(), question.field)
                    if ident not in submitted:
                        clause_pending.append(question.describe(ident, segment_id, original))
                        continue
                    option_id, supplied = submitted.pop(ident)
                    selected = question.answer(option_id, supplied)
                    values.update(selected)
                    label = question.options[option_id].label if option_id != 'custom' else '自定义参数'
                    clause_decisions.append(dict(question_id=ident, segment_id=segment_id, quote=original,
                                                 field=question.field, option_id=option_id, values=selected, label=label,
                                                 term_version=TERM_VERSION, original_clause=original))
                term_values.append(values)
            effective = None
            if not clause_pending:
                condition = _expand_condition(rule['condition'], terms, term_values)
                if not _valid_condition(condition):
                    raise ValueError('所选参数超出日线引擎的规则范围，请调整参数。')
                effective = (rule['prefix'] or '') + condition + rule['suffix']
                if interpretations.setdefault(original, effective) != effective:
                    raise ValueError('同一段的相同原句需要一致的术语定义。')
                parts.extend((text[replaced_through:clause_start], effective))
                replaced_through = clause_end
                replacements.append(dict(segment_id=segment_id, original_clause=original, effective_clause=effective))
            decisions.extend(dict(decision, effective_clause=effective) for decision in clause_decisions)
            pending.extend(clause_pending)
        parts.append(text[replaced_through:])
        projected.append(dict(segment, text=''.join(parts)))
    if submitted:
        raise ValueError('术语问题已失效或不存在，请重新生成执行参数。')
    return dict(segments=projected, clarifications=pending, decisions=decisions, replacements=replacements,
                version=TERM_VERSION)
