from fastapi import APIRouter, HTTPException, Query


def router(accounts):
    api = APIRouter(prefix='/api/trading/quotes', tags=['quotes'])

    @api.get('/catalog')
    def catalog():
        return accounts.catalog()

    @api.get('/overview')
    def overview(symbols: str = Query('', max_length=120)):
        selected = [s.strip().upper() for s in symbols.split(',') if s.strip()]
        if len(selected) > 10:
            raise HTTPException(400, '最多同时查看10只股票')
        try:
            return accounts.overview(selected)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    return api
