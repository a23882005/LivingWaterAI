"""W9 append-only persistence reference with account binding, staging, CAS and recovery."""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass, replace
from hashlib import sha256
import json
from typing import Any, Mapping

class PersistenceConflict(RuntimeError): pass
class PersistenceIntegrityError(RuntimeError): pass

def _norm(x:Any)->Any:
    if is_dataclass(x): return _norm(asdict(x))
    if isinstance(x,Mapping): return {str(k):_norm(v) for k,v in sorted(x.items(),key=lambda kv:str(kv[0]))}
    if isinstance(x,(list,tuple)): return [_norm(v) for v in x]
    if hasattr(x,'value'): return _norm(x.value)
    if str(type(x)).endswith("Decimal'>"): return str(x)
    return x

def content_digest(payload:Any)->str:
    return sha256(json.dumps(_norm(payload),sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ImmutableSnapshot:
    snapshot_id:str; kind:str; run_id:str; payload:Any; digest:str; rule_version:str; contract_version:str; source_lineage:tuple[str,...]; created_at:str
    status:str='NOT_PUBLISHED'; supersedes_id:str|None=None; domain:str=''; broker:str=''; account:str=''
@dataclass(frozen=True,slots=True)
class LatestPointer:
    stream_key:str; snapshot_id:str; revision:int

class InMemorySnapshotRepository:
    """Deterministic reference adapter. Records are immutable; publication is explicit."""
    def __init__(self):
        self._records:dict[str,ImmutableSnapshot]={}; self._pointers:dict[str,LatestPointer]={}; self._idem:dict[str,tuple[str,str]]={}
    @staticmethod
    def _identity(domain:str,broker:str,account:str)->str:
        if not all((domain,broker,account)): raise PersistenceIntegrityError('EXECUTION_ACCOUNT_IDENTITY_REQUIRED')
        return f'{domain}|{broker}|{account}'
    def append(self, *, snapshot_id:str, kind:str, run_id:str, payload:Any, rule_version:str, contract_version:str,
        source_lineage:tuple[str,...], created_at:str, idempotency_key:str, domain:str, broker:str, account:str,
        supersedes_id:str|None=None, status:str='NOT_PUBLISHED')->ImmutableSnapshot:
        if not all((snapshot_id,kind,run_id,rule_version,contract_version,created_at,idempotency_key)): raise PersistenceIntegrityError('SNAPSHOT_REQUIRED_IDENTITY_MISSING')
        self._identity(domain,broker,account)
        if status not in ('NOT_PUBLISHED','PUBLISHED'): raise PersistenceIntegrityError('INVALID_SNAPSHOT_STATUS')
        dg=content_digest(payload)
        idem_dg=content_digest({'kind':kind,'run_id':run_id,'payload':payload,'rule_version':rule_version,'contract_version':contract_version,'source_lineage':source_lineage,'supersedes_id':supersedes_id,'domain':domain,'broker':broker,'account':account})
        prior=self._idem.get(idempotency_key)
        if prior:
            prior_id,prior_dg=prior
            if prior_dg!=idem_dg: raise PersistenceConflict('IDEMPOTENCY_PAYLOAD_CONFLICT')
            return self.get(prior_id)
        if snapshot_id in self._records: raise PersistenceConflict('SNAPSHOT_ID_CONFLICT')
        if supersedes_id is not None:
            old=self.get(supersedes_id)
            if (old.domain,old.broker,old.account)!=(domain,broker,account): raise PersistenceIntegrityError('SUPERSEDES_ACCOUNT_MISMATCH')
        rec=ImmutableSnapshot(snapshot_id,kind,run_id,payload,dg,rule_version,contract_version,tuple(source_lineage),created_at,status,supersedes_id,domain,broker,account)
        self._records[snapshot_id]=rec; self._idem[idempotency_key]=(snapshot_id,idem_dg); return rec
    def get(self,snapshot_id:str)->ImmutableSnapshot:
        try: rec=self._records[snapshot_id]
        except KeyError as e: raise PersistenceIntegrityError('SNAPSHOT_NOT_FOUND') from e
        if content_digest(rec.payload)!=rec.digest: raise PersistenceIntegrityError('SNAPSHOT_DIGEST_MISMATCH')
        return rec
    def publish(self,snapshot_id:str)->ImmutableSnapshot:
        rec=self.get(snapshot_id)
        if rec.status=='PUBLISHED': return rec
        if rec.status!='NOT_PUBLISHED': raise PersistenceIntegrityError('INVALID_SNAPSHOT_STATUS')
        pub=replace(rec,status='PUBLISHED'); self._records[snapshot_id]=pub; return pub
    def compare_and_swap_latest(self, *, stream_key:str, new_snapshot_id:str, expected_snapshot_id:str|None)->LatestPointer:
        rec=self.get(new_snapshot_id)
        expected_stream=self._identity(rec.domain,rec.broker,rec.account)
        if stream_key!=expected_stream: raise PersistenceIntegrityError('LATEST_POINTER_ACCOUNT_MISMATCH')
        if rec.status!='PUBLISHED': raise PersistenceIntegrityError('LATEST_MUST_REFERENCE_PUBLISHED')
        cur=self._pointers.get(stream_key); cur_id=cur.snapshot_id if cur else None
        if cur_id!=expected_snapshot_id: raise PersistenceConflict('LATEST_POINTER_CAS_CONFLICT')
        ptr=LatestPointer(stream_key,new_snapshot_id,(cur.revision+1 if cur else 1)); self._pointers[stream_key]=ptr; return ptr
    def latest(self,stream_key:str)->ImmutableSnapshot|None:
        ptr=self._pointers.get(stream_key); return None if ptr is None else self.get(ptr.snapshot_id)

class JsonlSnapshotRepository(InMemorySnapshotRepository):
    """File-backed append-only reference adapter with restart recovery."""
    def __init__(self, directory:str):
        from pathlib import Path
        self._dir=Path(directory); self._dir.mkdir(parents=True,exist_ok=True)
        self._history=self._dir/'snapshots.jsonl'; self._events=self._dir/'publication_events.jsonl'; self._pointer_file=self._dir/'latest_pointers.json'
        super().__init__(); self._recover()
    def _recover(self):
        if self._history.exists():
            for line in self._history.read_text(encoding='utf-8').splitlines():
                if not line.strip(): continue
                row=json.loads(line); clean={k:v for k,v in row.items() if not k.startswith('_')}; clean['source_lineage']=tuple(clean.get('source_lineage',()))
                rec=ImmutableSnapshot(**clean)
                if rec.snapshot_id in self._records: raise PersistenceIntegrityError('DUPLICATE_SNAPSHOT_ID_IN_HISTORY')
                if content_digest(rec.payload)!=rec.digest: raise PersistenceIntegrityError('SNAPSHOT_DIGEST_MISMATCH')
                self._records[rec.snapshot_id]=rec
                ik=row.get('_idempotency_key'); idg=row.get('_idempotency_digest')
                if ik and idg:
                    if ik in self._idem and self._idem[ik]!=(rec.snapshot_id,idg): raise PersistenceIntegrityError('DUPLICATE_IDEMPOTENCY_KEY_IN_HISTORY')
                    self._idem[ik]=(rec.snapshot_id,idg)
        if self._events.exists():
            for line in self._events.read_text(encoding='utf-8').splitlines():
                if not line.strip(): continue
                ev=json.loads(line); sid=ev.get('snapshot_id')
                if ev.get('event')!='PUBLISH' or sid not in self._records: raise PersistenceIntegrityError('INVALID_PUBLICATION_EVENT')
                self._records[sid]=replace(self._records[sid],status='PUBLISHED')
        if self._pointer_file.exists():
            raw=json.loads(self._pointer_file.read_text(encoding='utf-8'))
            for k,v in raw.items(): self._pointers[k]=LatestPointer(k,v['snapshot_id'],int(v['revision']))
            for p in self._pointers.values():
                rec=self.get(p.snapshot_id)
                if rec.status!='PUBLISHED': raise PersistenceIntegrityError('LATEST_POINTS_TO_UNPUBLISHED')
                if p.stream_key!=self._identity(rec.domain,rec.broker,rec.account): raise PersistenceIntegrityError('LATEST_POINTER_ACCOUNT_MISMATCH')
    def append(self, **kwargs):
        key=kwargs.get('idempotency_key'); before=set(self._records); rec=super().append(**kwargs)
        if rec.snapshot_id not in before:
            row=_norm(rec); row['_idempotency_key']=key; row['_idempotency_digest']=self._idem[key][1]
            with self._history.open('a',encoding='utf-8') as fh:
                fh.write(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)+'\n'); fh.flush()
                import os; os.fsync(fh.fileno())
        return rec
    def publish(self,snapshot_id:str)->ImmutableSnapshot:
        before=self.get(snapshot_id)
        rec=super().publish(snapshot_id)
        if before.status!='PUBLISHED':
            with self._events.open('a',encoding='utf-8') as fh:
                fh.write(json.dumps({'event':'PUBLISH','snapshot_id':snapshot_id},sort_keys=True,separators=(',',':'))+'\n'); fh.flush()
                import os; os.fsync(fh.fileno())
        return rec
    def compare_and_swap_latest(self, **kwargs):
        # Validate CAS and candidate before mutating the durable pointer.
        stream_key=kwargs['stream_key']; new_snapshot_id=kwargs['new_snapshot_id']; expected_snapshot_id=kwargs.get('expected_snapshot_id')
        rec=self.get(new_snapshot_id)
        if stream_key!=self._identity(rec.domain,rec.broker,rec.account): raise PersistenceIntegrityError('LATEST_POINTER_ACCOUNT_MISMATCH')
        if rec.status!='PUBLISHED': raise PersistenceIntegrityError('LATEST_MUST_REFERENCE_PUBLISHED')
        cur=self._pointers.get(stream_key); cur_id=cur.snapshot_id if cur else None
        if cur_id!=expected_snapshot_id: raise PersistenceConflict('LATEST_POINTER_CAS_CONFLICT')
        ptr=LatestPointer(stream_key,new_snapshot_id,(cur.revision+1 if cur else 1))
        raw={k:{'snapshot_id':v.snapshot_id,'revision':v.revision} for k,v in self._pointers.items()}; raw[stream_key]={'snapshot_id':ptr.snapshot_id,'revision':ptr.revision}
        tmp=self._pointer_file.with_suffix('.tmp'); tmp.write_text(json.dumps(raw,sort_keys=True,separators=(',',':')),encoding='utf-8')
        import os
        with tmp.open('r+',encoding='utf-8') as fh: os.fsync(fh.fileno())
        os.replace(tmp,self._pointer_file); self._pointers[stream_key]=ptr
        return ptr
