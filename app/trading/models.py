from typing import Literal, Annotated
from decimal import Decimal
from pydantic import Field, model_validator, field_validator, ConfigDict
from app.models import StrictModel
from app.trading.conditions import Condition, validate_tree
from datetime import date
import re

MAIN_BOARD_SYMBOL_PATTERN = r'^(?:60[0135]\d{3}\.SH|00[0123]\d{3}\.SZ)$'

class Model(StrictModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)

class BaseRule(Model):
    target_pct: float = Field(gt=0, le=100)
    stop_loss_pct: float | None = Field(default=None, gt=0, lt=100)

class Threshold(BaseRule):
    type: Literal['threshold']
    buy_below: float = Field(gt=0)
    sell_above: float = Field(gt=0)
    @model_validator(mode='after')
    def ordered(self):
        if self.sell_above <= self.buy_below:
            raise ValueError('卖出线必须高于买入线')
        return self

class MovingAverage(BaseRule):
    type: Literal['ma']
    fast: int = Field(ge=1, le=250)
    slow: int = Field(ge=2, le=250)
    @model_validator(mode='after')
    def ordered(self):
        if self.fast >= self.slow:
            raise ValueError('慢均线周期必须大于快均线')
        return self

class Conditional(BaseRule):
    type: Literal['conditional']
    buy: Condition
    sell: Condition

    @model_validator(mode='after')
    def bounded_conditions(self):
        validate_tree(self.buy)
        validate_tree(self.sell)
        return self

class Item(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    source_id: str | None = None
    enabled: bool = True
    timeframe: Literal['daily', '5m'] = 'daily'
    weight: float = Field(default=0, ge=0, le=100)
    confirmed: bool = False
    mapping_note: str = Field(default='', max_length=4000)
    mapping_version: str | None = Field(default=None, min_length=1, max_length=80)
    rules: Annotated[Threshold | MovingAverage | Conditional, Field(discriminator='type')] | None = None

class PortfolioInput(Model):
    name: str = Field(min_length=1, max_length=120)
    mode: Literal['equal','weighted'] = 'equal'
    conflict_policy: Literal['block','weighted'] = 'block'
    items: list[Item] = Field(default_factory=list, max_length=20)
    revision: int | None = Field(default=None, ge=1)
    @model_validator(mode='after')
    def unique(self):
        if len({i.id for i in self.items}) != len(self.items):
            raise ValueError('组合项编号重复')
        return self

class DatasetInput(Model):
    name: str = Field(min_length=1,max_length=120)
    source: str = Field(min_length=1,max_length=500)
    csv_text: str = Field(min_length=1,max_length=1500000)
    market: Literal['CN_A_MAIN'] = 'CN_A_MAIN'
    price_basis: Literal['raw'] = 'raw'
    is_demo: bool = False
    ordinary_stock_confirmed: bool = False
    corporate_actions_confirmed_absent: bool = False

class Costs(Model):
    commission_bps: float = Field(default=3,ge=0,le=100)
    min_commission: float = Field(default=5,ge=0,le=1000)
    sell_tax_bps: float = Field(default=5,ge=0,le=100)
    slippage_bps: float = Field(default=0,ge=0,le=100)

class RunInput(Model):
    portfolio_id: str
    portfolio_revision: int = Field(ge=1)
    dataset_id: str
    symbol: str = Field(pattern=r'^(6\d{5}\.SH|[03]\d{5}\.SZ)$')
    initial_cash: float = Field(ge=0.01,le=1e9)
    costs: Costs = Field(default_factory=Costs)
    start_date: str | None = None
    end_date: str | None = None

    @field_validator('start_date','end_date',mode='before')
    @classmethod
    def calendar_date(cls,value):
        if value is None: return None
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
            raise ValueError('日期必须为YYYY-MM-DD')
        date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.start_date and self.end_date and self.start_date>self.end_date:
            raise ValueError('起始日期不能晚于结束日期')
        return self
    @field_validator('initial_cash')
    @classmethod
    def cash_precision(cls,value):
        if Decimal(str(value)) != Decimal(str(value)).quantize(Decimal('.01')):
            raise ValueError('初始资金最多两位小数')
        return value

class SessionInput(RunInput):
    symbol: str = Field(pattern=MAIN_BOARD_SYMBOL_PATTERN)
    dataset_id: str | None = None
    name: str = Field(min_length=1,max_length=120)
    mode: Literal['replay','incremental']
    feed: Literal['csv','tushare'] = 'csv'
    max_age_days: int = Field(default=4,ge=1,le=10)
    @model_validator(mode='after')
    def replay_dataset(self):
        if self.mode == 'replay' and not self.dataset_id:
            raise ValueError('历史回放必须选择数据集')
        if self.mode == 'replay' and self.feed != 'csv':
            raise ValueError('历史回放只使用已导入数据')
        return self

def portfolio_timeframe(portfolio):
    frames = {item.get('timeframe', 'daily') for item in portfolio['items'] if item['enabled']}
    if len(frames) != 1:
        raise ValueError('同一组合的启用策略须使用相同周期')
    return frames.pop()


class Revision(Model):
    revision: int = Field(ge=1)

class SyncInput(Model):
    request_id: str = Field(min_length=1,max_length=100)
    dataset_id: str | None = None
