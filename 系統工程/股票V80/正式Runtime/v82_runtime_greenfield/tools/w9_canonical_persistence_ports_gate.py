from decimal import Decimal
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from livingwater_v82_runtime.canonical_output import *
from livingwater_v82_runtime.persistence import *
from livingwater_v82_runtime.ports import *
from livingwater_v82_runtime.models import ExecutionAccountRef
from livingwater_v82_runtime.enums import FundingDomain
checks=[]
def ck(name,fn):
    try: fn(); checks.append((name,True,''))
    except Exception as e: checks.append((name,False,f'{type(e).__name__}:{e}'))
def raises(exc,fn,contains=None):
    try: fn()
    except exc as e:
        if contains and contains not in str(e): raise AssertionError(str(e))
        return
    raise AssertionError('did not raise')
vals={k:{'canonical':k} for k in CANONICAL_FIELD_NAMES}; vals['order_submission_plan']={'should_place_order':False,'order_type':None,'limit_price':None,'quantity':Decimal('0'),'time_in_force':None,'scheduling_mode':None,'broker_or_adapter_constraints':None,'order_intent_id':None}
a=assemble_canonical_analysis(values=vals,run_id='r1',rule_version='rv1'); v=project_formal_execution_view(a)
ck('CANONICAL_EXACTLY_49',lambda: (_ for _ in ()).throw(AssertionError()) if len(a.fields)!=49 else None)
ck('CANONICAL_ORDER_EXACT',lambda: (_ for _ in ()).throw(AssertionError()) if tuple(a.fields)!=CANONICAL_FIELD_NAMES else None)
ck('FORMAL_EXACTLY_13',lambda: (_ for _ in ()).throw(AssertionError()) if len(v.fields)!=13 else None)
ck('FORMAL_ORDER_EXACT',lambda: (_ for _ in ()).throw(AssertionError()) if tuple(v.fields)!=FORMAL_OUTPUT_NAMES else None)
for n in ('今日特殊分類','目前部署階段','目標與完成率','今日動作','執行比例','執行金額','執行股數','執行價格','成交後完成率','是否掛單','掛單方式','取消條件','下一次重新評估條件'):
    ck('MAP_'+n,lambda n=n: (_ for _ in ()).throw(AssertionError()) if n not in v.fields else None)
ck('MISSING_FIELD_FAIL',lambda: raises(CanonicalAssemblyError,lambda: assemble_canonical_analysis(values={k:v for k,v in vals.items() if k!='latest_price'},run_id='r1',rule_version='rv1'),'MISMATCH'))
ck('EXTRA_FIELD_FAIL',lambda: raises(CanonicalAssemblyError,lambda: assemble_canonical_analysis(values={**vals,'x':1},run_id='r1',rule_version='rv1'),'MISMATCH'))
ck('RUN_LINEAGE_PASS',lambda: validate_run_lineage(run_id='r1',upstream_v70_run_id='r1',c7_funding_run_id='r1'))
ck('RUN_LINEAGE_FAIL',lambda: raises(CanonicalAssemblyError,lambda:validate_run_lineage(run_id='r1',upstream_v70_run_id='r2',c7_funding_run_id='r1'),'RUN_ID_MISMATCH'))
out=build_runtime_output(analysis=a,run_id='r1',v82_snapshot_id='v82s1',upstream_v70_snapshot_id='v70s1',asset_id='QQQ',rule_version='rv1',contract_name='V82',contract_version='c1',data_as_of='t0',evaluated_at='t1',source_lineage=('v70s1','c7s1'),output_status='KNOWN')
ck('OUTPUT_49',lambda: (_ for _ in ()).throw(AssertionError()) if len(out.canonical_analysis)!=49 else None)
ck('OUTPUT_13',lambda: (_ for _ in ()).throw(AssertionError()) if len(out.fields_1_to_13)!=13 else None)
ck('OUTPUT_IDS',lambda: (_ for _ in ()).throw(AssertionError()) if (out.run_id,out.v82_snapshot_id,out.upstream_v70_snapshot_id)!=('r1','v82s1','v70s1') else None)
r=InMemorySnapshotRepository(); rec=r.append(snapshot_id='s1',kind='CANONICAL',run_id='r1',payload=out,rule_version='rv1',contract_version='c1',source_lineage=('v70s1','c7s1'),created_at='t1',idempotency_key='idem1',domain='US_BROKER',broker='IB',account='A1')
ck('APPEND_READ',lambda: (_ for _ in ()).throw(AssertionError()) if r.get('s1').digest!=rec.digest else None)
ck('IDEMPOTENT_SAME',lambda: (_ for _ in ()).throw(AssertionError()) if r.append(snapshot_id='ignored',kind='CANONICAL',run_id='r1',payload=out,rule_version='rv1',contract_version='c1',source_lineage=('v70s1','c7s1'),created_at='t2',idempotency_key='idem1',domain='US_BROKER',broker='IB',account='A1').snapshot_id!='s1' else None)
ck('IDEMPOTENT_CONFLICT',lambda: raises(PersistenceConflict,lambda:r.append(snapshot_id='s2',kind='CANONICAL',run_id='r2',payload=out,rule_version='rv1',contract_version='c1',source_lineage=('v70s1','c7s1'),created_at='t2',idempotency_key='idem1',domain='US_BROKER',broker='IB',account='A1'),'IDEMPOTENCY'))
ck('STAGED_NOT_LATEST',lambda: raises(PersistenceIntegrityError,lambda:r.compare_and_swap_latest(stream_key='US_BROKER|IB|A1',new_snapshot_id='s1',expected_snapshot_id=None),'PUBLISHED'))
ck('PUBLISH',lambda:r.publish('s1'))
ck('CAS_FIRST',lambda:r.compare_and_swap_latest(stream_key='US_BROKER|IB|A1',new_snapshot_id='s1',expected_snapshot_id=None))
ck('CAS_CONFLICT',lambda:raises(PersistenceConflict,lambda:r.compare_and_swap_latest(stream_key='US_BROKER|IB|A1',new_snapshot_id='s1',expected_snapshot_id=None),'CAS_CONFLICT'))
ck('LATEST_READBACK',lambda: (_ for _ in ()).throw(AssertionError()) if r.latest('US_BROKER|IB|A1').snapshot_id!='s1' else None)
r.append(snapshot_id='s3',kind='CANONICAL',run_id='r1',payload={'corrected':True},rule_version='rv1',contract_version='c1',source_lineage=('x',),created_at='t3',idempotency_key='idem3',domain='US_BROKER',broker='IB',account='A1',supersedes_id='s1')
ck('SUPERSEDES_APPEND_ONLY',lambda: (_ for _ in ()).throw(AssertionError()) if r.get('s1').snapshot_id!='s1' or r.get('s3').supersedes_id!='s1' else None)
acct=ExecutionAccountRef(FundingDomain.US_BROKER,'IB','A1')
ck('PORT_ACCOUNT_PASS',lambda:require_same_account(acct,{'domain':'US_BROKER','broker':'IB','account':'A1'}))
ck('PORT_ACCOUNT_FAIL',lambda:raises(PortContractError,lambda:require_same_account(acct,{'domain':'US_BROKER','broker':'IB','account':'A2'}),'MISMATCH'))
ck('PORT_CONTRACT_PASS',lambda:require_contract({'contract_name':'C7','contract_version':'1'},contract_name='C7',contract_version='1'))
ck('PORT_CONTRACT_FAIL',lambda:raises(PortContractError,lambda:require_contract({'contract_name':'C7','contract_version':'2'},contract_name='C7',contract_version='1'),'MISMATCH'))
ck('V75_BOUNDARY_PASS',lambda:reject_v75_equity_funding({'equity_executable_budget':100}))
ck('V75_BOUNDARY_FAIL',lambda:raises(PortContractError,lambda:reject_v75_equity_funding({'bond_executable_budget':1}),'FORBIDDEN'))

