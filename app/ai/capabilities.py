"""Expose actual engine capabilities and verify supported daily condition wording.

The model proposes an AST; this module does not trust it as evidence of meaning.
Unknown qualifiers stay unresolved instead of being discarded during parsing.
"""
import json
import math
import re
from app.ai.mapping_language import NUMBER, STOP_BASIS, normalize_rule_numbers


ALIASES = {
    '开盘价': 'OPEN', '最高价': 'HIGH', '最低价': 'LOW', '收盘价': 'CLOSE',
    '日线收盘价': 'CLOSE',
    '成交量': 'VOLUME', '昨收价': 'PREV_CLOSE', '前收盘价': 'PREV_CLOSE',
    '均线': 'MA', '简单均线': 'MA', '指数均线': 'EMA',
    '涨幅': 'CHANGE_PCT', '涨跌幅': 'CHANGE_PCT', '高开幅度': 'GAP_PCT',
    '振幅': 'AMPLITUDE_PCT', '涨停价': 'LIMIT_UP', '跌停价': 'LIMIT_DOWN',
    '首板': 'FIRST_LIMIT_UP', '收盘涨停': 'IS_LIMIT_UP', '收盘跌停': 'IS_LIMIT_DOWN',
    '连板数': 'LIMIT_UP_STREAK', '日线量比': 'VOLUME_RATIO',
    '布林中轨': 'BOLL_MID', '布林上轨': 'BOLL_UPPER', '布林下轨': 'BOLL_LOWER',
}
OPERATORS = {
    '大于等于': 'gte', '不低于': 'gte', '>=': 'gte', '≥': 'gte',
    '小于等于': 'lte', '不高于': 'lte', '<=': 'lte', '≤': 'lte',
    '上穿': 'cross_above', '向上穿越': 'cross_above', '向上突破': 'cross_above',
    '下穿': 'cross_below', '向下穿越': 'cross_below', '跌破': 'cross_below',
    '大于': 'gt', '高于': 'gt', '>': 'gt', '小于': 'lt', '低于': 'lt', '<': 'lt',
    '不等于': 'ne', '!=': 'ne', '等于': 'eq', '==': 'eq', '=': 'eq',
}
BUY_ACTION = r'买入|买'
SELL_ACTION = r'全部卖出|全部卖掉|清仓'
_ACTION = re.compile(rf'\s*(?:的时候|时|则|就)?(?:{BUY_ACTION}|{SELL_ACTION})\s*(?=[，,。；;\n！!]|$)')
_CONNECTOR = r'(?:并且|而且|且|同时|或者|或)'
_AFTER_PAUSE = re.compile(rf'\s*{_CONNECTOR}')
_PAUSED_CONNECTOR = re.compile(rf',(?={_CONNECTOR})')


def split_daily_clauses(text):
    """Keep indicator arguments and pauses before explicit actions intact."""
    clauses, start, depth = [], 0, 0
    for i, char in enumerate(text):
        if char in '(（': depth += 1
        elif char in ')）': depth -= 1
        elif char in '，,。；;\n！!' and depth == 0 and not (char == '!' and text[i:i+2] == '!='):
            if char in '，,':
                if _ACTION.match(text, i+1) or normalized(text[start:i]) == STOP_BASIS:
                    continue
                if _AFTER_PAUSE.match(text, i+1) and not _ACTION.search(text, start, i):
                    continue
            if text[start:i].strip(): clauses.append(text[start:i].strip())
            start = i + 1
    if text[start:].strip(): clauses.append(text[start:].strip())
    return clauses


def normalized(text):
    return re.sub(r'\s+', '', text).replace('％', '%').replace('（', '(').replace('）', ')').replace('，', ',')


def indicator_catalog():
    # Imported at use time so the one authoritative registry is always read.
    from app.trading.indicators import registry
    return registry()


def engine_capabilities():
    from app.trading.models import Conditional
    from app.trading.conditions import OPERATORS as engine_operators
    return {
        'frequency': 'daily', 'indicators': indicator_catalog(),
        'condition_operators': engine_operators,
        'rule_schema': Conditional.model_json_schema(),
        'execution': '仅日线收盘判断，下一交易日开盘模拟执行；sell优先；未预热指标不可触发；offset仅允许过去。',
        'unsupported_conditions': ['盘中/竞价/盘口大单/炸板回封时点', '题材板块排名或主观强弱',
                                   '缺少数据的换手/流通市值筛选', '动态分仓、加仓及部分卖出'],
    }


