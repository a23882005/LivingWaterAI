"""01 regression: current assets and interview save; no forced 60/40 deployment.
Synthetic-only; never touch Family formal DB, Drive or authenticated production.
"""
from pathlib import Path
from hashlib import sha256
import copy
import importlib.util
import json
import sqlite3
import sys
import tempfile
import uuid
import pytest

W7=Path(__file__).resolve().parents[1]
W5=W7.parent/'W5'
sys.path.insert(0,str(W7))
sys.path.insert(0,str(W5))
from first_allocation import (make_writer, first_allocation_handler,
                              completion_check, normalize_request,
                              OPERATION, STATUS)
from family_input import read_snapshot
from family_menu import FamilyMenu

C='TEST_CLIENT'
ACCOUNT='USER_CONFIRMED_ACCOUNT'
SPEC=json.loads((W5/'w1_schema_columns.json').read_text(encoding='utf-8'))


def fixture():
    root=Path(tempfile.mkdtemp())
    file=root/'synthetic.db'
    with sqlite3.connect(file) as db:
        db.execute('create table family_member_identity (client_id text)')
        db.execute('insert into family_member_identity values (?)',(C,))
        for table,cols in SPEC.items():
            columns=', '.join('"' + d['column'] + '" ' + d['sqlite_type'] for d in cols)
            db.execute('create table "'+table+'" ('+columns+')')
    return file


def record():
    return {'interview_confirmed':True,'as_of_utc':'2026-10-25T00:00:00Z',
            'confirmation_reference':'synthetic-mentor-confirmation',
            'mentor_answers':{'life_stage':'WORKING','withdrawal_horizon':'10+Y',
                              'interview_complete_count':13},
            'long_term_style':{'stock_weight':'0.60','bond_weight':'0.40'},
            'holdings':[{'ticker':'2454','display_name':'Synthetic chip company',
                         'exchange':'TWSE','currency':'TWD',
                         'reported_market_value':'100000',
                         'value_is_estimate':True,'confirmed_quantity':None}],
            'cash':[{'currency':'TWD','reported_amount':'50000',
                     'settled_verified':False}]}


class FakeCoordinator:
    """Imitates B06 snapshot/update idempotency; all bytes remain in temp fixture."""
    def __init__(self,path):
        self.path=path
        self.epoch='e1'
        self.saved={}
        self.calls=[]
        self.writer=make_writer(C,ACCOUNT)

    def snapshot(self,resource,principal):
        b=self.path.read_bytes()
        return {'data':b,'sha256':sha256(b).hexdigest(),'epoch':self.epoch}

    def update(self,resource,principal,request_id,epoch,op,payload):
        assert epoch==self.epoch and op==OPERATION
        assert resource=='personal'
        key=(request_id,json.dumps(payload,sort_keys=True))
        if request_id in self.saved:
            prior,old=self.saved[request_id]
            if prior!=key[1]:
                raise ValueError('REQUEST_COLLISION')
            return {'result':old,'duplicate':True,'epoch':epoch}
        with sqlite3.connect(self.path) as db:
            result=self.writer(db,payload)
        self.saved[request_id]=(key[1],result)
        self.epoch=uuid.uuid4().hex
        self.calls.append(op)
        return {'result':result,'duplicate':False,'epoch':epoch}


def run(coordinator,payload=None):
    h=first_allocation_handler(coordinator,principal=object(),resource='personal',
                               client_id=C,account_key=ACCOUNT)
    return h({'request_id':'stable-request-1','confirmed_record':payload or record()})


def test_01_held_stock_and_cash_saved_independently_without_loop2():
    file=fixture()
    c=FakeCoordinator(file)
    out=run(c)
    assert out['status']==STATUS and completion_check(out)
    assert out['loop2_executed'] is False and out['trade_authorization']=='NONE'
    assert c.calls==[OPERATION]
    snap=read_snapshot(file,expected_client_id=C)
    tables=snap['tables']
    positions=[x for x in tables['portfolio_position'] if x['instrument_key'].startswith('USER01-')]
    assert len(positions)==1 and positions[0]['quantity_decimal'] is None
    assert positions[0]['cost_basis_total_decimal'] is None
    assert positions[0]['cost_state']=='UNKNOWN'
    cash=tables['cash_balance_snapshot']
    assert len(cash)==1 and cash[0]['reported_cash_minor']==5000000
    assert cash[0]['normalized_settled_minor'] is None
    assert cash[0]['reconciled_at_utc'] is None
    fields={x['field_key']:x['value_text'] for x in tables['portfolio_snapshot_item']}
    assert fields['reported_market_value']=='100000'
    assert fields['stock_weight']=='0.60' and fields['bond_weight']=='0.40'
    assert fields['value_is_estimate']=='true'
    assert fields['settled_verified']=='false'
    assert tables['final_target_version']==[] and tables['final_target_allocation']==[]


