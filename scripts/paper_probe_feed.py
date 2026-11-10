"""Explicit, account-free Tencent daily-data probe. Never imports trading data.

This records reachability and actual coverage, not a verified live trading feed.
No guessed daily price limits or corporate-action absence are manufactured.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('.runtime/paper-feed-probe'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    query = {'param': 'sh600000,day,2026-01-01,2026-11-10,640,'}
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?' + urlencode(query)
    result = dict(provider='Tencent public daily endpoint', symbol='600000.SH',
        fetched_at=datetime.now(timezone.utc).isoformat(), account_used=False,
        requested_start_date='2026-01-01', requested_end_date='2026-11-10',
        request_url=url, live_verified=False, trading_eligible=False,
        reason='仅验证历史OHLCV；未取得官方每日限价及公司行为完整资料，不自动导入严格模拟盘')
    try:
        with urlopen(Request(url, headers={'User-Agent': 'quant-local-research/1.0'}), timeout=25) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('response too large')
            result['http_status'] = response.status
        data = json.loads(raw)
        rows = data.get('data', {}).get('sh600000', {}).get('day', [])
        if not rows:
            raise ValueError('raw daily data absent')
        args.output.joinpath('tencent-600000-raw.json').write_bytes(raw)
        result.update(status='historical_data_received', sha256=hashlib.sha256(raw).hexdigest(),
                      row_count=len(rows), actual_start_date=rows[0][0], actual_end_date=rows[-1][0],
                      last_daily_row=rows[-1][:6])
    except Exception as exc:
        result.update(status='unavailable', error_type=type(exc).__name__)
    args.output.joinpath('manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
