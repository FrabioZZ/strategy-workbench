"""Small, bounded live probe. Does not open or modify any trading database."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.runtime/phase4-quote-probe')
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    url = 'https://qt.gtimg.cn/q=sh600000,sz000001,sz300750'
    result = dict(url=url, method='GET', requested_at=datetime.now(timezone.utc).isoformat(),
                  timeout_seconds=8, symbols=['600000.SH', '000001.SZ', '300750.SZ'])
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'quant-local/phase4', 'Referer': 'https://gu.qq.com/'})
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError('oversize response')
            result.update(http_status=response.status, headers=dict(response.headers))
        result['received_at'] = datetime.now(timezone.utc).isoformat()
        (folder / 'response.bin').write_bytes(raw)
        decoded = raw.decode('gb18030')
        (folder / 'response.txt').write_text(decoded, encoding='utf-8')
        result.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        result['observations'] = []
        for line in decoded.strip().splitlines():
            key, value = line.split('=', 1)
            fields = value.strip('";').split('~')
            result['observations'].append(dict(key=key, name=fields[1], code=fields[2], price=fields[3],
                previous_close=fields[4], volume_lots=fields[6], source_time=fields[30], field_count=len(fields)))
    except Exception as exc:
        result.update(error=type(exc).__name__ + ': ' + str(exc), received_at=datetime.now(timezone.utc).isoformat())
    (folder / 'probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if result.get('error') else 0


if __name__ == '__main__':
    raise SystemExit(main())
