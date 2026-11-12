"""Application factory for the isolated localhost daily walkthrough."""
from pathlib import Path
import re
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import ROOT, Settings
from app.demo_model import DEMO_MODEL, DEMO_TEXT, DEMO_TITLE, demo_completion
from app.main import create_app
from app.trading import demo_market
from app.trading.store import TradingStore


MODEL_PATH = '/__phase11_model'
HISTORY_NAME = 'hs300-20240101-20261101'
BACKTEST_START = '2024-01-01'
BACKTEST_END = '2026-11-01'
BLOCKED_WRITES = re.compile(
    r'/api/(?:'
    r'(?:ai|asr)/config|'
    r'documents/(?:url|upload|[^/]+/(?:transcribe|retranscribe-copy))|'
    r'trading/(?:backtests|datasets|paper/sessions)(?:/.*)?'
    r')/?$'
)


def create_demo_app(data_dir: Path, port: int, *, history_data_dir: Path = ROOT / 'data'):
    token = secrets.token_urlsafe(32)
    settings = Settings(
        data_dir=data_dir, ai_provider='custom', ai_model=DEMO_MODEL, ai_api_key=token,
        ai_base_url=f'http://127.0.0.1:{port}{MODEL_PATH}', ai_timeout_seconds=10,
    )
    history_data_dir = history_data_dir.resolve()
    demo = dict(
        title=DEMO_TITLE, text=DEMO_TEXT, symbol=demo_market.SYMBOL,
        start_date=BACKTEST_START, end_date=BACKTEST_END, market_source='沪深300成分股前复权研究日线',
        replay=dict(start_date=demo_market.START_DATE, end_date=demo_market.END_DATE,
                    market_source=demo_market.SOURCE),
    )
    app = create_app(
        settings, daily_demo=demo, history_store=TradingStore(history_data_dir),
        replay_market=demo_market.ReplayMarket(history_data_dir / 'history' / HISTORY_NAME),
    )

    @app.middleware('http')
    async def restrict_demo(request: Request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and BLOCKED_WRITES.fullmatch(request.url.path):
            return JSONResponse({'detail': '隔离日线演示仅提供样例文本、固定模型替身和历史工作台。'}, status_code=403)
        return await call_next(request)

    @app.post(MODEL_PATH + '/chat/completions', include_in_schema=False)
    async def sample_model(request: Request):
        authorization = request.headers.get('authorization', '').encode('utf-8')
        if not secrets.compare_digest(authorization, f'Bearer {token}'.encode('ascii')):
            raise HTTPException(403, '仅演示实例可调用模型替身。')
        try:
            content = demo_completion(await request.json())
        except (ValueError, TypeError):
            raise HTTPException(422, '模型替身仅支持隔离演示的指定样例。') from None
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}

    return app