def test_01_duplicate_request_returns_same_record_without_double_entry():
    file=fixture()
    c=FakeCoordinator(file)
    first=run(c);second=run(c)
    assert first['run_id']==second['run_id']
    assert len(c.calls)==1
    with sqlite3.connect(file) as db:
        assert db.execute('select count(*) from cash_balance_snapshot').fetchone()[0]==1
        assert db.execute('select count(*) from portfolio_snapshot_run').fetchone()[0]==1


def test_01_current_holdings_exceed_60pct_does_not_block():
    file=fixture()
    c=FakeCoordinator(file)
    got=run(c)
    assert completion_check(got) and got['holdings_recorded']==1


def test_01_unconfirmed_interview_rejected_and_db_unchanged():
    file=fixture();c=FakeCoordinator(file)
    before=file.read_bytes();obj=record();obj['interview_confirmed']=False
    with pytest.raises(ValueError,match='CONFIRMED_INTERVIEW_REQUIRED'):
        run(c,obj)
    assert file.read_bytes()==before


def test_01_wrong_client_rejected_and_db_unchanged():
    file=fixture()
    with sqlite3.connect(file) as db:
        db.execute('update family_member_identity set client_id="OTHER"')
    before=file.read_bytes();c=FakeCoordinator(file)
    with pytest.raises(PermissionError,match='CLIENT_MISMATCH'):
        run(c)
    assert file.read_bytes()==before


def test_01_menu_closes_only_on_trusted_save_receipt():
    file=fixture(); c=FakeCoordinator(file)
    class Auth:
        def require_login(self):return C
    h=first_allocation_handler(c,principal=object(),resource='personal',client_id=C,account_key=ACCOUNT)
    menu=FamilyMenu(Auth(),project_name='Synthetic',login_account='synthetic',
                    handlers={'first_allocation':h},
                    completion_checks={'first_allocation':completion_check})
    got=menu.select(1,payload={'request_id':'stable-request-1','confirmed_record':record()})
    assert got['status']=='COMPLETED'
    assert got['result']['status']==STATUS
    assert got['menu'].count('｜')==14


@pytest.mark.parametrize('change',[{'long_term_style':{'stock_weight':'1.1','bond_weight':'-0.1'}},
                                   {'cash':[{'currency':'TWD','reported_amount':'-1'}]},
                                   {'holdings':[{'ticker':'2454','display_name':'Stock','currency':'TWD',
                                                 'reported_market_value':'100000','confirmed_quantity':'0'}]}])
def test_01_invalid_input_rejected(change):
    x=record();x.update(change)
    with pytest.raises(ValueError):
        normalize_request(x)


def test_01_false_completion_receipt_rejected():
    assert not completion_check({'status':'INTERVIEW_COMPLETE'})
    assert not completion_check({'status':STATUS,'save_receipt':{'verified':True}})


def test_01_without_ratio_does_not_invent_any_long_term_target():
    file=fixture();coordinator=FakeCoordinator(file)
    payload=record();payload.pop('long_term_style')
    out=run(coordinator,payload)
    assert completion_check(out)
    snap=read_snapshot(file,expected_client_id=C)
    fields={x['field_key'] for x in snap['tables']['portfolio_snapshot_item']}
    assert 'stock_weight' not in fields and 'bond_weight' not in fields
    assert snap['tables']['final_target_allocation']==[]


def test_01_with_actual_b06_transaction_and_receipt_deduplication():
    """Exercise the real B06 transaction/authorizer rather than only a fake adapter."""
    from 資料存取管理 import transaction
    file=fixture()
    payload={'client_id':C,'request_id':'req-b06-1',
             'confirmed_record':normalize_request(record())}
    before=file.read_bytes()
    updated, result, duplicate=transaction(
        before, 'account:TEST', 'req-b06-1', OPERATION, payload,
        make_writer(C,ACCOUNT))
    assert duplicate is False and result['status']=='STORED'
    file.write_bytes(updated)
    assert read_snapshot(file,expected_client_id=C)['tables']['cash_balance_snapshot'][0]['reported_cash_minor']==5000000
    unchanged, again, duplicate=transaction(
        updated,'account:TEST','req-b06-1',OPERATION,payload,
        make_writer(C,ACCOUNT))
    assert duplicate is True and unchanged==updated and again==result
