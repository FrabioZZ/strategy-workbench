"""Clock and unadjusted daily history for the isolated HS300 paper replay."""

from datetime import date, datetime, time, timedelta
from functools import cached_property, lru_cache
import json
from pathlib import Path

from app.trading.datasets import CN_TZ
from app.trading.history import digest, read_prices, tx_code

SYMBOL = '600000.SH'
START_DATE = '2024-01-01'
END_DATE = '2026-01-01'
SOURCE = '腾讯沪深300成分股未复权历史日线'
LIMITATIONS = [
    '只在模拟交易日收盘后公布完整日线。信号以收盘价计算，下一根日线公开时按该日开盘价估算调仓。',
    '使用未复权价格和虚拟份额，未模拟官方涨跌停、盘口、整手或公司行为现金流。',
    '股票范围取自已有历史包的沪深300成分股快照。缺失日线不填补，跨缺口不执行旧信号。',
]


def simulated_time(wall_time):
    local = wall_time.astimezone(CN_TZ)
    year = local.year - 2
    if local.month == 2 and local.day == 29:
        # Hold at the end of Feb 28 rather than moving the replay clock backwards.
        return datetime.combine(date(year, 2, 28), time.max, CN_TZ)
    return local.replace(year=year)


def completed_through(simulated_at):
    day = simulated_at.date()
    if simulated_at.time() < time(15):
        day -= timedelta(days=1)
    return day.isoformat()


class ReplayMarket:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()

    @cached_property
    def manifest(self):
        manifest = json.loads((self.folder / 'manifest.json').read_bytes())
        if manifest['schema_version'] != 1:
            raise ValueError('不支持的沪深300历史包版本')
        if not manifest['requested_start_date'] <= START_DATE <= END_DATE < manifest['requested_end_date_exclusive']:
            raise ValueError('已有沪深300历史包未覆盖模拟盘所需日期')
        return manifest

    def read_segments(self, files, code, start, end):
        merged = {}
        for name in files:
            path = (self.folder / name).resolve()
            if not path.is_relative_to(self.folder):
                raise ValueError('沪深300历史文件路径越界')
            raw = path.read_bytes()
            if digest(raw) != self.manifest['files'][name]['sha256']:
                raise ValueError(f'沪深300历史文件校验失败：{name}')
            for day, row in read_prices(json.loads(raw), code, adjusted=False).items():
                if not start <= day < end:
                    continue
                if day in merged and row != merged[day]:
                    raise ValueError('沪深300历史文件的重叠行情不一致')
                merged[day] = row
        return merged

    @cached_property
    def calendar_index(self):
        calendar = self.read_segments(self.manifest['calendar_files'], 'sh000300',
                                      self.manifest['requested_start_date'],
                                      self.manifest['requested_end_date_exclusive'])
        if not calendar:
            raise ValueError('沪深300历史包缺少模拟盘交易日历')
        return {day: index for index, day in enumerate(sorted(calendar))}

    def trading_days(self, start, end):
        try:
            if not self.manifest['requested_start_date'] <= start <= end <= self.manifest['requested_end_date_exclusive']:
                raise ValueError('日期超出已有沪深300历史包范围')
            return [day for day in self.calendar_index if start <= day <= end]
        except (OSError, KeyError, TypeError, IndexError):
            raise ValueError('已有沪深300历史包缺少文件或格式无效') from None

    @lru_cache(maxsize=32)
    def _history(self, symbol):
        security = next((item for item in self.manifest['securities'] if item['symbol'] == symbol), None)
        if security is None:
            raise ValueError(f'已有沪深300历史包没有 {symbol} 的未复权日线')
        after_end = (date.fromisoformat(END_DATE) + timedelta(days=1)).isoformat()
        rows = self.read_segments(security['raw_files'], tx_code(symbol), START_DATE, after_end)
        if not rows or rows.keys() - self.calendar_index.keys():
            raise ValueError(f'{symbol} 缺少可验证的沪深300未复权日线')
        result = []
        previous_index = None
        for day, row in sorted(rows.items()):
            index = self.calendar_index[day]
            gap = previous_index is not None and index != previous_index + 1
            result.append(dict(row, symbol=symbol, volume=row['volume'] * 100, gap_before=gap))
            previous_index = index
        return result

    def visible_history(self, symbol, through):
        try:
            return [row for row in self._history(symbol) if row['date'] <= through]
        except (OSError, KeyError, TypeError, IndexError):
            raise ValueError('已有沪深300历史包缺少文件或格式无效') from None