def capability_prompt():
    return '''\n真实引擎能力（以下注册表与后端验证器同源；不能添加未注册指标）：
''' + json.dumps(engine_capabilities(), ensure_ascii=False) + '''
conditional规则必须完整包含buy、sell、target_pct，比较使用left/right，逻辑使用conditions。
参数不能猜：原文只说RSI、MACD或“放量”而未明确周期/参数/阈值时提出问题。
引用字段使用buy、sell、target_pct、timeframe，止损存在时另给stop_loss_pct；buy/sell引用必须证明整棵条件树。
保留原话，不把阈值上限当固定仓位，不把定性强弱补成数字。正常开场与旁白不算交易条件。
支持常见原文表达如“当14日RSI小于30的时候买入”“收盘价低于5日均线时全部卖出”以及明确参数的指标比较。
明确的“收盘价向上突破二十日均线就买”“当收盘价跌破二十天均线，就清仓”分别使用CLOSE对MA(20)的cross_above和cross_below。
“股价站上均线”不能自行假定日线收盘或交叉事件；“跌破百分之五止损”未说明基准和收盘时点，须澄清。
首板前一日条件是FIRST_LIMIT_UP offset=1；次日收盘确认后第三日开盘执行，不能声称盘中打板。
'''


def parse_operand(text):
    text = normalized(text)
    number = re.fullmatch('(' + NUMBER + r')(%|元|股)?', text)
    if number:
        value = float(number[1])
        return {'value': value, '_unit': number[2]} if math.isfinite(value) else None
    offset = 0
    prefixed = False
    for prefix, value in [('前一日', 1), ('上一日', 1), ('昨日', 1), ('当日', 0), ('今日', 0)]:
        if text.startswith(prefix):
            text, offset = text[len(prefix):], value
            prefixed = True
            break
    explicit_offset = re.fullmatch(r'(.+)\[(\d+)\]', text)
    if explicit_offset:
        if prefixed: return None
        text, offset = explicit_offset[1], int(explicit_offset[2])
    if offset > 250: return None
    period = re.fullmatch(r'(\d+)日(.+)', text)
    params = {}
    if period:
        text, params = period[2], {'period': int(period[1])}
    call = re.fullmatch(r'([^()]+)\(([^()]*)\)', text)
    args = None
    if call:
        text, args = call[1], call[2].split(',')
    ma_field = None
    for field_text, field_value in [('成交量', 'volume'), ('开盘价', 'open'), ('最高价', 'high'), ('最低价', 'low'), ('收盘价', 'close')]:
        if text == field_text + '均线':
            text, ma_field = 'MA', field_value
            break
    name = ALIASES.get(text, text.upper())
    spec = next((item for item in indicator_catalog() if item['name'] == name), None)
    if spec is None: return None
    definitions = spec.get('params', {})
    parameter_names = [key for key, item in definitions.items() if item['type'] != 'string']
    if args is not None:
        names = list(definitions) if len(args) == len(definitions) else parameter_names
        if params or len(args) != len(names): return None
        for key, value in zip(names, args):
            if definitions[key]['type'] == 'string': params[key] = value
            elif re.fullmatch(NUMBER, value): params[key] = float(value) if '.' in value else int(value)
            else: return None
    # Engine defaults describe execution, not evidence that the speaker selected them.
    if set(params) - set(definitions) or not set(parameter_names) <= set(params): return None
    for key, item in definitions.items():
        if item['type'] == 'string': params.setdefault(key, item['default'])
    if ma_field: params['field'] = ma_field
    from app.trading.indicators import normalize_params
    try: params = normalize_params(name, params)
    except (ValueError, TypeError): return None
    return {'indicator': name, 'params': params, 'offset': offset}


