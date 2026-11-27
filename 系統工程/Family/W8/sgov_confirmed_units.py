"""Read existing position-bound SGOV role confirmations; never create one.

The latest known/effective proposal must itself be confirmed. A pending or
unknown successor cannot fall back to an earlier approval. Role shares are
accounting units of one physical position, never settled cash or sale consent.
"""
from copy import deepcopy
from decimal import Decimal,localcontext,InvalidOperation
from family_input import digest
from member_market_source import time


class RoleSourceUnavailable(ValueError):
    pass


def number(value):
    if value is None or isinstance(value,bool):raise RoleSourceUnavailable('SGOV_ROLE_EXACT_NUMBER_REQUIRED')
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):raise RoleSourceUnavailable('SGOV_ROLE_EXACT_NUMBER_REQUIRED') from None
    if not n.is_finite() or n<0:raise RoleSourceUnavailable('SGOV_ROLE_NONNEGATIVE_NUMBER_REQUIRED')
    return n


def _known(row,fields,cutoff):
    return all(row.get(k) and time(row[k])<=cutoff for k in fields)


def _unique(rows,code):
    values={digest(r):r for r in rows}
    if len(values)!=1:raise RoleSourceUnavailable(code)
    return next(iter(values.values()))


def select(request,account,quantity,*,instrument_key=None,position_as_of=None):
    """Return original rows for the exact current physical position at cutoff."""
    client=request['client_id'];snapshot=request['client_snapshot']['payload'];tables=snapshot['tables']
    cutoff=time(request['evaluation_at'])
    if not isinstance(account,str) or not account:
        raise RoleSourceUnavailable('SGOV_ROLE_SINGLE_ACCOUNT_BINDING_REQUIRED')
    account_positions=[r for r in tables.get('portfolio_position',[]) if r.get('client_id')==client
        and r.get('account_key')==account and r.get('position_source_kind') not in (None,'NOT_PROVIDED')
        and r.get('position_source_reference') and _known(r,('as_of_utc','recorded_at_utc'),cutoff)]
    account_instruments={r.get('instrument_key') for r in account_positions}
    instruments=[r for r in tables.get('portfolio_instrument',[]) if r.get('client_id')==client
        and r.get('ticker')=='SGOV' and r.get('instrument_type')=='ETF' and r.get('identity_state')=='KNOWN'
        and r.get('instrument_key') in account_instruments
        and r.get('source_kind') not in (None,'NOT_PROVIDED') and r.get('source_reference')
        and _known(r,('as_of_utc','created_at_utc'),cutoff)]
    if instrument_key is not None:instruments=[r for r in instruments if r.get('instrument_key')==instrument_key]
    instrument=_unique(instruments,'SGOV_ROLE_ORIGINAL_INSTRUMENT_IDENTITY_REQUIRED')
    positions=[r for r in account_positions if r.get('instrument_key')==instrument['instrument_key']]
    if not positions:raise RoleSourceUnavailable('SGOV_ROLE_CURRENT_POSITION_SOURCE_REQUIRED')
    latest=max(time(r['as_of_utc']) for r in positions)
    position=_unique([r for r in positions if time(r['as_of_utc'])==latest],'SGOV_ROLE_CURRENT_POSITION_AMBIGUOUS')
    if position_as_of is not None and time(position_as_of)!=latest:
        raise RoleSourceUnavailable('SGOV_ROLE_POSITION_NOT_CURRENT_AT_CUTOFF')
    if number(position.get('quantity_decimal'))!=number(quantity):
        raise RoleSourceUnavailable('SGOV_ROLE_PHYSICAL_QUANTITY_CHANGED__NEW_POSITION_ROLE_REQUIRED')
    key=dict(client_id=client,account_key=account,instrument_key=instrument['instrument_key'],position_as_of_utc=position['as_of_utc'])
    def matches(row):return all(row.get(k)==v for k,v in key.items())
    candidates=[r for r in tables.get('sgov_role_proposal',[]) if matches(r)
        and r.get('created_at_utc') and time(r['created_at_utc'])<=cutoff]
    versions={}
    for r in candidates:
        version=r.get('version_no')
        if type(version) is not int or version<1 or r.get('previous_version_no')!=(None if version==1 else version-1):
            raise RoleSourceUnavailable('SGOV_ROLE_VERSION_CHAIN_INVALID')
        if (not r.get('effective_at_utc') or time(r['effective_at_utc'])<time(r['created_at_utc'])
            or time(r['created_at_utc'])<latest):raise RoleSourceUnavailable('SGOV_ROLE_VERSION_TIME_CONFLICT')
        if version in versions and versions[version]!=r:raise RoleSourceUnavailable('SGOV_ROLE_VERSION_CONFLICT')
        versions[version]=r
    if not versions:raise RoleSourceUnavailable('SGOV_ROLE_POSITION_PROPOSAL_REQUIRED')
    if sorted(versions)!=list(range(1,max(versions)+1)):raise RoleSourceUnavailable('SGOV_ROLE_VERSION_CHAIN_INCOMPLETE')
    ordered=[versions[k] for k in sorted(versions)]
    if any(time(a['effective_at_utc'])>time(b['effective_at_utc']) or time(a['created_at_utc'])>time(b['created_at_utc']) for a,b in zip(ordered,ordered[1:])):
        raise RoleSourceUnavailable('SGOV_ROLE_VERSION_TIME_ORDER_CONFLICT')
    effective=[r for r in ordered if time(r['effective_at_utc'])<=cutoff]
    if not effective:raise RoleSourceUnavailable('SGOV_ROLE_NO_EFFECTIVE_VERSION_AT_CUTOFF')
    proposal=effective[-1];bond=proposal.get('bond_core_bps');dry=proposal.get('dry_powder_bps')
    if (proposal.get('role_state')!='VERIFIED' or proposal.get('evidence_state')!='VERIFIED'
        or proposal.get('source_kind') not in ('USER_PROVIDED','OWNER_VERIFIED','DOCUMENT','AUTHORIZED_IMPORT')
        or not proposal.get('source_reference') or type(bond) is not int or type(dry) is not int
        or min(bond,dry)<0 or max(bond,dry)>10000 or bond+dry!=10000):
        raise RoleSourceUnavailable('SGOV_ROLE_LATEST_EFFECTIVE_VERSION_NOT_QUALIFIED')
    confirmations=[r for r in tables.get('sgov_role_confirmation',[]) if matches(r)
        and r.get('version_no')==proposal['version_no'] and r.get('confirmed_at_utc')
        and time(r['confirmed_at_utc'])<=cutoff]
    confirmation=_unique(confirmations,'SGOV_ROLE_LATEST_EFFECTIVE_VERSION_CONFIRMATION_REQUIRED')
    if (confirmation.get('confirmer_kind') not in ('CLIENT','AUTHORIZED_REPRESENTATIVE') or not confirmation.get('confirmer_reference')
        or confirmation.get('confirmation_source_kind') not in ('USER_PROVIDED','OWNER_VERIFIED','DOCUMENT')
        or not confirmation.get('confirmation_source_reference')
        or time(confirmation['confirmed_at_utc'])<time(proposal['created_at_utc'])):
        raise RoleSourceUnavailable('SGOV_ROLE_OWNER_CONFIRMATION_SOURCE_REQUIRED')
    result=dict(schema_version='Family.W8.ConfirmedSgovPositionRole.v1',client_id=client,account_key=account,
        source_db_sha256=snapshot['source_sha256'],evaluation_at=request['evaluation_at'],
        instrument=deepcopy(instrument),position=deepcopy(position),proposal=deepcopy(proposal),confirmation=deepcopy(confirmation))
    result['digest']=digest(result)
    return result


