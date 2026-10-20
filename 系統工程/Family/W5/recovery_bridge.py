"""W5 pure-computation replay seam over the existing W2 staging journal.

Not a production store. The trusted caller supplies W2 recovery, validation,
and a side-effect-free compute function. W7 owns durable identity/version CAS.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math
from threading import RLock


class RecoveryError(ValueError):
    pass


def _compute_outcome(compute,request):
    # Distinguish an engine-raised TimeoutError from actual elapsed timeout.
    try:return True,compute(request)
    except Exception as error:return False,error


def encode(value):
    """Tagged v1 encoding: preserve Decimal, numeric types and array order."""
    if value is None:return ['null']
    if isinstance(value,bool):return ['bool',value]
    if isinstance(value,str):return ['str',value]
    if isinstance(value,int):return ['int',str(value)]
    if isinstance(value,Decimal):
        if not value.is_finite():raise RecoveryError('NONFINITE_INPUT')
        return ['decimal',str(value)]
    if isinstance(value,float):
        if not math.isfinite(value):raise RecoveryError('NONFINITE_INPUT')
        return ['float',value.hex()]
    if isinstance(value,list):return ['list',[encode(x) for x in value]]
    if isinstance(value,dict) and all(isinstance(k,str) for k in value):
        return ['dict',[[k,encode(value[k])] for k in sorted(value)]]
    raise RecoveryError('UNSUPPORTED_INPUT_TYPE')


def input_digest(request):
    wire=['Family.W5.digest.v1',encode(request)]
    return hashlib.sha256(json.dumps(wire,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class StagingAnalysisStore:
    def __init__(self,w2_recovery):
        self._w2=w2_recovery
        self._entries={}
        self._lock=RLock()

    def snapshot(self):
        with self._lock:
            return {'storage_scope':'ISOLATED_TEST_STAGING','digest_version':'Family.W5.digest.v1',
                    'entries':[encode(deepcopy(v)) for _,v in sorted(self._entries.items())]}

    def analyze(self,request,*,validate,compute,timeout_seconds=30):
        if isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,(int,float)) or not math.isfinite(timeout_seconds) or timeout_seconds<=0:
            raise RecoveryError('INVALID_TIMEOUT')
        frozen=deepcopy(request)
        for name in ('client_id','request_id','run_id'):
            if not isinstance(frozen.get(name),str) or not frozen[name].strip():
                raise RecoveryError('IDENTITY_REQUIRED:'+name)
        key=(frozen['client_id'],frozen['request_id'])
        fingerprint=input_digest(frozen)
        # One staging lock serializes competing requests and publication.
        # validate must read the current trusted permission/version provider.
        with self._lock:
            validate(deepcopy(frozen))
            entry=self._entries.get(key)
            if entry is not None and entry['input_digest']!=fingerprint:
                raise RecoveryError('IDEMPOTENCY_CONFLICT')
            if entry is None:
                state=self._w2.new_test_state(project_id='Family.W5',client_id=key[0],
                    run_id=frozen['run_id'],version=1,checkpoint_id='CP-1',state_payload={})
                event={'request_id':key[1],'run_id':frozen['run_id'],'project_id':'Family.W5',
                    'client_id':key[0],'expected_version':1,'confirmation_id':key[1],
                    'checkpoint_id':'CP-1','authorized':True,'action':'STAGING_CONFIRMATION',
                    'payload':{'input_digest':fingerprint,'request':encode(frozen)}}
                accepted=self._w2.apply_event(state,event)
                if accepted['status']!='APPLIED_IN_TEST_STAGING':
                    raise RecoveryError('W2_JOURNAL_REJECTED:'+str(accepted['issue_codes']))
                entry={'client_id':key[0],'request_id':key[1],'input_digest':fingerprint,
                       'journal':state,'status':'REGISTERED','result':None,
                       'publication_count':0,'attempts':0,'timeouts':0}
                self._entries[key]=entry
            if entry['status']=='COMPLETE':
                validate(deepcopy(frozen))
                return {'status':'REPLAYED','input_digest':fingerprint,'result':deepcopy(entry['result'])}
            for attempt in range(2):
                validate(deepcopy(frozen))
                executor=ThreadPoolExecutor(max_workers=1)
                entry['attempts']+=1
                future=executor.submit(_compute_outcome,compute,deepcopy(frozen))
                try:
                    succeeded,result=future.result(timeout=timeout_seconds)
                except FutureTimeout:
                    # No callback can publish; late computation owns no store ref.
                    future.cancel()
                    entry['timeouts']+=1
                    entry['status']='TIMED_OUT'
                    if attempt==1:raise RecoveryError('COMPUTATION_TIMEOUT')
                    continue
                except Exception:
                    entry['status']='ERROR'
                    raise
                finally:
                    executor.shutdown(wait=False,cancel_futures=True)
                if not succeeded:
                    entry['status']='ERROR'
                    raise result
                validate(deepcopy(frozen))
                if not isinstance(result,dict) or result.get('trade_action')!='NO_TRADE':
                    raise RecoveryError('NO_TRADE_RESULT_REQUIRED')
                encode(result)  # Refuse nonserializable/nonfinite recovery state.
                entry['result']=deepcopy(result)
                entry['status']='COMPLETE'
                entry['publication_count']+=1
                return {'status':'COMPUTED','input_digest':fingerprint,'result':deepcopy(result)}
