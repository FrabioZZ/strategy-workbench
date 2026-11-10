from fastapi import APIRouter, HTTPException
from app.trading.paper_service import ActionInput, KIND, PaperInput, public


def router(service):
    api = APIRouter(prefix='/api/trading/external-paper', tags=['免账号外部历史模拟'])

    def get(c, ident):
        try:
            return service.store.get(c, KIND, ident)
        except KeyError:
            raise HTTPException(404, '外部模拟会话不存在') from None

    @api.get('/capabilities')
    def capabilities():
        return service.capabilities()

    @api.get('/sessions')
    def sessions():
        with service.store.transaction() as c:
            return [public(s) for s in service.store.list(c, KIND)]

    @api.get('/sessions/{ident}')
    def session(ident: str):
        with service.store.transaction() as c:
            return public(get(c, ident))

    @api.post('/sessions', status_code=201)
    def create(body: PaperInput):
        with service.store.transaction() as c:
            try:
                return public(service.create(c, body))
            except KeyError:
                raise HTTPException(404, '所选组合或数据集不存在') from None

    @api.post('/sessions/{ident}/step')
    def step(ident: str, body: ActionInput):
        with service.store.transaction() as c:
            get(c, ident)
            return public(service.action(c, ident, 'step', body))

    @api.post('/sessions/{ident}/run')
    def run(ident: str, body: ActionInput):
        with service.store.transaction() as c:
            get(c, ident)
            return public(service.action(c, ident, 'run', body))

    @api.post('/sessions/{ident}/pause')
    def pause(ident: str):
        with service.store.transaction() as c:
            get(c, ident)
            return public(service.action(c, ident, 'pause'))

    return api
