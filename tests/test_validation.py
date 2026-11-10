import json
import pytest
from app.models import Segment
from app.validation import validate_strategy, parse_transcript


def source():
    return [Segment(id="s1", start=1.0, end=5.0, text="日线突破20日均线买入。跌破20日均线卖出。")]


def draft():
    return {"title": "均线策略", "asset": None, "timeframe": {"value": "日线", "evidence": [{"segment_id": "s1", "quote": "日线"}]}, "rules": [{"kind": "buy", "text": "突破20日均线买入", "evidence": [{"segment_id": "s1", "quote": "突破20日均线买入"}]}], "questions": []}


def test_verified_quotes_derive_timestamp_and_missing_conditions():
    result = validate_strategy(json.dumps(draft()), source())
    assert result["rules"][0]["evidence"][0]["start"] == 1.0
    assert result["executable"] is False
    assert any("仓位" in q for q in result["questions"])
    assert any("止损" in q for q in result["questions"])


@pytest.mark.parametrize("mutation", ["quote", "id", "threshold", "extra", "timestamp"])
def test_reject_fabricated_evidence_and_rules(mutation):
    d = draft()
    if mutation == "quote": d["rules"][0]["evidence"][0]["quote"] = "突破30日均线买入"
    if mutation == "id": d["rules"][0]["evidence"][0]["segment_id"] = "missing"
    if mutation == "threshold": d["rules"][0]["text"] = "突破30日均线买入"
    if mutation == "extra": d["order"] = {"action": "buy"}
    if mutation == "timestamp": d["rules"][0]["evidence"][0]["start"] = 999
    with pytest.raises(ValueError): validate_strategy(json.dumps(d), source())


def test_vague_rule_is_not_filled_in():
    s = [Segment(id="s1", text="适量买入，注意止损。")]
    d = {"title": "草案", "asset": None, "timeframe": None, "rules": [{"kind": "buy", "text": "适量买入", "evidence": [{"segment_id": "s1", "quote": "适量买入"}]}], "questions": []}
    r = validate_strategy(json.dumps(d), s)
    assert r["rules"][0]["needs_clarification"]
    assert r["rules"][0]["evidence"][0]["start"] is None


def test_srt_and_plain_text_keep_real_time_only():
    assert parse_transcript("1\n00:00:02,000 --> 00:00:05,000\n日线买入\n")[0].start == 2.0
    assert parse_transcript("一句原文\n第二句")[0].start is None
    assert len(parse_transcript("WEBVTT\n\n00:01.000 --> 00:03.000\n原文")) == 1
    with pytest.raises(ValueError): parse_transcript("1\n00:00:05,000 --> 00:00:01,000\n逆序")


def test_reject_non_json_and_duplicate_keys():
    with pytest.raises(ValueError): validate_strategy('```json\n{}\n```', source())
    with pytest.raises(ValueError): validate_strategy('{"title":"a","title":"b"}', source())