ck('ACCOUNT_REQUIRED_FAIL',lambda: raises(PersistenceIntegrityError,lambda:r.append(snapshot_id='badacct',kind='CANONICAL',run_id='r1',payload={'x':1},rule_version='rv1',contract_version='c1',source_lineage=('x',),created_at='t',idempotency_key='badacct',domain='',broker='IB',account='A1'),'ACCOUNT_IDENTITY'))
ck('POINTER_ACCOUNT_MISMATCH',lambda: raises(PersistenceIntegrityError,lambda:r.compare_and_swap_latest(stream_key='US_BROKER|IB|OTHER',new_snapshot_id='s1',expected_snapshot_id=None),'ACCOUNT_MISMATCH'))
ck('SUPERSEDES_ACCOUNT_MISMATCH',lambda: raises(PersistenceIntegrityError,lambda:r.append(snapshot_id='badsub',kind='CANONICAL',run_id='r1',payload={'x':2},rule_version='rv1',contract_version='c1',source_lineage=('x',),created_at='t',idempotency_key='badsub',domain='US_BROKER',broker='IB',account='A2',supersedes_id='s1'),'SUPERSEDES_ACCOUNT'))

import tempfile
with tempfile.TemporaryDirectory() as td:
    fr=JsonlSnapshotRepository(td); fr.append(snapshot_id='fs1',kind='CANONICAL',run_id='r1',payload={'x':1},rule_version='rv1',contract_version='c1',source_lineage=('x',),created_at='t',idempotency_key='fid1',domain='US_BROKER',broker='IB',account='A1'); fr.publish('fs1'); fr.compare_and_swap_latest(stream_key='US_BROKER|IB|A1',new_snapshot_id='fs1',expected_snapshot_id=None)
    fr2=JsonlSnapshotRepository(td)
    ck('FILE_RESTART_RECOVERY',lambda: (_ for _ in ()).throw(AssertionError()) if fr2.latest('US_BROKER|IB|A1').snapshot_id!='fs1' else None)
    ck('FILE_RESTART_IDEMPOTENCY',lambda: (_ for _ in ()).throw(AssertionError()) if fr2.append(snapshot_id='ignored',kind='CANONICAL',run_id='r1',payload={'x':1},rule_version='rv1',contract_version='c1',source_lineage=('x',),created_at='t2',idempotency_key='fid1',domain='US_BROKER',broker='IB',account='A1').snapshot_id!='fs1' else None)

passed=sum(x[1] for x in checks); print(f'{passed}/{len(checks)} PASS' if passed==len(checks) else f'{passed}/{len(checks)} FAIL')
for x in checks:
    if not x[1]: print(x)
if passed!=len(checks): raise SystemExit(1)
