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
