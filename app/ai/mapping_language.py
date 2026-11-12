"""Recognize bounded spoken expressions while retaining the original citations."""
import re


NUMBER = r'-?\d+(?:\.\d+)?'
_DIGITS = {char: value for value, char in enumerate('零一二三四五六七八九')}
_DIGITS['两'] = 2
_CHINESE_NUMBER = r'[零一二两三四五六七八九十百]{1,5}(?:点[零一二三四五六七八九]{1,6})?'
_MA_PERIOD = re.compile(rf'({_CHINESE_NUMBER}|\d+)(?:天|日)(?=(?:简单|指数)?均线)')
_PERCENTAGE = re.compile(rf'百分之({NUMBER}|{_CHINESE_NUMBER})')
STOP_BASIS = '以入场信号收盘价为基准'


def _spoken_number(text: str) -> str:
    if re.fullmatch(NUMBER, text):
        return text
    integer, separator, fraction = text.partition('点')
    match = re.fullmatch(r'(?:(?P<hundreds>[一二两三四五六七八九])百)?'
                         r'(?:(?P<tens>[一二三四五六七八九])?十|(?P<zero>零)(?=.))?'
                         r'(?P<ones>[零一二两三四五六七八九])?', integer)
    if not match:
        return text
    hundreds, tens, zero, ones = match.groups()
    if (zero and (not hundreds or ones in (None, '零', '两'))
            or hundreds and not tens and '十' in integer
            or hundreds and ones and not zero and '十' not in integer
            or '十' in integer and ones in ('零', '两')):
        # In particular, do not interpret 一百五 as either 105 or 150.
        return text
    value = 100 * _DIGITS.get(hundreds, 0) + _DIGITS.get(ones, 0)
    if '十' in integer:
        value += 10 * _DIGITS.get(tens, 1)
    decimal = ''.join(str(_DIGITS[digit]) for digit in fraction)
    return f'{value}{separator}{decimal}'


def normalize_rule_numbers(text: str) -> str:
    """Normalize explicit MA periods and percentages for matching only."""
    text = _MA_PERIOD.sub(lambda match: _spoken_number(match[1]) + '日', text)
    return _PERCENTAGE.sub(lambda match: _spoken_number(match[1]) + '%', text)


def is_timeframe_context(clause: str, timeframe: str) -> bool:
    if not timeframe:
        return False
    return re.fullmatch(rf'(?:我|我们)?(?:在|用|按){re.escape(timeframe)}(?:周期|级别)?(?:观察|判断)', clause) is not None


_AUDIENCE = r'(?:大家|各位(?:朋友)?|朋友们|同学们)'
_EPISODE = r'(?:本期|这期|这一期)'
_TOPIC = r'(?:(?:这个|这一|该)(?:方法|策略)|(?:日线|双均线|均线|阈值)(?:方法|策略))'
_SUBJECT = r'(?:我|我们)?'
_EXPLAIN = r'(?:分享|介绍|讲解|说明)'

# Match whole clauses with bounded vocabulary, not arbitrary text after a
# harmless prefix. In particular, topics cannot hide numbers, filters, timing,
# negation or extra buy/sell qualifications. Unknown clauses still need review.
_NARRATION = tuple(re.compile(pattern) for pattern in (
    _AUDIENCE + r'好',
    r'欢迎(?:大家)?(?:来到|观看|收看)' + _EPISODE + r'(?:视频|节目|课程)',
    r'欢迎(?:大家)?回来',
    r'(?:今天|' + _EPISODE + r')?' + _SUBJECT + r'(?:来|要|想|将)?'
    + r'(?:(?:和|跟|给)' + _AUDIENCE + r')?' + _EXPLAIN + _TOPIC,
    r'(?:刚才|前面)' + _SUBJECT + _EXPLAIN + r'了' + _TOPIC,
    r'(?:下面|接下来)' + _SUBJECT + r'(?:来|继续)?' + _EXPLAIN + r'(?:' + _TOPIC + r')?',
    r'(?:下面|接下来)?' + _SUBJECT + r'(?:来看|看)(?:一个)?(?:例子|示例|图表)',
    r'(?:下面|接下来)?' + _SUBJECT + r'用(?:图表|示意图)(?:来)?(?:说明|讲解)' + _TOPIC,
    r'(?:为了)?(?:方便|帮助)(?:大家)?理解',
    r'(?:我|我们)把(?:步骤|过程|规则)写在(?:屏幕|图表)上',
    r'(?:这里的|这张)?(?:图表|示意图)(?:只是|是)(?:为了|用来)(?:方便|帮助)(?:大家)?理解',
    r'(?:均线|图表)(?:用于|用来|帮助)(?:观察|理解)(?:价格)?(?:趋势|走势)',
    r'(?:今天|' + _EPISODE + r')的(?:讲解|分享|视频)(?:就)?到这里',
    r'以上就是(?:今天|' + _EPISODE + r')的(?:讲解|分享|内容)',
    r'(?:感谢|谢谢)(?:' + _AUDIENCE + r'(?:的)?)?(?:观看|收看|支持)',
    r'(?:感谢|谢谢)' + _AUDIENCE,
    r'(?:我们)?(?:下期|下次)再见',
    r'(?:喜欢' + _EPISODE + r'视频的朋友|大家)(?:可以)?(?:点赞|收藏|点赞收藏)',
    r'欢迎(?:大家)?在评论区(?:交流|留言|讨论)',
))


def is_plain_narration(clause: str) -> bool:
    """Accept only a complete, unambiguous non-rule clause; never prove a field."""
    return any(pattern.fullmatch(clause) for pattern in _NARRATION)
