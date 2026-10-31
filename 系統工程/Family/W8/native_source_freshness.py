"""Use the existing publication contract; unknowns carry concrete reasons."""
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
import importlib.util,sys
from family_input import digest


def build(root,request,report):
    path=Path(root)/'scripts/validate_v703_publication.py'
    if str(Path(root).resolve()) not in sys.path:sys.path.insert(0,str(Path(root).resolve()))
    spec=importlib.util.spec_from_file_location('family_v75_publication_check',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    at=datetime.fromisoformat(request['evaluation_at'].replace('Z','+00:00'))
    macro=request['macro_snapshot'];state='UNKNOWN';reason=None
    try:
        module.validate_current_contract(macro['payload'],at)
        if macro['payload'].get('verification',{}).get('ready') is True:
            state='FRESH'
        else:reason='V70_VERIFICATION_NOT_READY'
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        reason=str(error)
        try:
            made=datetime.fromisoformat(macro['payload']['asOf'].replace('Z','+00:00'))
            if made.utcoffset() is not None and at-made>=timedelta(hours=26):state='STALE'
        except (KeyError,ValueError,TypeError):pass
    markets=[row['market'] for row in report['analysis_result']['positions']
        if row['native_product_identity'].get('engine_route')=='V75_PREDICATES' and row.get('market')]
    markets+=list(report.get('bond_target_market_observations',{}).values())
    target_symbols={r.get('ticker') for r in request.get('confirmed_target',{}).get('payload',{}).get('draft',{}).get('target_lines',[])}
    held_symbols={r['symbol'] for r in report['analysis_result']['positions']
        if r['native_product_identity'].get('engine_route')=='V75_PREDICATES' and r.get('symbol')}
    scope=target_symbols|held_symbols
    if scope:markets=[m for m in markets if m['symbol'] in scope]
    def qualified(market):
        contract=market.get('qualified_bond_market')
        if not isinstance(contract,dict):return False
        return (contract.get('schema_version')=='Family.W8.QualifiedBondMarket.v1'
            and contract.get('digest')==digest({k:v for k,v in contract.items() if k!='digest'})
            and contract==report.get('v75_macro_inputs',{}).get('qualified_bond_markets',{}).get(market['symbol'])
            and contract.get('eligible') is True and contract.get('status')=='FRESH'
            and contract.get('scope')=='COMPLETED_RTH_BOND_MARKET_SNAPSHOT_ONLY'
            and contract.get('source_sha256')==market.get('source_sha256')
            and contract.get('observed_date')==market.get('observed_date'))
    missing=[{'symbol':m['symbol'],'observed_date':m.get('observed_date'),
        'source_sha256':m.get('source_sha256'),
        'reason':'CANONICAL_IDENTITY_CLOSE_AND_SESSION_ATTESTATION_REQUIRED'}
        for m in markets if not qualified(m)]
    return {'schema_version':'Family.W8.NativeSourceFreshness.v1',
        'v70':{'state':state,'reason':reason,'feed_as_of':macro['payload'].get('asOf'),
            'policy_source':'scripts/validate_v703_publication.py',
            'policy_sha256':sha256(path.read_bytes()).hexdigest(),
            'contract':'EXISTING_V70_26_HOUR_AND_POLICY_COMPONENT_CONTRACT'},
        'market':{'state':'FRESH' if markets and not missing else 'UNKNOWN',
            'reason':None if markets and not missing else 'MARKET_CONTRACT_ATTESTATION_NOT_BOUND',
            'missing_attestations':missing,
            'scope':'APPROVED_AND_HELD_BOND_SNAPSHOTS__ADVISORY_CANDIDATES_CHECKED_SEPARATELY',
            'source_recency_is_not_canonical_market_attestation':True}}


def validate(root,request,report):
    if report.get('native_source_freshness')!=build(root,request,report):
        raise PermissionError('NATIVE_SOURCE_FRESHNESS_REPLAY_MISMATCH')
