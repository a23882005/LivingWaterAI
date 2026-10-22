import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resource_headers import *

def header():
    return dict(schema=SCHEMA,resource_key='family.mou',binding='BOUND',file_id='synthetic_mou_id',policy_ref='private.mou',state='Close',readers=[],updater=None)

def policies():return {'private.mou':{'read':['account:mou'],'update':['account:mou']}}

def test_roundtrip_and_owner():
    h=parse_header(render_header(header()))
    assert authorize(h,policies(),VerifiedPrincipal('account:mou',100),'update',99)=='synthetic_mou_id'

@pytest.mark.parametrize('p',[{'subject':'account:mou','expires_at':100},VerifiedPrincipal('account:Arthur',100),VerifiedPrincipal('account:mou',99)])
def test_untrusted_wrong_account_and_expired(p):
    with pytest.raises(PermissionError):authorize(header(),policies(),p,'read',99)

def test_text_cannot_add_permissions():
    h=header();h['readers']=['account:Arthur'];h['state']='Read'
    with pytest.raises(PermissionError):authorize(h,policies(),VerifiedPrincipal('account:Arthur',100),'read',99)

@pytest.mark.parametrize('field,value',[('state','Read'),('state','Update'),('state','open'),('updater','account:mou'),('file_id','../other'),('admin',True)])
def test_bad_header(field,value):
    h=header();h[field]=value
    with pytest.raises(ValueError):validate_header(h)

def test_active_states():
    h=header();h.update(state='Read',readers=['account:mou']);validate_header(h)
    h.update(state='Update',readers=[],updater='account:mou');validate_header(h)

def test_unbound_account_database_is_closed():
    h=header();h.update(binding='PENDING_B07',file_id=None)
    validate_header(h)
    with pytest.raises(PermissionError):authorize(h,policies(),VerifiedPrincipal('account:mou',100),'read',99)
    h.update(state='Update',updater='account:mou')
    with pytest.raises(ValueError):validate_header(h)

def test_duplicate_keys_or_multiple_blocks():
    text=render_header(header())
    with pytest.raises(ValueError):parse_header(text+text)
    with pytest.raises(ValueError):parse_header(text.replace('"schema":','"schema":"forged", "schema":'))

def test_catalog_duplicate_or_missing_policy():
    text=render_header(header())
    assert len(load_catalog([text],policies()))==1
    with pytest.raises(ValueError):load_catalog([text,text],policies())
    h=header();h['resource_key']='other'
    with pytest.raises(ValueError):load_catalog([text,render_header(h)],policies())
    with pytest.raises(ValueError):load_catalog([text],{})

def test_unknown_operation_and_wildcard():
    with pytest.raises(PermissionError):authorize(header(),policies(),VerifiedPrincipal('account:mou',100),'admin',99)
    p=policies();p['private.mou']['read']=['*']
    with pytest.raises(ValueError):validate_policies(p)
