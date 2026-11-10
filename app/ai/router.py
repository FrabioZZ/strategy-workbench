from fastapi import APIRouter, Depends, HTTPException, Request
from app.ai.configuration import ConfigInput, is_loopback
from app.ai.client import complete
from app.ai.mapping import map_strategy
from app.trading.portfolios import candidates


def require_local(request: Request):
    if not request.client or not is_loopback(request.client.host):
        raise HTTPException(403,'AI 设置及调用仅允许本机回环客户端操作。')


def router(configuration, source_store):
    api=APIRouter(prefix='/api/ai',dependencies=[Depends(require_local)])

    @api.get('/config')
    def get_config(): return configuration.public()

    @api.put('/config')
    def save_config(body: ConfigInput):
        try: return configuration.save(body)
        except ValueError as exc: raise HTTPException(400,str(exc)) from None

    @api.delete('/config')
    def delete_config(): return configuration.delete()

    @api.post('/test')
    def test():
        try:
            complete(configuration.current(),[{'role':'user','content':'Reply with OK only.'}],probe=True)
            return {'ok':True,'message':'已收到所选模型的有效回复；此测试不保证提取质量。'}
        except ValueError as exc:
            return {'ok':False,'message':str(exc)}

    @api.post('/strategies/{source_id}/mapping')
    def mapping(source_id: str):
        source=next((s for s in candidates(source_store) if s['id']==source_id),None)
        if not source: raise HTTPException(404,'策略草案不存在')
        if source['stale']: raise HTTPException(409,'策略草案已过期，请重新提取后映射。')
        try:
            config=configuration.current()
            result=map_strategy(config,source)
            if next((s['stale'] for s in candidates(source_store) if s['id']==source_id),True):
                raise HTTPException(409,'映射期间原文或草案已变化，请刷新后重试。')
            return dict(source_id=source_id,source_revision=source['revision'],provider=config.ai_provider,
                        model=config.ai_model,**result)
        except ValueError as exc: raise HTTPException(400,str(exc)) from None

    return api
