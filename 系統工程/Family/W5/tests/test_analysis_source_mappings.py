"""Market references and logical roles do not rewrite W1 or authorize orders."""
from copy import deepcopy
import pytest
from family_boundary import prepare_input,BoundaryError
from family_input import digest
from stock_source_bridge import bind_stock_source
from bond_source_bridge import bind_bond_sources
from position_source_bridge import bind_position_values
from test_family_runner import runner_case
from test_stock_source_bridge import refresh


def test_separate_market_reference_preserves_unknown_held_exchange_and_quantity():
    req,ctx=runner_case();binding=ctx['native_binding'];facts=req['native_bundle']['stock_evidence']
    req['client_snapshot']['payload']['tables']['portfolio_instrument'][0]['exchange_code']=None
    facts['market_identity_digest']='source-identity'
    binding['stock_instrument']['market_reference']={'scope':'ANALYSIS_MARKET_REFERENCE__NOT_HELD_OR_EXECUTION_VENUE',
        'asset_id':'QQQ','exchange':facts['exchange'],'currency':'USD','source_digest':'source-identity',
        'source_reference':'SYNTHETIC_QUALIFIED_HISTORY'}
    refresh(req,ctx);before=deepcopy((req,ctx));prepared=prepare_input(req,trusted_context=ctx)
    bound=bind_stock_source(req,prepared,binding)
    assert bound['held_exchange'] is None and bound['confirmed_quantity']=='0'
    assert (req,ctx)==before
    binding['stock_instrument']['market_reference']['asset_id']='OTHER'
    with pytest.raises(BoundaryError,match='STOCK_MARKET_REFERENCE_MISMATCH'):
        bind_stock_source(req,prepared,binding)


def role_case(bond='0',dry='120'):
    req,ctx=runner_case();bundle=req['native_bundle']
    roles={'sgov_bond_bucket_amount':{'amount':bond,'currency':'USD'},
        'sgov_dry_powder_bucket_amount':{'amount':dry,'currency':'USD'}}
    bundle['stock_request']['work3_handoff']['funding_context']['sgov_boundary'].update(deepcopy(roles))
    facts=bundle['bond_evidence']['SGOV']
    facts['sgov_role_binding']={**roles,'physical_quantity':'1','physical_value':'120'}
    facts['existing_policy']['current_position_quantity']='1' if bond=='120' else '0'
    refresh(req,ctx)
    return req,ctx


@pytest.mark.parametrize('bond,dry,expected',[('0','120','0'),('120','0','1')])
def test_physical_sgov_share_is_separate_from_bond_policy_share(bond,dry,expected):
    req,ctx=role_case(bond,dry);before=deepcopy((req,ctx))
    bound=bind_bond_sources(req,prepare_input(req,trusted_context=ctx),ctx['native_binding'])['SGOV']
    assert bound['confirmed_quantity']=='1' and bound['logical_bond_quantity']==expected
    assert (req,ctx)==before


def test_mixed_role_requires_source_share_split_instead_of_target_ratio():
    req,ctx=role_case('60','60')
    with pytest.raises(BoundaryError,match='BOND_MIXED_ROLE_QUANTITY_SOURCE_REQUIRED'):
        bind_bond_sources(req,prepare_input(req,trusted_context=ctx),ctx['native_binding'])


def test_role_money_must_reconcile_to_physical_value():
    req,ctx=role_case('0','119')
    with pytest.raises(BoundaryError,match='BOND_SGOV_ROLE_SOURCE_MISMATCH'):
        bind_bond_sources(req,prepare_input(req,trusted_context=ctx),ctx['native_binding'])


def test_existing_approval_can_map_absent_bond_without_creating_w1_or_buy_permission():
    req,ctx=runner_case();tables=req['client_snapshot']['payload']['tables']
    target=next(r for r in req['confirmed_target']['payload']['draft']['target_lines'] if r['ticker']=='SPSB')
    tables['portfolio_instrument']=[r for r in tables['portfolio_instrument'] if r['ticker']!='SPSB']
    tables['portfolio_position']=[r for r in tables['portfolio_position'] if r['instrument_key']!='SPSB_KEY']
    facts=req['native_bundle']['bond_evidence']['SPSB'];facts['market_identity_digest']='source-SPSB'
    mapping=ctx['native_binding']['bond_instruments']['SPSB']
    mapping.update(instrument_key='APPROVED_TARGET:'+target['instrument_id'],approved_target_source=deepcopy(target),
        market_reference={'scope':'ANALYSIS_MARKET_REFERENCE__NOT_HELD_OR_EXECUTION_VENUE',
            'asset_id':'SPSB','exchange':'ARCA','currency':'USD','source_digest':'source-SPSB','source_reference':'SYNTHETIC_MARKET'})
    refresh(req,ctx);before=deepcopy((req,ctx));prepared=prepare_input(req,trusted_context=ctx)
    result=bind_bond_sources(req,prepared,ctx['native_binding'])['SPSB']
    assert result['approved_target_only'] and result['confirmed_quantity']=='0'
    assert result['additional_new_buy_cap']=='0' and result['policy']['reason_codes']==['W1_PERMISSION_NOT_REGISTERED']
    assert (req,ctx)==before
    mapping['approved_target_source']['ticker']='OTHER'
    with pytest.raises(BoundaryError,match='BOND_TARGET_INSTRUMENT_SOURCE_REQUIRED'):
        bind_bond_sources(req,prepared,ctx['native_binding'])


def test_current_quantity_reference_price_keeps_original_price_clock():
    req,ctx=runner_case();quote=ctx['valuation_source']['prices']['QQQ']
    observed=quote['as_of'];quote.update(as_of=req['evaluation_at'],price_observation_as_of=observed,
        valuation_basis='CURRENT_QUANTITY_AT_KNOWN_REFERENCE_PRICE',price_source_digest='source-QQQ')
    refresh(req,ctx);prepared=prepare_input(req,trusted_context=ctx)
    prepared.payload['stock_source']=bind_stock_source(req,prepared,ctx['native_binding'])
    prepared.payload['family_sources']={'bond':bind_bond_sources(req,prepared,ctx['native_binding'])}
    result=bind_position_values(req,prepared,ctx)
    assert result['positions']['QQQ']['sources']['price']['price_observation_as_of']==observed
    quote.pop('valuation_basis');req['valuation_digest']=digest(ctx['valuation_source'])
    with pytest.raises(BoundaryError,match='STOCK_VALUATION_REFERENCE_CLOCK_REQUIRED'):
        bind_position_values(req,prepared,ctx)