def parse_condition(text, nesting=0):
    if nesting > 8: return None
    text = _PAUSED_CONNECTOR.sub('', normalized(text))
    # Explicit grouping is accepted, but never strip a partial pair of brackets.
    if text.startswith('(') and text.endswith(')'):
        depth = 0
        for i, char in enumerate(text):
            depth += (char == '(') - (char == ')')
            if depth == 0 and i < len(text) - 1: break
        else: return parse_condition(text[1:-1], nesting+1)
    for words, op in [(('或者', '或'), 'or'), (('并且', '而且', '且', '同时'), 'and')]:
        depth, positions, i = 0, [], 0
        while i < len(text):
            depth += (text[i] == '(') - (text[i] == ')')
            word = next((w for w in words if depth == 0 and text.startswith(w, i)), None)
            if word: positions.append((i, len(word))); i += len(word)
            else: i += 1
        if positions:
            parts, start = [], 0
            for i, size in positions: parts.append(text[start:i]); start = i + size
            parts.append(text[start:])
            children = [parse_condition(part, nesting+1) for part in parts]
            return {'op': op, 'conditions': children} if all(children) else None
    for token in sorted(OPERATORS, key=len, reverse=True):
        if token in text:
            parts = text.split(token)
            if len(parts) != 2: return None
            left, right = map(parse_operand, parts)
            if not left or not right: return None
            for constant, other in ((left, right), (right, left)):
                unit = constant.pop('_unit', None)
                if not unit: continue
                indicator = other.get('indicator')
                price = indicator in {'OPEN', 'HIGH', 'LOW', 'CLOSE', 'PREV_CLOSE', 'LIMIT_UP', 'LIMIT_DOWN', 'ATR', 'BOLL_MID', 'BOLL_UPPER', 'BOLL_LOWER'}
                price |= indicator in {'MA', 'EMA'} and other.get('params', {}).get('field') != 'volume'
                volume = indicator == 'VOLUME' or (indicator in {'MA', 'EMA'} and other.get('params', {}).get('field') == 'volume')
                percentage = indicator in {'CHANGE_PCT', 'GAP_PCT', 'AMPLITUDE_PCT', 'RSI', 'WR'}
                if not ((unit == '元' and price) or (unit == '股' and volume) or (unit == '%' and percentage)): return None
            return {'op': OPERATORS[token], 'left': left, 'right': right}
    operand = parse_operand(text)
    if operand and operand.get('indicator') in ('FIRST_LIMIT_UP', 'IS_LIMIT_UP', 'IS_LIMIT_DOWN'):
        return {'op': 'eq', 'left': operand, 'right': {'value': 1}}
    return None


def canonical_condition(value):
    """Account only for harmless omitted defaults and AND/OR ordering."""
    if 'conditions' in value:
        children = []
        for child in value['conditions']:
            normalized_child = canonical_condition(child)
            if normalized_child[0] == value['op']: children.extend(normalized_child[1])
            else: children.append(normalized_child)
        return value['op'], tuple(sorted(children, key=repr))
    def operand(item):
        if 'value' in item: return ('value', float(item['value']))
        from app.trading.indicators import normalize_params
        return ('indicator', item['indicator'], tuple(sorted(normalize_params(item['indicator'], item.get('params', {})).items())), item.get('offset', 0))
    return value['op'], operand(value['left']), operand(value['right'])


def parse_daily_rule_clause(clause):
    clause = normalize_rule_numbers(normalized(clause))
    position = re.fullmatch(r'(?:目标)?仓位(?:为|是|设为)?(' + NUMBER + r')%', clause)
    if position:
        return 'target_pct', float(position[1])
    stop = re.fullmatch(rf'{STOP_BASIS}(?:的|,)?(?:日线)?收盘(?:下跌|亏损)({NUMBER})%(?:时|就)?(?:全部)?(?:止损|清仓)', clause)
    if stop:
        return 'stop_loss_pct', float(stop[1])
    match = re.fullmatch(rf'(?:如果|当(?!日))?(.+?),?(?:的时候|时|则|就)?({BUY_ACTION}|{SELL_ACTION})', clause)
    if match:
        expression = parse_condition(match[1])
        if expression:
            return ('buy' if match[2] in ('买入', '买') else 'sell'), expression
    return None


def conditional_coverage(text, rules, narration):
    covered = set()
    for clause in split_daily_clauses(text):
        if narration(normalize_rule_numbers(normalized(clause))):
            continue
        parsed = parse_daily_rule_clause(clause)
        if not parsed:
            return set(), False
        field, value = parsed
        if field in ('buy', 'sell'):
            if canonical_condition(value) != canonical_condition(rules[field]):
                return set(), False
        elif value != rules.get(field):
            return set(), False
        covered.add(field)
    return covered, bool(covered)


def unsupported_questions(text):
    questions = []
    if re.search(r'盘中|盤中|分时|分時|風時|分鐘|分钟|竞价|競價|進價|進駕|盘口|盤口|堂口|炸板|乍榜|回封|回風', text):
        questions.append('原文包含盘中、分时、竞价或炸板回封条件；现有日线数据不能表达，需明确独立的日线确认版，不能省略原条件。')
    if re.search(r'板块|板塊|题材|題材|流通盘|流通盤|市盈率|市净率|换手|換手|筹码|籌碼', text):
        questions.append('原文包含题材、板块或基本面/换手筛选，请明确数据来源和数值定义；当前指标不能自动代替这些条件。')
    if re.search(r'仓位|倉位|资金|資金', text) and re.search(r'减半|減半|分成|分餐|不要超|不超过|不超過|加仓|加倉|加長', text):
        questions.append('原文包含动态分仓、部分减仓或仓位上限；请明确固定目标仓位，不能把上限自动当成目标。')
    return questions
