"""Synthetic account-specific ETF policy through the normal target-source seam."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import json,sqlite3,sys,zipfile
import pytest
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from approved_target_input import build_approved_target_view
from member_v82_analysis import target_source
from owner_etf_constraints_source import approval_target
from etf_structure_source import evaluate_etf_structure,LEAVES


def case(tmp_path):
    client='fam_'+'a'*32;member='SyntheticMember';symbols=['AAA','BBB','CCC','DDD']
    account={'client_id':client,'account_key':'SYNTHETIC_US','account_state':'UNKNOWN'}
    db=tmp_path/'SYNTHETIC.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE family_member_identity(client_id TEXT,family_alias TEXT)')
        c.execute('INSERT INTO family_member_identity VALUES(?,?)',(client,member))
        c.execute('CREATE TABLE portfolio_account(client_id TEXT,account_key TEXT,account_state TEXT)')
        c.executemany('INSERT INTO portfolio_account VALUES(?,?,?)',[(client,'SYNTHETIC_US','UNKNOWN'),(client,'SYNTHETIC_OTHER','UNKNOWN')])
    tables={'portfolio_account':[account],
        'portfolio_instrument':[{'client_id':client,'instrument_key':s,'ticker':s,'instrument_type':'ETF',
            'identity_state':'KNOWN','quote_currency':'USD'} for s in symbols],
        'portfolio_position':[{'client_id':client,'account_key':'SYNTHETIC_US','instrument_key':s,
            'quantity_decimal':'1','as_of_utc':'2026-11-01T00:00:00Z'} for s in symbols]}
    snapshot={'client_id':client,'source_sha256':sha256(db.read_bytes()).hexdigest(),
        'tables':tables,'payload_digest':digest(tables)}
    def desc(p):return {'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}
    document=tmp_path/'SYNTHETIC_ORIGINAL.docx'
    header='2026/11/21｜'+member+' 四檔上限裁定'
    paragraph=header+'｜指揮官原文「照原配置，沒有額外上限」。只適用 '+member+' 的 '+'、'.join(symbols)+'。維持原配置與風控。'
    with zipfile.ZipFile(document,'w') as z:
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'+paragraph+'</w:t></w:r></w:p></w:document>')
    receipt=tmp_path/'SYNTHETIC_CAPTURE.json'
    capture={'schema_version':'Family.W8.RegisteredDocumentCapture.v1','file_id':'SYNTHETIC_DOC',
        'source_sha256':desc(document)['sha256'],'revision_id':'2',
        'revision_modified_at':'2026-11-20T21:00:00Z','modified_at':'2026-11-20T21:00:00Z',
        'captured_at':'2026-11-20T22:00:00Z'}
    receipt.write_text(json.dumps(capture))
    data={'schema_version':'Family.W8.OwnerETFConstraintsSource.v1','client_id':client,
        'source_db_sha256':snapshot['source_sha256'],'member':member,'symbols':symbols,
        'account_scope':{'account_key':account['account_key'],'original_account_row':account},
        'original_document':desc(document),'document_file_id':'SYNTHETIC_DOC','source_section':header,
        'registration_receipt':desc(receipt),'authority_reference':'https://docs.google.com/document/d/SYNTHETIC_DOC/edit#explicit-owner-policy',
        'trade_authorization':'NONE'}
    config={'member_db_path':str(db)}
    def save():
        p=tmp_path/'SYNTHETIC_SOURCE.json';p.write_text(json.dumps(data));config['owner_etf_constraints_source']=desc(p)
    save()
    original={'source_kind':'SYNTHETIC_EXISTING_TARGET','target_hash':'ORIGINAL_APPROVAL_HASH','payload':{'draft':{
        'target_lines':[{'ticker':s,'weight':{'value':'0.25'}} for s in symbols],
        'etf_constraints':{'AAA':{'allowed_mandate_components':['EQUITY'],'unrelated_limit':'UNCHANGED'}}}}}
    return snapshot,config,data,save,original


def apply(snapshot,config,target,at='2026-11-21T01:00:00Z'):
    with patch('member_v82_analysis._historical_target_source',return_value=deepcopy(target)):
        return target_source(snapshot,config,at)


def mandate_case(tmp_path):
    snapshot, config, decision, _, _ = case(tmp_path)
    symbols = decision['symbols']
    lines = [f'| {symbol} named ETF | 25% | Verified purpose {symbol} |' for symbol in symbols]
    path = tmp_path / 'SYNTHETIC_TARGET.md'
    path.write_text('| 標的 | 目標權重 | 用途 |\n| --- | --- | --- |\n' + '\n'.join(lines) + '\n')
    source = 'drive:SYNTHETIC_TARGET'
    target = build_approved_target_view(client_id=snapshot['client_id'], source_path=path,
        source_reference=source, source_available_at='2026-11-01T12:00:00Z',
        target_version=3, allocation_version='SYNTHETIC-v3',
        rows=[{'source_line': line, 'weight': '0.25'} for line in lines],
        mappings=[{'ticker': s, 'instrument_id': s, 'asset_type': 'ETF'} for s in symbols])['target']
    items = {s: {'instrument_id': s, 'original_document_row': line,
        'allowed_mandate_components': ['APPROVED_EQUITIES']} for s, line in zip(symbols, lines)}
    items['AAA'].pop('allowed_mandate_components')
    items['AAA']['missing_approval_clause'] = 'Unresolved coverage of an additional strategy.'
    mandate = {'schema_version': 'Family.W8.OwnerETFMandateSource.v1',
        'client_id': snapshot['client_id'], 'source_db_sha256': snapshot['source_sha256'],
        'account_key': decision['account_scope']['account_key'], 'trade_authorization': 'NONE',
        'allocation_version': 'SYNTHETIC-v3', 'target_version': 3, 'available_at': '2026-11-20T23:54:38Z',
        'work_order_reference': 'SYNTHETIC_SCOPE_WORK_ORDER',
        'approved_document': {'local_path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest(),
                              'source_reference': source}, 'items': items}
    def save():
        path = tmp_path / 'SYNTHETIC_MANDATE.json'
        path.write_text(json.dumps(mandate))
        config['owner_etf_constraints_source']['mandate_source'] = {
            'local_path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}
    save()
    return snapshot, config, target, mandate, save


def mandate_leaf(target, snapshot, symbol, components, at='2026-11-21T01:00:00Z'):
    facts = {'symbol': symbol, 'source_sha256': 'a' * 64,
        'source_url': 'https://fund-docs.vanguard.com/synthetic.pdf',
        'mandate': {'components': components, 'method_version': 'SYNTHETIC',
            'as_of': '2026-11-19T00:00:00Z', 'available_at': '2026-11-20T00:00:00Z',
            'valid_until': '2026-11-22T00:00:00Z', 'data_quality': 'OK'}}
    return evaluate_etf_structure(facts, {'client_id':snapshot['client_id'],
        'evaluation_at':at,'confirmed_target':target}, symbol)['leaves'][LEAVES[1]]


def test_bound_owner_mandate_is_compared_without_extending_approval(tmp_path):
    snapshot, config, base, data, _ = mandate_case(tmp_path)
    projected = apply(snapshot, config, base)
    assert approval_target(projected, snapshot, '2026-11-21T01:00:00Z') == base
    assert projected['payload']['draft']['target_lines'] == base['payload']['draft']['target_lines']
    for symbol in ('BBB', 'CCC', 'DDD'):
        leaf = mandate_leaf(projected, snapshot, symbol, ['APPROVED_EQUITIES'])
        assert leaf['truth'] == 'TRUE' and not leaf['missing_fields']
        assert leaf['detail']['approved_scope_source']['original_document_row'] == data['items'][symbol]['original_document_row']
    excess = mandate_leaf(projected, snapshot, 'BBB', ['APPROVED_EQUITIES', 'ADDED_STRATEGY'])
    assert excess['truth'] == 'UNKNOWN'
    assert excess['detail']['approved_components'] == ['APPROVED_EQUITIES']
    assert excess['detail']['unmapped_issuer_components'] == ['ADDED_STRATEGY']
    assert excess['missing_fields'] == ['approved_target.etf_constraints.BBB.changed_mandate_scope_review']
    explicit_policy = deepcopy(projected)
    explicit_policy['payload']['draft']['etf_constraints']['BBB'].pop('mandate_scope_source')
    assert mandate_leaf(explicit_policy, snapshot, 'BBB', ['ADDED_STRATEGY'])['truth'] == 'FALSE'
    unresolved = mandate_leaf(projected, snapshot, 'AAA', ['ADDED_STRATEGY'])
    assert unresolved['truth'] == 'UNKNOWN'
    assert unresolved['detail']['approved_scope_source']['missing_approval_clause'] == data['items']['AAA']['missing_approval_clause']
    assert all(row['lookthrough_restrictions'] == 'EXPLICIT_APPROVED_NONE'
               for row in projected['payload']['draft']['etf_constraints'].values())


@pytest.mark.parametrize('bad', ['client_id', 'account_key', 'source_db_sha256', 'target_version',
    'allocation_version', 'document', 'reference', 'fund', 'row', 'missing_components', 'before_scope'])
def test_invalid_owner_mandate_binding_preserves_unknown_and_lookthrough(tmp_path, bad):
    snapshot, config, base, data, save = mandate_case(tmp_path)
    at = '2026-11-21T01:00:00Z'
    if bad == 'document':
        data['approved_document']['sha256'] = 'b' * 64
    elif bad == 'reference':
        data['approved_document']['source_reference'] = 'drive:OTHER_DOC'
    elif bad == 'fund':
        data['items']['BBB']['instrument_id'] = 'CCC'
    elif bad == 'row':
        data['items']['BBB']['original_document_row'] = data['items']['CCC']['original_document_row']
    elif bad == 'missing_components':
        del data['items']['BBB']['allowed_mandate_components']
    elif bad == 'before_scope':
        at = '2026-11-20T23:54:37Z'
    else:
        data[bad] = 'OTHER'
    save()
    projected = apply(snapshot, config, base, at)
    leaf = mandate_leaf(projected, snapshot, 'BBB', ['APPROVED_EQUITIES'], at)
    assert leaf['truth'] == 'UNKNOWN' and leaf['detail']['approved_components'] is None
    assert 'approved_target.etf_constraints.BBB.allowed_mandate_components' in leaf['missing_fields']
    assert projected['payload']['draft']['etf_constraints']['BBB']['lookthrough_restrictions'] == 'EXPLICIT_APPROVED_NONE'


def test_normal_target_entry_applies_only_explicit_symbols_and_leaves_other_leaves_unknown(tmp_path):
    s,c,_,_,base=case(tmp_path);old=deepcopy(base);out=apply(s,c,base)
    assert base==old
    assert out['payload']['draft']['target_lines']==base['payload']['draft']['target_lines']
    assert out['payload']['draft']['etf_constraints']['AAA']['unrelated_limit']=='UNCHANGED'
    for symbol in ('AAA','BBB','CCC','DDD'):
        req={'client_id':s['client_id'],'evaluation_at':'2026-11-21T01:00:00Z','confirmed_target':out}
        value=evaluate_etf_structure(None,req,symbol)
        leaf=value['leaves'][LEAVES[4]]
        assert leaf['truth']=='TRUE' and leaf['applicability']=='NOT_APPLICABLE_EXPLICIT_APPROVED_NONE'
        assert leaf['detail']['authority_reference'].startswith('https://docs.google.com/document/d/SYNTHETIC_DOC/')
        assert value['result']=='UNKNOWN'
        assert all(value['leaves'][name]['truth']=='UNKNOWN' for name in LEAVES[:4])
    assert approval_target(out,s,'2026-11-21T01:00:00Z')==base


def test_unlisted_symbol_missing_source_and_before_registration_do_not_default_to_none(tmp_path):
    s,c,_,_,base=case(tmp_path)
    assert apply(s,c,base,'2026-11-20T20:59:59Z')==base
    out=apply(s,c,base);req={'client_id':s['client_id'],'evaluation_at':'2026-11-21T01:00:00Z','confirmed_target':out}
    assert evaluate_etf_structure(None,req,'UNLISTED')['leaves'][LEAVES[4]]['truth']=='UNKNOWN'
    c.pop('owner_etf_constraints_source');assert apply(s,c,base)==base


@pytest.mark.parametrize('bad',['client','database','member','account','original_account_row','symbols','document_hash','registration_hash','authority','trade'])
def test_wrong_account_scope_unbound_source_or_projection_is_rejected(tmp_path,bad):
    s,c,d,save,base=case(tmp_path)
    if bad=='client':d['client_id']='OTHER'
    elif bad=='database':d['source_db_sha256']='b'*64
    elif bad=='member':d['member']='OtherMember'
    elif bad=='account':
        d['account_scope']={'account_key':'SYNTHETIC_OTHER','original_account_row':{
            'client_id':s['client_id'],'account_key':'SYNTHETIC_OTHER','account_state':'UNKNOWN'}}
    elif bad=='original_account_row':d['account_scope']['original_account_row']['account_state']='KNOWN'
    elif bad=='symbols':d['symbols'].append('UNLISTED')
    elif bad=='document_hash':d['original_document']['sha256']='b'*64
    elif bad=='registration_hash':d['registration_receipt']['sha256']='b'*64
    elif bad=='authority':d['authority_reference']='UNBOUND_REFERENCE'
    else:d['trade_authorization']='YES'
    save()
    with pytest.raises((PermissionError,ValueError)):apply(s,c,base)


def test_replaying_new_policy_cannot_change_the_original_approval_or_other_constraints(tmp_path):
    s,c,_,_,base=case(tmp_path);out=apply(s,c,base)
    changed=deepcopy(out);changed['payload']['draft']['target_lines'][0]['weight']['value']='0.99'
    with pytest.raises(PermissionError,match='PROJECTION_REPLAY'):approval_target(changed,s,'2026-11-21T01:00:00Z')
    changed=deepcopy(out);changed['payload']['draft']['etf_constraints']['UNLISTED']={'lookthrough_restrictions':'EXPLICIT_APPROVED_NONE'}
    with pytest.raises(PermissionError,match='PROJECTION_REPLAY'):approval_target(changed,s,'2026-11-21T01:00:00Z')


def test_derived_analysis_hash_is_coherent_and_original_signed_target_replays_exactly(tmp_path):
    s,c,_,_,base=case(tmp_path);draft=base['payload']['draft']
    draft['draft_hash']=digest(draft)
    base['payload']['target_hash']=base['target_hash']=draft['draft_hash']
    out=apply(s,c,base);newdraft=out['payload']['draft']
    assert out['target_hash']==out['payload']['target_hash']==newdraft['draft_hash']
    assert newdraft['draft_hash']==digest({k:v for k,v in newdraft.items() if k!='draft_hash'})
    assert out['target_hash']!=base['target_hash']
    assert approval_target(out,s,'2026-11-21T01:00:00Z')==base


def test_registered_revision_time_cannot_be_backdated_to_the_date_only_header(tmp_path):
    s,c,d,save,base=case(tmp_path)
    p=Path(d['registration_receipt']['local_path']);r=json.loads(p.read_bytes());r['modified_at']='2026-11-20T16:00:00Z'
    p.write_text(json.dumps(r));d['registration_receipt']['sha256']=sha256(p.read_bytes()).hexdigest();save()
    with pytest.raises(PermissionError,match='REGISTRATION_TIME'):apply(s,c,base)


def test_project_reads_registered_dated_mandate_and_checks_its_bytes(tmp_path):
    from on_demand_project import register_project_mandate

    snapshot, config, target, first, _ = mandate_case(tmp_path)
    del config['owner_etf_constraints_source']['mandate_source']
    second = deepcopy(first)
    second['available_at'] = '2026-11-21T02:00:00Z'
    item = second['items']['AAA']
    del item['missing_approval_clause']
    item['allowed_mandate_components'] = ['APPROVED_EQUITIES']
    item['product_basis'] = {'source_reference': 'SYNTHETIC_SECTION_6'}
    file = tmp_path / 'registered.json'
    file.write_text(json.dumps({'schema_version': 'Family.W8.RegisteredMandateRevisions.v1',
        'approved_document_utf8': Path(first['approved_document']['local_path']).read_text(),
        'revisions': [second, first]}))
    registration = {'member': 'SyntheticMember', 'file_name': file.name, 'drive_file_id': 'TEST',
                    'sha256': sha256(file.read_bytes()).hexdigest()}
    sources = tmp_path / 'Sources.txt'
    sources.write_text('MENU04_REGISTERED_MANDATE=' + json.dumps(registration))
    desc = {'local_path': str(sources), 'sha256': sha256(sources.read_bytes()).hexdigest()}
    register_project_mandate(config, desc, 'SyntheticMember')
    for at, expected in [('2026-11-21T01:59:59Z', 'UNKNOWN'), (second['available_at'], 'TRUE')]:
        result = apply(snapshot, config, target, at)
        assert mandate_leaf(result, snapshot, 'AAA', ['APPROVED_EQUITIES'], at)['truth'] == expected
    with pytest.raises(PermissionError, match='REGISTRATION_MISMATCH'):
        register_project_mandate(config, desc, 'OtherMember')
    file.write_bytes(file.read_bytes() + b' ')
    with pytest.raises(PermissionError, match='MANDATE_BYTES_CHANGED'):
        register_project_mandate(config, desc, 'SyntheticMember')
    sources.write_text('different')
    with pytest.raises(PermissionError, match='SOURCES_BYTES_CHANGED'):
        register_project_mandate(config, desc, 'SyntheticMember')


def test_registered_issuer_structure_never_overrides_primary_observation(tmp_path):
    snapshot, config, target, original, _ = mandate_case(tmp_path)
    at = '2026-11-21T01:00:00Z'
    proj = apply(snapshot, config, target, at)
    request = {'client_id':snapshot['client_id'], 'evaluation_at':at,'confirmed_target':proj}
    issuer = {'symbol':'BBB', 'source_sha256':'b'*64, 'source_url':'https://fund-docs.vanguard.com/synthetic.pdf',
              'mandate':{'components':['APPROVED_EQUITIES'], 'method_version':'test',
                         'as_of':'2026-11-20T00:00:00Z','available_at':'2026-11-20T09:00:00Z',
                         'valid_until':'2026-11-22T00:00:00Z','data_quality':'OK'}}
    assert evaluate_etf_structure(None,request,'BBB',None,issuer)['leaves'][LEAVES[1]]['truth']=='TRUE'
    primary={**issuer, 'mandate':{**issuer['mandate'], 'components':['OTHER']}}
    leaf=evaluate_etf_structure(primary,request,'BBB',None,issuer)['leaves'][LEAVES[1]]
    assert leaf['truth']=='UNKNOWN' and leaf['detail']['unmapped_issuer_components']==['OTHER']
    with pytest.raises(PermissionError,match='REGISTERED_ISSUER_STRUCTURE_MISMATCH'):
        evaluate_etf_structure(None,request,'BBB',None,{**issuer, 'symbol':'AAA'})
