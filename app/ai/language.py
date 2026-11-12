"""Bounded Chinese ASR edits, with deterministic trading-meaning guardrails.

The model judges language/context; this gate limits what that judgement can
change automatically. It is not a semantic equivalence proof or an ASR model.
"""
import re
from difflib import SequenceMatcher


# Used only to compare protected terms. No replacement is applied unless the
# model explicitly proposes it. Ordinary edits do not have to be in this map.
_TERM_ALIASES = {'均现': '均线', '均限': '均线', '日现': '日线',
                 '仓为': '仓位', '收盘介': '收盘价'}
_PUNCTUATION = re.compile(r'[\s，。！？、；：,.!?;:]')
_PUNCTUATION_WIDTH = str.maketrans('，。！？；：', ',.!?;:')
_NUMERAL = r'[零〇一二三四五六七八九十百千万亿两壹贰叁肆伍陆柒捌玖拾佰仟萬億兩貳參陸]+'
_NUMBER = r'\d+(?:[.,]\d+)*\s*[%％‰]?|' + _NUMERAL
_NUMBERS = re.compile(_NUMBER)
_QUANTITIES = re.compile(
    r'(?:' + _NUMBER + r')\s*(?:美元|港元|人民币|人民幣|元|股|手|成|倍|天|日|周|週|月|年|分钟|分鐘|秒)')
_MA_TYPO = re.compile(r'(' + _NUMBER + r'\s*(?:日|天)\s*)军线')
_STOP_TYPO = re.compile(r'((?:百分之' + _NUMBER + r'|\d+(?:\.\d+)?[%％])\s*)只损(?!失)')

# Longest match first, so adding "等于" or changing "只有" to "只要"
# changes the signature even when some individual characters are shared.
_PROTECTED_WORDS = '''
买 买入 買 買入 卖 卖出 賣 賣出 加仓 加倉 减仓 減倉 建仓 建倉 清仓 清倉
开仓 開倉 平仓 平倉 持仓 持倉 空仓 空倉 满仓 滿倉 半仓 半倉 轻仓 輕倉 重仓 重倉
做多 做空 看多 看空 多头 多頭 空头 空頭 止盈 止损 止損 盈利 亏损 虧損
不 不要 不得 没 沒 没有 沒有 无 無 非 未 禁止 避免 勿 莫 别 別 不能 无需 無需
如果 若 假如 假设 假設 除非 否则 否則 只有 只要 即使 即便 虽然 雖然
但是 然而 并且 並且 且 或者 或 而且 同时 同時 才 就 仅 僅 必须 必須 可以 应当 應當
大于 大於 小于 小於 高于 高於 低于 低於 等于 等於 不等于 不等於
大于等于 大於等於 小于等于 小於等於 高于等于 高於等於 低于等于 低於等於
超过 超過 不超过 不超過 至少 至多 最多 最少 以上 以下 以内 以內 以外
高过 高過 低过 低過 多于 多於 少于 少於 超出 达到 達到
高 低 大 小 多 少 上方 下方 上面 下面 之上 之下
上涨 上漲 下跌 上升 下降 增加 减少 減少 扩大 擴大 缩小 縮小
上穿 下穿 突破 跌破 跌穿 站上 站稳 站穩 放量 缩量 縮量 强势 強勢 弱势 弱勢
之前 之后 之後 以前 以后 以後 前 后 後 当天 當天 今天 昨天 明天 次日 后天 後天
开盘 開盤 收盘 收盤 最高 最低 均线 均線 日线 日線 周线 周線 月线 月線
分钟 分鐘 小时 小時 仓位 倉位 股价 股價 价格 價格 收盘价 收盤價
全部 部分 一半 所有 剩余 剩餘
吗 嗎 呢 是否 能否
'''.split()
_PROTECTED = re.compile('|'.join(re.escape(word) for word in sorted(set(_PROTECTED_WORDS), key=len, reverse=True))
                        + r'|[<>≤≥=≠+\-±%％‰]|[A-Za-z][A-Za-z0-9_.-]*')


def _plain(text):
    return _PUNCTUATION.sub('', text)


def _canonical_terms(text):
    for original, corrected in _TERM_ALIASES.items():
        text = text.replace(original, corrected)
    text = _MA_TYPO.sub(r'\1均线', text)
    return _STOP_TYPO.sub(r'\1止损', text)


def _scope_text(text):
    # Width changes and a final full stop do not move a clause boundary.
    # Interior punctuation and question/exclamation marks remain significant.
    return _canonical_terms(text).translate(_PUNCTUATION_WIDTH).strip().removesuffix('.')


def correction_issue(original, corrected):
    """Return a reviewable rejection reason, or None for a bounded local edit."""
    if original == corrected:
        return None
    if _NUMBERS.findall(original) != _NUMBERS.findall(corrected):
        return '数字、比例或序号发生变化'
    if _QUANTITIES.findall(original) != _QUANTITIES.findall(corrected):
        return '数值对应的单位或周期发生变化'
    old_terms = _PROTECTED.findall(_plain(_canonical_terms(original)))
    new_terms = _PROTECTED.findall(_plain(_canonical_terms(corrected)))
    if old_terms != new_terms:
        return '交易方向、仓位、否定、比较、条件或时序词发生变化'

    old, new = _plain(original), _plain(corrected)
    # Keep diff work bounded even for a long or repetitive ASR segment.
    if max(len(original), len(corrected)) > 2000:
        return '段落过长，需要拆段校对'
    if not old or not new:
        return '校正缺少可保留的原文'
    operations = SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
    if not any(tag == 'equal' for tag, *_ in operations):
        return '校正缺少可保留的原文'
    edits = [op for op in operations if op[0] != 'equal']
    sizes = [max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in edits]
    if (len(edits) > 6 or any(size > 4 for size in sizes)
            or sum(sizes) > min(12, max(1, min(len(old), len(new)) // 4))):
        return '改动超出局部错词或语法修正范围'

    # A negation/conditional is allowed to coexist with an unrelated typo fix.
    # Moving its punctuation is not: 不要买入 -> 不，要买入 must still fail.
    if old_terms or _NUMBERS.search(original) or re.search(r'[!?！？]', original + corrected):
        before, after = _scope_text(original), _scope_text(corrected)
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if tag != 'equal' and _PUNCTUATION.search(before[i1:i2] + after[j1:j2]):
                return '断句或疑问语气变化可能改变条件或否定的作用范围'
    return None
