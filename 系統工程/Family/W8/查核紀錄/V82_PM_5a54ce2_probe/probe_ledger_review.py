import pathlib,sys,types,json,tempfile
from decimal import Decimal
r=(pathlib.Path(sys.argv[1])/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime' if len(sys.argv)>1 else pathlib.Path(__file__).parent/'source/系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime')
# Isolated pure-function probe: bypass only package __init__ side-effect imports.
# This does not run or substitute any funding/JSON-schema validation or E2E.
pkg=types.ModuleType('livingwater_v82_runtime');pkg.__path__=[str(r)];sys.modules['livingwater_v82_runtime']=pkg
from livingwater_v82_runtime.daily_slice import maturity,speed,open_cycle,cycle_room,update_intent,CycleLedgerStore
owner={'client_id':'SYNTHETIC','broker':'SYNTHETIC','account':'A','currency':'USD','funding_domain':'US_DIRECT'}
at='2026-10-30T20:00:00Z';session='2026-10-30'
def rates(n):
 return speed(mode='Left Overweight',maturity_result=maturity([{'id':'M'+str(i+1),'truth':'TRUE' if i<n else 'FALSE'} for i in range(8)]),credit_level=0,core_etf='TRUE',high_beta='FALSE',macro_pressure='FALSE',extreme_valuation='OFF')
s=rates(3)
def cycle(gap):return open_cycle(owner=owner,session_id=session,exchange='SYNTHETIC_X',asset_id='SYNTHETIC',opened_at=at,gap=gap,speed_result=s,permission=True,exposure_reconciled=True,session_open=True)
def room(c):return cycle_room(c,speed_result=s,permission=True,trend_allowed=True,session_id=session,session_open=True)
def event(c,eid,state,filled,remaining,release=False):
 return update_intent(c,event_id=eid,intent_id='I1',state=state,filled_amount=filled,remaining_amount=remaining,
  receipt={'owner':owner,'asset_id':'SYNTHETIC','source_reference':'SYNTHETIC_RECEIPT','source_hash':'SYNTHETIC_HASH','as_of':at,'available_at':at,'release_confirmed':release},
  evaluation_at=at,speed_result=s,permission=True,trend_allowed=True,session_id=session,session_open=True)
c=cycle('100');c=event(c,'PLAN','PLANNED','0','25');c=event(c,'OPEN','OPEN','0','25')
before=room(c)
pending_keep=event(c,'PENDING_KEEP','CANCEL_PENDING','0','25')
try:
 pending_drop=event(c,'PENDING_DROP','CANCEL_PENDING','0','0')
 drop={'accepted':True,'room':room(pending_drop)}
 with tempfile.TemporaryDirectory() as d:
  store=CycleLedgerStore(pathlib.Path(d)/'planning.sqlite',create=True);store.save(c,expected_revision=None)
  store.save(pending_drop,expected_revision=c['revision']);drop['persisted']=store.get(c['slice_cycle_id'])==pending_drop
except ValueError as e:drop={'accepted':False,'error':str(e)}
receipt={'scope':'ISOLATED_SYNTHETIC_NATIVE_COMPONENT_PROBE','head':'5a54ce25c1dedc39c781aa2e6acd9f867b581d56',
 'mature_150000_B0':cycle('150000')['B0'],'immature_150000_B0':open_cycle(owner=owner,session_id=session,exchange='SYNTHETIC_X',asset_id='SYNTHETIC',opened_at=at,gap='150000',speed_result=rates(0),permission=True,exposure_reconciled=True,session_open=True)['B0'],
 'before_pending':before,'pending_unchanged_room':room(pending_keep),'pending_zero_remaining_without_release':drop,
 'expected':'Cancellation/replacement pending without confirmed release must retain prior unfilled commitment, adjusting only verified fills; malformed shrink must be rejected or preserve that commitment.',
 'real_orders_or_private_db_changed':False}
pathlib.Path(__file__).with_name('ledger_review_results.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print(json.dumps(receipt,ensure_ascii=False,indent=2))
