"""Persistent independent historical sessions backed by the optional BackBroker."""
import hashlib
import json
import re
from typing import Literal
from fastapi import HTTPException
from pydantic import Field
from app.store import now
from app.trading.models import Model, RunInput
from app.trading.portfolios import ready_portfolio
from app.trading.store import identity
from app.trading.paper_engine import engine_info, replay

KIND = 'paper_external'
LIMITATIONS = [
    'Backtrader历史回放，仅本地研究模拟；不连接第三方账号、券商或实时行情',
    '仅未复权普通沪深主板日线；无公司行为，复权研究数据不能用于本模块',
    '收盘决定股数，下一根开盘由BackBroker撮合；跳空可能资金不足拒单',
    '买入100股整手、只做多；日线下一日执行，不模拟盘口、队列及成交量冲击',
    '停牌、零量、开盘触及涨跌停保守不成交；一根内未成交则撤销',
    '费用/滑点为可调研究假设；Backtrader许可证为GPL-3.0-or-later',
]


class PaperInput(RunInput):
    name: str = Field(min_length=1, max_length=120)
    mode: Literal['replay'] = 'replay'


class ActionInput(Model):
    request_id: str = Field(min_length=1, max_length=100)


def public(value):
    return {k: v for k, v in value.items() if not k.startswith('_')}


class PaperService:
    def __init__(self, store, sources):
        self.store, self.sources = store, sources

    def capabilities(self):
        return {**engine_info(), 'account_required': False, 'live_supported': False,
                'modes': ['replay'], 'limitations': LIMITATIONS}

    def recover(self):
        # Called only during app startup, never from a normal request/read.
        with self.store.transaction() as c:
            for value in self.store.list(c, KIND):
                if value['status'] != 'completed':
                    value.update(status='paused', updated_at=now(), message='服务重启，历史账本已保留；请显式单步或运行')
                    self.store.put(c, KIND, value)

    def dataset(self, c, ident, symbol, expected_hash=None):
        ds = self.store.get(c, 'dataset', ident)
        if (ds.get('price_basis') != 'raw' or ds.get('market') != 'CN_A_MAIN'
                or ds.get('dataset_type') == 'research_adjusted'
                or ('allowed_modes' in ds and 'replay' not in ds['allowed_modes'])
                or not re.fullmatch(r'(60[0135]\d{3}\.SH|00[0123]\d{3}\.SZ)', symbol)):
            raise HTTPException(400, '外部模拟仅接受未复权普通主板撮合数据；复权研究数据请使用研究回测')
        if symbol not in ds['symbols']:
            raise HTTPException(400, '数据集不含所选标的')
        digest = hashlib.sha256(json.dumps(ds['rows'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if digest != ds['hash'] or (expected_hash is not None and digest != expected_hash):
            raise HTTPException(409, '冻结数据内容已变化，拒绝改写旧账本，请重新导入并新建会话')
        rows = [r for r in ds['rows'] if r['symbol'] == symbol]
        if not rows or len(rows) > 10000:
            raise HTTPException(400, '回放需要1至10000根有效日线')
        return ds, rows

    def create(self, c, body):
        if body.start_date or body.end_date:
            raise HTTPException(400, '日期区间目前仅适用于回测；外部模拟请使用完整冻结数据')
        if not engine_info()['installed']:
            raise HTTPException(503, '请在本机安装 requirements-paper.txt 中的可选模拟引擎版本')
        p = ready_portfolio(self.store, c, self.sources, body.portfolio_id, body.portfolio_revision)
        ds, rows = self.dataset(c, body.dataset_id, body.symbol)
        ledger = replay(p, [], body.initial_cash, body.costs.model_dump())
        value = {**identity(), **body.model_dump(), **ledger, 'kind': KIND, 'status': 'paused',
                 'portfolio_snapshot': p, 'dataset_hash': ds['hash'],
                 'dataset_snapshot': {k: v for k, v in ds.items() if k != 'rows'},
                 'is_demo': bool(ds['is_demo'] or any(i.get('source_snapshot', {}).get('is_demo', False)
                                for i in p['items'] if i['enabled'] and i.get('source_snapshot'))),
                 'warnings': list(dict.fromkeys(LIMITATIONS + ds.get('warnings', []))),
                 'consumed_bars': 0, 'total_bars': len(rows), 'cursor': None, '_requests': {},
                 'updated_at': now(), 'message': '已冻结策略与数据；等待单步或运行历史回放'}
        return self.store.put(c, KIND, value)

    def action(self, c, ident, action, body=None):
        value = self.store.get(c, KIND, ident)
        if action == 'pause':
            if value['status'] != 'completed':
                value.update(status='paused', message='已暂停，历史账本保留', updated_at=now())
            return self.store.put(c, KIND, value)
        if action not in ('step', 'run') or body is None:
            raise HTTPException(400, '无效的历史回放操作')
        previous = value['_requests'].get(body.request_id)
        if previous is not None:
            if previous != action:
                raise HTTPException(409, '同一request_id不可用于不同操作')
            return value
        if value['status'] == 'completed':
            return value
        ready_portfolio(self.store, c, self.sources, value['portfolio_id'], value['portfolio_revision'])
        if value['engine']['version'] != engine_info()['version']:
            raise HTTPException(409, '引擎版本已变化，请恢复固定版本或新建会话')
        ds, rows = self.dataset(c, value['dataset_id'], value['symbol'], value['dataset_hash'])
        count = min(len(rows), value['consumed_bars'] + 1) if action == 'step' else len(rows)
        ledger = replay(value['portfolio_snapshot'], rows[:count], value['initial_cash'], value['costs'])
        value.update(ledger)
        value.update(consumed_bars=count, cursor=rows[count-1]['date'], updated_at=now(),
                     status='completed' if count == len(rows) else 'paused',
                     message='历史回放到达末尾；末根待成交订单不补虚构行情' if count == len(rows) else '历史回放已推进一根')
        value['_requests'][body.request_id] = action
        return self.store.put(c, KIND, value)
