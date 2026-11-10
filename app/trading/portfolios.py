import json
from fastapi import HTTPException
from app.store import now
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
        result.append(dict(id=r['id'],document_id=r['document_id'],title=strategy.get('title') or r['title'],
                           source_title=r['title'],revision=r['revision'],
                           stale=stale,is_demo=bool(r['is_demo']),strategy=strategy,
                           transcript=json.loads(r['transcript']),created_at=r['created_at'],
                           corrected_transcript=json.loads(r['corrected_transcript']) if r['corrected_transcript'] else None,
                           ai_review=json.loads(r['ai_review']) if r['ai_review'] else None,
                           evidence_transcript_version=strategy.get('transcript_version','original')))
    return result


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
            elif src['strategy'].get('questions'): errors.append(item['name']+'：原草案有未解决问题，不可运行')
            else:
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


def decorate(p, source_store):
    p['readiness']=readiness(p,candidates(source_store))
    return p


def save_portfolio(store, c, source_store, body, ident=None):
    old=store.get(c,'portfolio',ident) if ident else None
    if old and body.revision != old['revision']: raise HTTPException(409,'组合版本已变化，请刷新后重试')
    p=body.model_dump(exclude={'revision'})
    available=candidates(source_store); lookup={s['id']:s for s in available}
    for item in p['items']:
        item['source_snapshot']=lookup.get(item['source_id']) if item['source_id'] else None
    p.update(identity() if not old else {k:old[k] for k in ('id','created_at')})
    p.update(revision=old['revision']+1 if old else 1, updated_at=now())
    p['readiness']=readiness(p,available)
    return store.put(c,'portfolio',p)


def ready_portfolio(store,c,source_store,ident,revision):
    p=decorate(store.get(c,'portfolio',ident),source_store)
    if p['revision'] != revision: raise HTTPException(409,'组合版本已变化，请使用最新版本创建运行')
    if not p['readiness']['ready']: raise HTTPException(409,'；'.join(p['readiness']['errors']))
    return p