def units(selection,quantity):
    qty=number(quantity)
    if number(selection['position']['quantity_decimal'])!=qty:raise RoleSourceUnavailable('SGOV_ROLE_UNIT_POSITION_QUANTITY_CONFLICT')
    proposal=selection['proposal'];bond=proposal['bond_core_bps'];dry=proposal['dry_powder_bps']
    if type(bond) is not int or type(dry) is not int or min(bond,dry)<0 or bond+dry!=10000:
        raise RoleSourceUnavailable('SGOV_ROLE_UNIT_BASIS_POINTS_CONFLICT')
    with localcontext() as numeric:
        numeric.prec=max(50,len(qty.as_tuple().digits)+12)
        b=qty*Decimal(bond)/10000;d=qty-b
    return dict(physical_quantity=str(qty),bond_quantity=str(b),dry_quantity=str(d),unit='SHARES',
        position_role_digest=selection['digest'])


def validated_units(source):
    """Check the replayed role accounting; upstream validate re-reads the DB."""
    basis=source.get('source_basis') or {};selection=basis.get('confirmed_position_role')
    if (source.get('status')!='SOURCE_DERIVED_ACCOUNTING' or basis.get('kind')!='EXISTING_CONFIRMED_POSITION_ROLE_VERSION'
        or not isinstance(selection,dict) or source.get('owner_role_confirmation')!=selection.get('confirmation')):
        raise RoleSourceUnavailable('SGOV_CONFIRMED_ROLE_UNITS_REQUIRED')
    raw=deepcopy(selection);claimed=raw.pop('digest',None)
    if claimed!=digest(raw):raise RoleSourceUnavailable('SGOV_ROLE_SELECTION_DIGEST_CONFLICT')
    physical=source['physical'];expected=units(selection,physical['quantity'])
    if source.get('role_quantities')!=expected:raise RoleSourceUnavailable('SGOV_ROLE_UNIT_ALLOCATION_CONFLICT')
    if (selection['client_id']!=source['client_id'] or selection['source_db_sha256']!=source['source_db_sha256']
        or source['owner'].get('client_id')!=source['client_id']
        or selection['account_key']!=source['owner']['account'] or selection['evaluation_at']!=source.get('evaluation_at')
        or physical['valuation']['currency']!=source['owner']['currency']):
        raise RoleSourceUnavailable('SGOV_ROLE_UNIT_OWNER_OR_DB_CONFLICT')
    price=number(physical['price']);value=number(physical['valuation']['amount']);qty=number(expected['physical_quantity'])
    with localcontext() as numeric:
        numeric.prec=50
        b=number(expected['bond_quantity'])*price;d=value-b
        if qty*price!=value or d!=number(expected['dry_quantity'])*price:
            raise RoleSourceUnavailable('SGOV_ROLE_UNIT_PHYSICAL_VALUE_CONFLICT')
    if any(source['roles'][k].get('currency')!=physical['valuation']['currency'] for k in ('sgov_bond_bucket_amount','sgov_dry_powder_bucket_amount')):
        raise RoleSourceUnavailable('SGOV_ROLE_UNIT_CURRENCY_CONFLICT')
    if number(source['roles']['sgov_bond_bucket_amount']['amount'])!=b or number(source['roles']['sgov_dry_powder_bucket_amount']['amount'])!=d:
        raise RoleSourceUnavailable('SGOV_ROLE_UNIT_MONEY_CONFLICT')
    return deepcopy(expected)


