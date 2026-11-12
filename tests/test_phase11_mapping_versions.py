from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException

from app.ai.mapping import map_strategy
from app.store import Store
from app.trading.datasets import build_dataset, demo_input
from app.trading.models import PortfolioInput, RunInput
from app.trading.paper_service import PaperInput, PaperService, engine_info
from app.trading.portfolios import decorate, save_portfolio
from app.trading.service import TradingService
from app.trading.store import TradingStore
from app.trading.workstation import Workstation, WorkstationInput
from test_ai_conditional_mapping import conditional_fixture


def stored_mapping(store):
    source, _ = conditional_fixture(buy='收盘价站上5日均线时买入')
    document = store.create_document('映射版本', 'text', segments=source['transcript'])
    store.save_strategy(document, source['strategy'], 'fixture', 'fixture')
    source_id = store.document(document['id'])['strategy_id']
    question, = map_strategy(None, source)['clarifications']
    result = map_strategy(None, source, [{'question_id': question['id'], 'option_id': 'above'}])
    assert result['ready'], result
    mapping = {**result, 'source_id': source_id, 'source_revision': document['revision'],
               'timeframe': 'daily', 'mapping_version': 'first', 'resolution_method': 'ai'}
    mapping['decisions'][0].update(basis='assumption', reason='用持续状态定义站上')
    store.current_ai_mapping(source_id, mapping)
    return document, mapping


def test_only_one_concurrent_replacement_can_use_the_observed_version(tmp_path):
    store = Store(tmp_path)
    store.init()
    _, mapping = stored_mapping(store)
    source_id = mapping['source_id']
    start = Barrier(2)

    def replace(version):
        start.wait(timeout=5)
        candidate = {**mapping, 'mapping_version': version}
        try:
            return store.current_ai_mapping(source_id, candidate, expected_version='first')
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = pool.map(replace, ('second', 'third'))
    winners = [result for result in (left, right) if result is not None]
    winner, = winners
    assert winner['mapping_version'] in ('second', 'third')
    assert store.current_ai_mapping(source_id) == winner
    assert store.current_ai_mapping(source_id, mapping) == winner


@pytest.mark.parametrize('change', ['document_edit', 'new_draft'])
def test_source_changes_prevent_reading_or_replacing_a_mapping(tmp_path, change):
    store = Store(tmp_path)
    store.init()
    document, mapping = stored_mapping(store)
    source_id = mapping['source_id']
    if change == 'document_edit':
        store.edit(document['id'], document['revision'], document['segments'])
    else:
        store.save_strategy(document, store.document(document['id'])['strategy'], 'fixture', 'new fixture')

    with pytest.raises(ValueError):
        store.current_ai_mapping(source_id)
    with pytest.raises(ValueError):
        store.current_ai_mapping(source_id, {**mapping, 'mapping_version': 'second'}, expected_version='first')


def test_portfolio_must_confirm_current_mapping_and_frozen_run_keeps_original(tmp_path):
    sources = Store(tmp_path)
    sources.init()
    trading = TradingStore(tmp_path)
    trading.init()
    service = TradingService(trading, sources)
    _, mapping = stored_mapping(sources)
    item = {'id': 'item', 'name': '版本化策略', 'source_id': mapping['source_id'],
            'rules': mapping['rules'], 'mapping_note': mapping['mapping_note'], 'confirmed': True}

    def save(item, previous=None):
        body = PortfolioInput(name='版本化组合', items=[item],
                              revision=previous['revision'] if previous else None)
        with trading.transaction() as connection:
            return save_portfolio(trading, connection, sources, body, previous['id'] if previous else None)

    missing = save(item)
    assert not missing['readiness']['ready']
    assert missing['items'][0]['source_snapshot']['ai_mapping'] is None
    item['mapping_version'] = 'first'
    unconfirmed = save({**item, 'confirmed': False})
    assert not unconfirmed['readiness']['ready']
    mismatched = save({**item, 'timeframe': '5m'})
    assert not mismatched['readiness']['ready']
    assert mismatched['items'][0]['source_snapshot']['ai_mapping'] is None
    saved = save(item)
    assert saved['readiness']['ready'], saved
    assert saved['items'][0]['source_snapshot']['ai_mapping'] == mapping

    dataset = build_dataset(demo_input())
    run_body = RunInput(portfolio_id=saved['id'], portfolio_revision=saved['revision'],
                        dataset_id=dataset['id'], symbol='600000.SH', initial_cash=10000)
    with trading.transaction() as connection:
        trading.put(connection, 'dataset', dataset)
        run = service.create(connection, run_body)

    replacement = {**mapping, 'mapping_version': 'second', 'resolution_method': 'manual',
                   'decisions': [{**mapping['decisions'][0], 'basis': 'manual', 'reason': '按人工口径'}]}
    sources.current_ai_mapping(mapping['source_id'], replacement, expected_version='first')
    with trading.transaction() as connection:
        old = decorate(trading.get(connection, 'portfolio', saved['id']), sources)
        assert not old['readiness']['ready']
        assert old['items'][0]['source_snapshot']['ai_mapping'] == mapping
        with pytest.raises(HTTPException) as rejected:
            service.create(connection, run_body)
        assert rejected.value.status_code == 409

    stale_save = save(item, saved)
    assert not stale_save['readiness']['ready']
    assert stale_save['items'][0]['source_snapshot']['ai_mapping'] == mapping
    item['mapping_version'] = 'second'
    resaved = save(item, stale_save)
    assert resaved['readiness']['ready'], resaved
    assert resaved['items'][0]['source_snapshot']['ai_mapping'] == replacement

    with trading.transaction() as connection:
        frozen = trading.get(connection, 'backtest', run['id'])
    assert frozen['portfolio_snapshot']['items'][0]['source_snapshot']['ai_mapping'] == mapping


@pytest.mark.parametrize('entry', ['daily', 'workstation', 'external'])
def test_run_rejects_symbol_outside_versioned_source_market(tmp_path, entry):
    if entry == 'external' and not engine_info()['installed']:
        pytest.skip('optional Backtrader engine unavailable')
    sources = Store(tmp_path)
    sources.init()
    trading = TradingStore(tmp_path)
    trading.init()
    _, mapping = stored_mapping(sources)  # The source specifies 沪市主板股票.
    item = {'id': 'item', 'name': '沪市策略', 'source_id': mapping['source_id'], 'confirmed': True,
            'rules': mapping['rules'], 'mapping_note': mapping['mapping_note'], 'mapping_version': 'first'}
    dataset = build_dataset(demo_input())
    with trading.transaction() as connection:
        saved = save_portfolio(trading, connection, sources, PortfolioInput(name='沪市策略', items=[item]))
        trading.put(connection, 'dataset', dataset)
    assert saved['readiness']['ready'], saved
    inputs = {'portfolio_id': saved['id'], 'portfolio_revision': saved['revision'],
              'symbol': '000001.SZ', 'initial_cash': 10000}

    with pytest.raises(HTTPException) as rejected:
        if entry == 'workstation':
            Workstation(trading, sources).setup(WorkstationInput(**inputs, start_date='2026-01-05'))
        else:
            with trading.transaction() as connection:
                if entry == 'daily':
                    TradingService(trading, sources).create(connection, RunInput(**inputs, dataset_id=dataset['id']))
                else:
                    PaperService(trading, sources).create(connection, PaperInput(**inputs, dataset_id=dataset['id'],
                                                                               name='不匹配的历史回放'))
    assert rejected.value.status_code == 400
    assert '沪市主板股票' in rejected.value.detail and '000001.SZ' in rejected.value.detail
