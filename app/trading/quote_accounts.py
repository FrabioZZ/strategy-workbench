"""Read snapshots with SQLite mode=ro, close connections, then request quotes."""
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
import json
import sqlite3
import threading

from app.trading.quotes import CN, REFRESH_SECONDS, SYMBOL


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def value_account(account, quotes, now):
    base = dict(id=account['id'], name=account['name'], eligible=account['mode'] == 'incremental',
                mode=account['mode'], execution_status=account['status'], cash=account['cash'],
                valued_at=now.astimezone(CN).isoformat(), ledger_cursor=account.get('cursor'),
                portfolio_revision=account['portfolio_revision'])
    if not base['eligible']:
        return base | dict(status='historical_excluded', positions=[], total_assets=None,
                           market_value=None, unrealized_pnl=None)
    positions = []
    for p in account['positions']:
        if p['quantity'] <= 0:
            continue
        q = quotes.get(p['symbol'])
        valid = bool(q and q['valid_for_valuation'])
        qty, cost = Decimal(str(p['quantity'])), Decimal(str(p['average_cost']))
        market_value = qty * Decimal(str(q['price'])) if valid else None
        positions.append(dict(symbol=p['symbol'], quantity=p['quantity'], average_cost=p['average_cost'],
            book_cost=money(qty*cost), market_value=money(market_value) if valid else None,
            unrealized_pnl=money(market_value-qty*cost) if valid else None, quote=q))
    complete = all(p['market_value'] is not None for p in positions)
    market_value = money(sum(Decimal(str(p['market_value'])) for p in positions)) if complete else None
    return base | dict(status='cash_only' if not positions else 'valued' if complete else 'incomplete',
        positions=positions, complete=complete, market_value=market_value,
        total_assets=money(Decimal(str(account['cash']))+Decimal(str(market_value))) if complete else None,
        unrealized_pnl=money(sum(Decimal(str(p['unrealized_pnl'])) for p in positions)) if complete else None)


class QuoteAccounts:
    def __init__(self, store, quotes):
        self.store, self.quotes = store, quotes

    def _connection(self):
        return sqlite3.connect(self.store.path.resolve().as_uri()+'?mode=ro', uri=True, timeout=3)

    def catalog(self):
        # Extract metadata only: the research dataset contains >200k OHLCV rows.
        with closing(self._connection()) as c:
            row = c.execute("""SELECT json_extract(body,'$.symbol_metadata'), json_extract(body,'$.universe')
                FROM resources WHERE kind='dataset' AND json_extract(body,'$.dataset_type')='research_adjusted'
                ORDER BY rowid DESC LIMIT 1""").fetchone()
        metadata, universe = (json.loads(row[0] or '[]'), json.loads(row[1] or '{}')) if row else ([], {})
        members = [dict(symbol=m['symbol'], name=m.get('name',m['symbol'])) for m in metadata if SYMBOL.fullmatch(m['symbol'])]
        return dict(members=members, universe=universe, source='已导入的沪深300股票池',
                    message='' if members else '本机尚无股票池，可直接输入沪深A股完整代码查看报价。')

    def sessions(self):
        with closing(self._connection()) as c:
            rows = c.execute("""SELECT kind, json_object('id', id, 'name', json_extract(body,'$.name'),
                'mode', json_extract(body,'$.mode'), 'status', json_extract(body,'$.status'),
                'cash', json_extract(body,'$.cash'), 'positions', json_extract(body,'$.positions'),
                'cursor', json_extract(body,'$.cursor'), 'portfolio_revision', json_extract(body,'$.portfolio_revision'))
                FROM resources WHERE kind IN ('paper','paper_external') ORDER BY rowid DESC""").fetchall()
        return [(kind, json.loads(body)) for kind, body in rows]

    def overview(self, symbols=(), watch=True):
        sessions = self.sessions()  # Connection is closed before any provider I/O.
        accounts = [s for kind, s in sessions if kind == 'paper' and s['mode'] == 'incremental']
        held = [p['symbol'] for s in accounts for p in s['positions'] if p['quantity'] > 0]
        wanted = list(dict.fromkeys([*symbols, *held]))
        response = self.quotes.get(wanted, watch=watch)
        lookup = {q['symbol']:q for q in response['quotes']}
        response['accounts'] = [value_account(s, lookup, self.quotes.clock()) for s in accounts]
        response['excluded_historical_accounts'] = len(sessions)-len(accounts)
        response['quotes'] = [lookup[s] for s in dict.fromkeys(symbols)]
        return response


class QuoteWorker:
    """Independent 45-second display refresh. No order/ledger service calls."""
    def __init__(self, accounts):
        self.accounts = accounts
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name='public-quote-refresh', daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.wait(REFRESH_SECONDS):
            try:
                self.accounts.overview(self.accounts.quotes.watch_symbols(), watch=False)
            except Exception:
                # Source errors are represented per symbol; DB temporarily busy can retry next cycle.
                import logging
                logging.getLogger(__name__).exception('Read-only quote refresh failed')

    def close(self):
        self.stop.set()
        self.thread.join(timeout=10)