def position_partition(request,owner,position,approved_ids):
    """Classify one physical source position; never create a funding bucket."""
    binding=position.get('sgov_role_binding')
    if binding is None:return None
    if (position.get('ticker',position.get('asset_id'))!='SGOV' or position.get('asset_class')!='BOND'
        or not {'SGOV_BOND','SGOV_DRY'}<=set(approved_ids)
        or not isinstance(binding,dict) or not binding.get('instrument_key') or not binding.get('position_as_of_utc')):
        raise RoleSourceUnavailable('SGOV_ROLE_EXPLICIT_PHYSICAL_AND_APPROVED_ROLE_IDS_REQUIRED')
    selected=select(request,owner['account'],position['quantity'],instrument_key=binding['instrument_key'],
        position_as_of=binding['position_as_of_utc'])
    allocation=units(selected,position['quantity']);price=number(position['price'])
    if price<=0:raise RoleSourceUnavailable('SGOV_ROLE_POSITIVE_SOURCE_PRICE_REQUIRED')
    with localcontext() as numeric:
        numeric.prec=50
        physical=number(allocation['physical_quantity'])*price
        bond=number(allocation['bond_quantity'])*price;dry=physical-bond
        if dry!=number(allocation['dry_quantity'])*price:raise RoleSourceUnavailable('SGOV_ROLE_UNIT_MONEY_CONFLICT')
    receipt=dict(owner=deepcopy(owner),physical_position_id=position['position_id'],
        confirmed_position_role=selected,role_quantities=allocation,source_price=str(price),
        physical_market_value=str(physical),bond_market_value=str(bond),dry_market_value=str(dry),
        included_in_available_cash=False,cash_release_authorized=False)
    return [('SGOV_BOND','bond ETF',bond),('SGOV_DRY','cash',dry)],receipt
