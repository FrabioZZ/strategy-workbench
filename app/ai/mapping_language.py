"""Small, positive grammar for narration that supplies no trading conditions."""
import re


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
