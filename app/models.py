from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Segment(StrictModel):
    id: str = Field(pattern=r"^s[1-9][0-9]*$", max_length=16)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    text: str = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def valid_time(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("起止时间必须同时填写或留空")
        if self.start is not None and self.end < self.start:
            raise ValueError("结束时间不能早于开始时间")
        if not self.text.strip():
            raise ValueError("段落不能为空")
        return self


class Evidence(StrictModel):
    segment_id: str = Field(min_length=1, max_length=16)
    quote: str = Field(min_length=1, max_length=10000)


class SourcedValue(StrictModel):
    value: str = Field(min_length=1, max_length=300)
    evidence: list[Evidence] = Field(min_length=1, max_length=10)


class Rule(StrictModel):
    kind: Literal["buy", "sell", "position", "stop_loss", "filter", "other"]
    text: str = Field(min_length=1, max_length=2000)
    evidence: list[Evidence] = Field(min_length=1, max_length=10)


class StrategyInput(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    asset: SourcedValue | None
    timeframe: SourcedValue | None
    rules: list[Rule] = Field(max_length=80)
    questions: list[str] = Field(max_length=40)


class TextImport(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=120000)
    is_demo: bool = False

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip():
            raise ValueError("标题不能为空")
        return value.strip()


class UrlImport(StrictModel):
    title: str = Field(default="视频资料", min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=10000)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip():
            raise ValueError("标题不能为空")
        return value.strip()


class TranscriptUpdate(StrictModel):
    revision: int = Field(ge=1)
    segments: list[Segment] = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def unique_and_bounded(self):
        if len({s.id for s in self.segments}) != len(self.segments):
            raise ValueError("段落编号重复")
        if sum(len(s.text) for s in self.segments) > 120000:
            raise ValueError("转写最多120000字")
        return self
