import json
import re
from fastapi import HTTPException
from app.store import now
from app.strategy_names import unique_strategy_name
from app.trading.models import MAIN_BOARD_SYMBOL_PATTERN
from app.trading.store import identity


def candidates(source_store):
    with source_store.connect() as c:
        rows=c.execute('SELECT s.*,d.title,d.is_demo,d.revision AS current_revision FROM strategies s JOIN documents d ON s.document_id=d.id ORDER BY s.created_at DESC,s.rowid DESC').fetchall()
    latest={}
    result=[]
    for r in rows:
        stale=r['document_id'] in latest or r['revision'] != r['current_revision']
        latest[r['document_id']]=True
        strategy=json.loads(r['result'])
        strategy['title']=r['display_title']
        result.append(dict(id=r['id'],document_id=r['document_id'],title=r['display_title'],
                           source_title=r['title'],revision=r['revision'],
                           stale=stale,is_demo=bool(r['is_demo']),strategy=strategy,
                           transcript=json.loads(r['transcript']),created_at=r['created_at'],
                           corrected_transcript=json.loads(r['corrected_transcript']) if r['corrected_transcript'] else None,
                           ai_review=json.loads(r['ai_review']) if r['ai_review'] else None,
                           ai_mapping=json.loads(r['ai_mapping']) if r['ai_mapping'] else None,
                           evidence_transcript_version=strategy.get('transcript_version','original')))
    return result


def _source_mapping(source):
    return (source or {}).get('ai_mapping') or {}


def _mapping_matches(item, source):
    mapping = _source_mapping(source)
    return (mapping.get('ready') is True
            and mapping.get('source_revision') == source['revision']
            and mapping.get('timeframe', 'daily') == item.get('timeframe', 'daily')
            and mapping.get('rules') == item['rules'])


def readiness(p, available):
    errors=[]; warnings=['映射由用户人工确认；无法表达的原规则不可直接执行']
    active=[i for i in p['items'] if i['enabled']]
    if not active: errors.append('至少启用一个策略')
    total=sum(i['weight'] for i in active)
    if p['mode']=='weighted' and abs(total-100)>0.000001: errors.append('启用项权重必须合计100%')
    lookup={s['id']:s for s in available}
    for item in p['items']:
        item['effective_weight']=(100/len(active) if p['mode']=='equal' else item['weight']) if item['enabled'] else 0
        if not item['enabled']: continue
        if not item['confirmed'] or not item['mapping_note'].strip(): errors.append(item['name']+'：需要明确确认完整规则映射')
        if not item['rules']: errors.append(item['name']+'：缺少可执行规则')
        if item['source_id']:
            src=lookup.get(item['source_id'])
            if not src or src['stale']: errors.append(item['name']+'：原草案已过期或不存在，请重新选择并确认')
            else:
                mapping = _source_mapping(src)
                version = mapping.get('mapping_version')
                snapshot_version = _source_mapping(item.get('source_snapshot')).get('mapping_version')
                if version != item.get('mapping_version') or version != snapshot_version:
                    errors.append(item['name']+'：请载入并确认最新的执行规则版本。')
                elif not _mapping_matches(item, src) and (version or src['strategy'].get('questions') or mapping.get('decisions')):
                    errors.append(item['name']+'：当前规则缺少与原草案一致的术语确认和映射。')
                if (mapping.get('ready') is True and mapping.get('rules') == item['rules']
                        and mapping.get('timeframe', 'daily') != item.get('timeframe', 'daily')):
                    errors.append(item['name']+'：策略周期必须与已核验规则的周期一致。')
                kinds={r.get('kind') for r in src['strategy'].get('rules',[])}
                if not kinds: errors.append(item['name']+'：草案没有可核对的原规则')
                if 'stop_loss' in kinds and (not item['rules'] or not item['rules'].get('stop_loss_pct')):
                    errors.append(item['name']+'：原文包含止损，当前映射缺少止损参数')
                # Confirmed conditional trees can encode daily indicator filters.
                # Legacy two-rule forms cannot silently discard source filters.
                supported={'buy','sell','position','stop_loss'}
                if item['rules'] and item['rules'].get('type')=='conditional':
                    supported.add('filter')
                if kinds-supported:
                    errors.append(item['name']+'：原文含过滤或其他未支持规则，不能省略后运行')
    return {'ready':not errors,'errors':errors,'warnings':warnings}


