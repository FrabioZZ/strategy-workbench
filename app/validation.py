import json
import re
from app.models import Segment, StrategyInput

EXPLICIT_MA_BREAKOUT = re.compile(r'收盘价向上突破\s*(?:\d+|[零〇一二三四五六七八九十百两]+)\s*(?:日|天)均线')
VAGUE_RULE = re.compile(r'适量|适当|附近|放量|缩量|突破|企稳|趋势|注意|合适|明显|较大|较小')


def needs_rule_clarification(text):
    return bool(VAGUE_RULE.search(EXPLICIT_MA_BREAKOUT.sub('', text)))


def _unique_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("模型 JSON 包含重复字段")
        result[k] = v
    return result


def validate_strategy(raw: str, segments: list[Segment]) -> dict:
    if len(raw) > 200000:
        raise ValueError("模型结果过长")
    obj = json.loads(raw, object_pairs_hook=_unique_pairs,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError("无效数值")))
    draft = StrategyInput.model_validate(obj, strict=True)
    by_id = {s.id: s for s in segments}

    def evidence(items):
        result = []
        for item in items:
            segment = by_id.get(item.segment_id)
            if segment is None or item.quote not in segment.text or not item.quote.strip():
                raise ValueError("模型引用无法匹配真实转写，请重试或校对原文")
            result.append({**item.model_dump(), "start": segment.start, "end": segment.end})
        return result

    def sourced(item):
        if item is None:
            return None
        refs = evidence(item.evidence)
        if not any(item.value in e["quote"] for e in refs):
            raise ValueError("标的或周期并非原文摘录")
        return {"value": item.value, "evidence": refs}

    questions = [q[:1000] for q in draft.questions if q.strip()]
    rules = []
    for rule in draft.rules:
        refs = evidence(rule.evidence)
        # Extractive rules are deliberate: generated thresholds/paraphrases cannot pass.
        if not any(rule.text in e["quote"] for e in refs):
            raise ValueError("策略规则必须逐字摘自引用，禁止补造条件或阈值")
        vague = needs_rule_clarification(rule.text)
        if vague:
            questions.append(f"需人工明确“{rule.text[:120]}”的判定口径、阈值与适用条件。")
        rules.append({**rule.model_dump(), "evidence": refs, "needs_clarification": vague,
                      "review_status": "pending_human_review"})
    kinds = {r.kind for r in draft.rules}
    for kind, name in [("buy", "买入条件"), ("sell", "卖出条件"), ("position", "仓位"), ("stop_loss", "止损")]:
        if kind not in kinds:
            questions.append(f"原文未提取到{name}，需补充确认；不能据此执行交易。")
    if draft.asset is None:
        questions.append("标的或股票范围未明确。")
    if draft.timeframe is None:
        questions.append("观察周期或持仓周期未明确。")
    if not rules:
        questions.append("未找到可引用的交易规则，请检查资料内容。")
    return {"title": draft.title, "asset": sourced(draft.asset), "timeframe": sourced(draft.timeframe),
            "rules": rules, "questions": list(dict.fromkeys(questions)), "executable": False,
            "status": "draft", "notice": "仅为教学资料策略草案；引用一致不等于策略正确，须人工复核。"}


TIME = r"(?:(\d{1,3}):)?(\d{2}):(\d{2})[,.](\d{3})"
TIMELINE = re.compile(rf"^\s*{TIME}\s*-->\s*{TIME}(?:\s+.*)?$")


def _seconds(groups):
    h, m, s, ms = groups
    if int(m) > 59 or int(s) > 59:
        raise ValueError("字幕时间格式错误")
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_transcript(text: str) -> list[Segment]:
    text = text.lstrip("\ufeff").strip().replace("\r\n", "\n")
    if not text or len(text) > 120000:
        raise ValueError("请提供1至120000字的文本或字幕")
    segments = []
    if "-->" in text or text.startswith("WEBVTT"):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "-->" not in line:
                continue
            match = TIMELINE.match(line)
            if not match:
                raise ValueError("字幕时间格式无效，请使用 SRT 或 VTT")
            content = []
            for following in lines[i + 1:]:
                if not following.strip() or "-->" in following:
                    break
                content.append(following.strip())
            if content:
                segments.append(Segment(id=f"s{len(segments)+1}", start=_seconds(match.groups()[:4]),
                                        end=_seconds(match.groups()[4:]), text="\n".join(content)))
    else:
        for line in text.splitlines():
            if line.strip():
                segments.append(Segment(id=f"s{len(segments)+1}", text=line.strip()))
    if not segments or len(segments) > 3000:
        raise ValueError("未找到有效段落，或超过3000段限制")
    return segments
