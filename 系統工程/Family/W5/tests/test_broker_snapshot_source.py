"""Synthetic source boundaries; real account acceptance is captured privately."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import pytest
from broker_snapshot_source import read,project_positions,project_holdings
from family_input import digest
from family_boundary import prepare_input
from test_family_boundary import fixture


def broker_case(tmp_path):
    req,ctx=fixture('fam_'+'a'*32)
    req['evaluation_at']='2026-10-27T12:00:00Z'
    req['client_snapshot']['payload']['source_sha256']='a'*64
    req['client_snapshot']['digest']=ctx['snapshot_digest']=digest(req['client_snapshot']['payload'])
    original=prepare_input(req,trusted_context=ctx).payload['positions']
    symbol=original[0]['source_instrument']['ticker'];owner=req['owner']
    def save(name,payload,method=None,args=None):
        path=tmp_path/name;path.write_text(json.dumps(payload))
        ref={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
        if method:ref.update(tool_name=method,arguments=args or {})
        return ref
    def result(**data):return {'status':'fulfilled','value':{'isError':False,'structuredContent':data}}
    auth=save('owner.json',{'schema_version':'Family.W8.BrokerConnectionOwner.v1',
        'client_id':req['client_id'],'owner':owner,'recorded_at':'2026-10-25T00:00:00Z',
        'source_reference':'SYNTHETIC_OWNER_IDENTITY','scope':'READ_ONLY_RECONCILIATION_AND_ADVICE','trade_authorization':'NONE'})
    pos=save('positions.json',result(positions=[{'contract_description':symbol,'contract_id':123,
        'position':3,'currency':owner['currency'],'asset_class':'STK','market_price':100,'average_price':90}]),'get_account_positions')
    balances=save('balances.json',result(balances=[{'currency':owner['currency'],'cash_balance':20,'settled_cash':20}]),'get_account_balances')
    summary=save('summary.json',result(available_funds=10000,buying_power=40000),'get_account_summary')
    orders=save('orders.json',result(orders=[{'order_id':456,'primary_description':'Buy 1 '+symbol,
        'side':'BUY','order_status':'REPLACED','total_shares_qty':'1','cum_shares_qty':'0',
        'remaining_shares_qty':'1','limit_price':'90','order_time':'2026-10-25T12:00:00Z'}]),
        'get_account_orders',{'show_completed':False})
    manifest={'schema_version':'Family.W5.ReadonlyBrokerSnapshot.v1','client_id':req['client_id'],
        'owner':owner,'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],
        'captured_at':'2026-10-26T00:00:00Z','owner_authorization':auth,
        'positions':pos,'balances':balances,'summary':summary,'orders':orders}
    source=save('manifest.json',manifest);ctx['broker_snapshot_source']=source
    req['broker_snapshot_source_digest']=digest(source)
    return req,ctx,original,source,manifest,save


def test_actual_boundary_projects_quantities_without_editing_db_snapshot(tmp_path):
    req,ctx,original,source,_,_=broker_case(tmp_path);before=deepcopy(req['client_snapshot'])
    prepared=prepare_input(req,trusted_context=ctx)
    position=prepared.payload['positions'][0]
    assert position['quantity']=='3' and position['source_position']['source_kind']=='BROKER_READONLY_SNAPSHOT'
    assert position['original_db_position']==original[0]
    assert req['client_snapshot']==before
    view=prepared.payload['broker_snapshot_source']
    assert view['cash']['total']=='20' and view['cash']['available'] is None
    assert view['cash']['account_summary_observations']['available_funds']==10000
    assert not view['cash']['margin_funds_used_as_cash']


def test_replaced_in_working_list_keeps_remaining_exposure_and_original_label(tmp_path):
    req,ctx,_,source,_,_=broker_case(tmp_path);view=read(req,source)
    orders=view['order_source'];assert orders['complete_for_open_order_exposure']
    assert not orders['lifecycle_fully_resolved']
    assert orders['active_orders'][0]['state']=='REPLACE_PENDING'
    assert orders['active_orders'][0]['provider_status']=='REPLACED'
    assert orders['active_orders'][0]['remaining_qty']=='1'


@pytest.mark.parametrize('field',['client_id','owner','source_db_sha256'])
def test_other_member_or_db_is_rejected(tmp_path,field):
    req,ctx,_,source,_,_=broker_case(tmp_path)
    if field=='owner':req['owner']['account']='OTHER'
    elif field=='client_id':req['client_id']='OTHER'
    else:req['client_snapshot']['payload']['source_sha256']='b'*64
    with pytest.raises(PermissionError,match='OWNER_OR_DB'):read(req,source)


def test_tampered_or_future_broker_data_is_not_adopted(tmp_path):
    req,ctx,_,source,manifest,save=broker_case(tmp_path)
    Path(manifest['positions']['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):read(req,source)
    req,ctx,_,source,manifest,save=broker_case(tmp_path)
    manifest['captured_at']='2099-01-01T00:00:00Z';source=save('manifest.json',manifest)
    with pytest.raises(PermissionError,match='FUTURE_CAPTURE'):read(req,source)


def test_inconsistent_order_remains_unknown_without_losing_positions(tmp_path):
    req,ctx,_,source,manifest,save=broker_case(tmp_path)
    path=Path(manifest['orders']['local_path']);raw=json.loads(path.read_text())
    raw['value']['structuredContent']['orders'][0]['remaining_shares_qty']='2'
    manifest['orders']=save('orders.json',raw,'get_account_orders',{'show_completed':False})
    source=save('manifest.json',manifest);view=read(req,source)
    assert len(view['positions'])==1
    assert view['order_source']['status']=='UNKNOWN' and view['order_source']['active_orders'] is None


def test_request_cannot_inject_untrusted_broker_digest(tmp_path):
    req,ctx,_,_,_,_=broker_case(tmp_path);ctx.pop('broker_snapshot_source')
    with pytest.raises(ValueError,match='TRUSTED_BROKER_SOURCE_REQUIRED'):
        prepare_input(req,trusted_context=ctx)
