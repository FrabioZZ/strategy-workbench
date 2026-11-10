"""Offline fixtures: verify provenance, actual coverage, and idempotent dataset-only import."""
import hashlib
import json
import pytest
from app.trading import datasets
from app.trading.store import TradingStore


def bundle(folder):
    folder.mkdir(parents=True,exist_ok=True)
    files={}
    def write(name,value):
        raw=json.dumps(value).encode(); (folder/name).write_bytes(raw)
        files[name]=dict(sha256=hashlib.sha256(raw).hexdigest(),fetched_at='2026-11-10T00:00:00+00:00',
                         url='https://example.test/public',params={})
        return name
    members=[dict(symbol='300750.SZ',name='测试创业板')]
    write('members.json',members)
    rows=[['2024-01-02','10','10','10','10','1000'],['2024-01-04','11','11','11','11','1000']]
    write('raw.json',{'code':0,'data':{'sz300750':{'day':rows}}})
    write('adjusted.json',{'code':0,'data':{'sz300750':{'qfqday':rows}}})
    calendar=rows[:1]+[['2024-01-03','10','10','10','10','1000']]+rows[1:]+[['2024-01-05','10','10','10','10','1000']]
    write('calendar.json',{'code':0,'data':{'sh000300':{'day':calendar}}})
    manifest=dict(schema_version=1,provider='Tencent public daily / CSI universe',
        fetched_at='2026-11-10T00:00:00+00:00',requested_start_date='2024-01-01',requested_end_date_exclusive='2024-01-06',
        universe=dict(name='沪深300',as_of_date='2026-11-09',source='公开成分股快照',survivorship_bias=True),
        universe_file='members.json',calendar_files=['calendar.json'],files=files,
        securities=[dict(**members[0],raw_files=['raw.json'],adjusted_files=['adjusted.json'])],failures=[])
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return manifest


def test_import_reports_real_tail_and_interior_gap_without_filling(tmp_path):
    from app.trading.history import load_bundle
    bundle(tmp_path)
    value,report=load_bundle(tmp_path)
    assert value['end_date']=='2024-01-04'
    assert value['expected_end_date']=='2024-01-05'
    assert value['coverage']['missing_tail_symbols']==['300750.SZ']
    assert value['coverage']['status']=='partial'
    assert [r['date'] for r in value['rows']]==['2024-01-02','2024-01-04']
    assert value['rows'][1]['gap_before'] is True
    assert report['securities'][0]['missing_dates']==['2024-01-03','2024-01-05']
    assert value['symbol_metadata'][0]['name']=='测试创业板'
    assert 'rows' not in datasets.summary(value)


def test_manifest_tampering_rejected_before_any_import(tmp_path):
    from app.trading.history import load_bundle
    bundle(tmp_path)
    (tmp_path/'raw.json').write_text('{}')
    with pytest.raises(ValueError,match='hash'): load_bundle(tmp_path)


def test_import_is_idempotent_and_preserves_strategy_and_paper_state(tmp_path):
    from app.trading.history import import_bundle
    source=tmp_path/'source'; bundle(source)
    target=tmp_path/'store'; store=TradingStore(target); store.init()
    with store.transaction() as c:
        store.put(c,'portfolio',{'id':'user-strategy','revision':8})
        store.put(c,'paper',{'id':'running-paper','status':'running','cash':123,'fills':[{'id':'existing'}]})
    first=import_bundle(source,target); second=import_bundle(source,target)
    assert first['id']==second['id']
    with store.transaction() as c:
        assert len(store.list(c,'dataset'))==1
        assert store.get(c,'portfolio','user-strategy')=={'id':'user-strategy','revision':8}
        assert store.get(c,'paper','running-paper')=={'id':'running-paper','status':'running','cash':123,'fills':[{'id':'existing'}]}


def test_adjusted_overlap_mismatch_is_not_silently_combined(tmp_path):
    from app.trading.history import load_bundle
    manifest=bundle(tmp_path)
    raw=json.dumps({'code':0,'data':{'sz300750':{'qfqday':[['2024-01-04','12','12','12','12','1000']]}}}).encode()
    (tmp_path/'other.json').write_bytes(raw)
    manifest['files']['other.json']={**manifest['files']['adjusted.json'],'sha256':hashlib.sha256(raw).hexdigest()}
    manifest['securities'][0]['adjusted_files'].append('other.json')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='没有有效'): load_bundle(tmp_path)


def test_official_universe_preserves_source_date_and_rejects_duplicates():
    from scripts.fetch_hs300_history import normalize_csi_rows
    rows=[['20261109','000300','沪深300','CSI 300',f'{600000+i}',f'名称{i}','Name','上海证券交易所','Shanghai Stock Exchange'] for i in range(300)]
    members,as_of=normalize_csi_rows(rows)
    assert as_of=='2026-11-09'
    assert members[0]=={'symbol':'600000.SH','name':'名称0'}
    rows[-1]=rows[0]
    with pytest.raises(ValueError,match='300'): normalize_csi_rows(rows)
