"""Reuse original observations only for identical inputs and unchanged bytes.

This cache is created inside one Member request. It never accepts serialized
outputs, crosses a member/run/cutoff, changes a producer or upgrades eligibility.
"""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import RLock
from contextlib import contextmanager
from contextvars import ContextVar
import json

_ACTIVE=ContextVar('member_original_arithmetic_cache',default=None)


def active_cache():return _ACTIVE.get()


def normalized(value):
    if isinstance(value,Path):return str(value.resolve())
    if isinstance(value,Decimal):return {'decimal_value':str(value)}
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalized(v) for v in value]
    if isinstance(value,(set,frozenset)):return sorted((normalized(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    return value


def source_bytes(arguments):
    root=Path(arguments['repo_root']).resolve();paths=set()
    for folder in (root/'data/market_history/global',arguments.get('alternative_source_dir')):
        if folder is not None:
            directory=Path(folder)
            paths.update(p.resolve() for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in ('.json','.csv'))
    rules=arguments.get('formal_rule_source')
    if rules is not None:paths.add(Path(rules['local_path']).resolve())
    return [{'path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]


class SameRunMarketCache:
    def __init__(self):self._values={};self._arithmetic={};self._lock=RLock()

    @contextmanager
    def activate(self):
        token=_ACTIVE.set(self)
        try:yield self
        finally:_ACTIVE.reset(token)

    def memo(self,name,arguments,builder,*,repo_root):
        # Raw files/receipts are still re-read and qualified by their original
        # callers. Only deterministic arithmetic on these exact values is reused.
        from verify_dependencies import verify
        verify(repo_root)
        locks=Path(repo_root)/'系統工程/Family/W5'
        versions={n:sha256((locks/n).read_bytes()).hexdigest() for n in ('source_lock.json','dependency_lock.json')}
        try:key=sha256(json.dumps({'function':name,'inputs':normalized(arguments),'versions':versions},
            ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        except (TypeError,ValueError):return builder()  # Original validation owns invalid input semantics.
        with self._lock:
            if key not in self._arithmetic:self._arithmetic[key]=deepcopy(builder())
            return deepcopy(self._arithmetic[key])

    def build(self,builder,arguments):
        with self._lock:
            before=source_bytes(arguments)
            key=sha256(json.dumps({'inputs':normalized(arguments),'files':before},ensure_ascii=False,
                sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            if key not in self._values:
                result=builder(**arguments)
                if source_bytes(arguments)!=before:raise PermissionError('MEMBER_MARKET_SOURCE_CHANGED_DURING_ORIGINAL_BUILD')
                self._values[key]=deepcopy(result)
            return deepcopy(self._values[key])