def number_item_names(items):
    occupied = {item['name'].strip().casefold() for item in items}
    seen = set()
    for item in items:
        key = item['name'].strip().casefold()
        if key in seen:
            item['name'] = unique_strategy_name(item['name'], occupied, 120)
        seen.add(key)


def decorate(p, source_store):
    number_item_names(p['items'])
    p['readiness']=readiness(p,candidates(source_store))
    return p


def save_portfolio(store, c, source_store, body, ident=None):
    old=store.get(c,'portfolio',ident) if ident else None
    if old and body.revision != old['revision']: raise HTTPException(409,'组合版本已变化，请刷新后重试')
    p=body.model_dump(exclude={'revision'})
    number_item_names(p['items'])
    available=candidates(source_store); lookup={s['id']:s for s in available}
    previous_items = {item['id']: item for item in old['items']} if old else {}
    for item in p['items']:
        snapshot = lookup.get(item['source_id'])
        version = _source_mapping(snapshot).get('mapping_version')
        selected = item.get('mapping_version')
        if selected is None:
            item.pop('mapping_version', None)
        if version and (version != selected or not _mapping_matches(item, snapshot)):
            # Keep the last confirmed provenance when saving an obsolete item.
            # Never attach the replacement mapping to a different selection.
            previous = previous_items.get(item['id'], {}).get('source_snapshot')
            if (selected and (previous or {}).get('id') == item['source_id']
                    and _source_mapping(previous).get('mapping_version') == selected
                    and _mapping_matches(item, previous)):
                snapshot = previous
            else:
                snapshot = {**snapshot, 'ai_mapping': None}
        item['source_snapshot'] = snapshot
    p.update(identity() if not old else {k:old[k] for k in ('id','created_at')})
    p.update(revision=old['revision']+1 if old else 1, updated_at=now())
    p['readiness']=readiness(p,available)
    return store.put(c,'portfolio',p)


def ready_portfolio(store,c,source_store,ident,revision):
    p=decorate(store.get(c,'portfolio',ident),source_store)
    if p['revision'] != revision: raise HTTPException(409,'组合版本已变化，请使用最新版本创建运行')
    if not p['readiness']['ready']: raise HTTPException(409,'；'.join(p['readiness']['errors']))
    return p


def check_portfolio_symbol(portfolio, symbol, *, ticker_message='{name}：原策略指定 {ticker}，当前选择 {symbol}'):
    for item in portfolio['items']:
        snapshot = item.get('source_snapshot')
        if not item['enabled'] or not snapshot:
            continue
        asset = snapshot['strategy'].get('asset')
        if not isinstance(asset, dict):
            continue
        ticker = ''.join(asset.get('value', '').split()).upper()
        name = item['name']
        if re.fullmatch(MAIN_BOARD_SYMBOL_PATTERN, ticker) and ticker != symbol:
            raise HTTPException(400, ticker_message.format(name=name, ticker=ticker, symbol=symbol))
        if not item.get('mapping_version'):
            continue
        market = re.fullmatch(r'(沪市|深市|沪深|A股)(主板)?(?:普通)?(?:股票)?', ticker)
        if not market:
            continue
        suffix = {'沪市': '.SH', '深市': '.SZ'}.get(market[1])
        if ((suffix and not symbol.endswith(suffix))
                or (market[2] and not re.fullmatch(MAIN_BOARD_SYMBOL_PATTERN, symbol))):
            raise HTTPException(400, f'{name}：原策略限定{ticker}，当前选择 {symbol}')
