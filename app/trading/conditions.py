"""Validated expression tree shared by all daily signal consumers."""
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.trading.indicators import normalize_params, REGISTRY

OPERATORS=['gt','gte','lt','lte','eq','ne','cross_above','cross_below','and','or']


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class Constant(Strict):
    value: float = Field(strict=True)


class Indicator(Strict):
    indicator: str
    params: dict = Field(default_factory=dict)
    offset: int = Field(default=0,ge=0,le=250,strict=True)

    @model_validator(mode='after')
    def validate_indicator(self):
        self.params=normalize_params(self.indicator,self.params)
        return self


Operand = Constant | Indicator


class Comparison(Strict):
    op: Literal['gt','gte','lt','lte','eq','ne','cross_above','cross_below']
    left: Operand
    right: Operand


class Junction(Strict):
    op: Literal['and','or']
    conditions: list['Condition'] = Field(min_length=2,max_length=16)


Condition = Annotated[Union[Comparison,Junction],Field(discriminator='op')]
Junction.model_rebuild()


def validate_tree(node):
    count=0
    def visit(current,depth):
        nonlocal count
        count+=1
        if depth>8 or count>64: raise ValueError('条件树最多8层、64个节点')
        if isinstance(current,Junction):
            for child in current.conditions: visit(child,depth+1)
    visit(node,1)


def operand_value(operand, book, index):
    if 'value' in operand: return operand['value']
    return book.value(operand['indicator'],operand.get('params'),index-operand.get('offset',0))


def evaluate(node,book,index=None):
    index=len(book.rows)-1 if index is None else index
    op=node['op']
    if op in ('and','or'):
        values=[evaluate(child,book,index) for child in node['conditions']]
        if op=='and': return False if False in values else None if None in values else True
        return True if True in values else None if None in values else False
    left=operand_value(node['left'],book,index); right=operand_value(node['right'],book,index)
    if left is None or right is None: return None
    if op in ('cross_above','cross_below'):
        prior_left=operand_value(node['left'],book,index-1); prior_right=operand_value(node['right'],book,index-1)
        if prior_left is None or prior_right is None: return None
        return (prior_left<=prior_right and left>right) if op=='cross_above' else (prior_left>=prior_right and left<right)
    return {'gt':lambda:left>right,'gte':lambda:left>=right,'lt':lambda:left<right,
            'lte':lambda:left<=right,'eq':lambda:left==right,'ne':lambda:left!=right}[op]()


def indicator_names(rule):
    result=set()
    def visit(node):
        if isinstance(node,dict):
            if 'indicator' in node: result.add(node['indicator'])
            for value in node.values(): visit(value)
        elif isinstance(node,list):
            for value in node: visit(value)
    visit(rule)
    return result


def raw_only_indicators(portfolio):
    return sorted({name for item in portfolio['items'] if item['enabled']
                   for name in indicator_names(item.get('rules')) if REGISTRY[name]['raw_only']})
