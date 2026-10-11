"""W9 typed integration ports/adapters. Adapters transport/validate; they own no V82 business rules."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from .enums import FundingDomain
from .models import ExecutionAccountRef, V82RuntimeInput, V82RuntimeOutput

class PortContractError(ValueError): pass
class V70Port(Protocol):
    def load_snapshot(self, *, run_id:str, snapshot_id:str)->Mapping[str,Any]: ...
class MentorInputPort(Protocol):
    def load_runtime_input(self, *, run_id:str)->V82RuntimeInput: ...
class PersistencePort(Protocol):
    def append(self, **kwargs:Any)->Any: ...
    def compare_and_swap_latest(self, **kwargs:Any)->Any: ...
class OutputPort(Protocol):
    def publish(self, output:V82RuntimeOutput)->None: ...
class BrokerPositionPort(Protocol):
    def confirmed_position(self, account:ExecutionAccountRef, asset_id:str)->Any: ...
class BrokerOrderPort(Protocol):
    def submit_intent(self, account:ExecutionAccountRef, order_intent:Any)->Any: ...
class ExecutionConstraintPort(Protocol):
    def constraints(self, account:ExecutionAccountRef, asset_id:str)->Mapping[str,Any]: ...
class MarketDataPort(Protocol):
    def facts(self, asset_id:str)->Mapping[str,Any]: ...
class EventNewsPort(Protocol):
    def evidence(self, asset_id:str)->Mapping[str,Any]: ...
class C7FundingPort(Protocol):
    def context(self, *, run_id:str)->Mapping[str,Any]: ...

@dataclass(frozen=True,slots=True)
class AccountIdentity:
    domain:str; broker:str; account:str

def require_same_account(expected:ExecutionAccountRef, payload:Mapping[str,Any])->None:
    try: domain=str(payload['domain']); broker=str(payload['broker']); account=str(payload['account'])
    except (KeyError,TypeError) as e: raise PortContractError('ACCOUNT_IDENTITY_MISSING') from e
    exp_domain=expected.domain.value if hasattr(expected.domain,'value') else str(expected.domain)
    if (domain,broker,account)!=(exp_domain,expected.broker,expected.account): raise PortContractError('ACCOUNT_IDENTITY_MISMATCH')

def require_contract(payload:Mapping[str,Any], *, contract_name:str, contract_version:str)->None:
    if payload.get('contract_name')!=contract_name or payload.get('contract_version')!=contract_version:
        raise PortContractError('CONTRACT_NAME_OR_VERSION_MISMATCH')

def reject_v75_equity_funding(payload:Mapping[str,Any])->None:
    forbidden={'bond_executable_budget','SGOV_BOND_BUCKET','SGOV_DRY_POWDER_BUCKET','bank_cash'}
    if any(k in payload and payload[k] not in (None,0,'0') for k in forbidden): raise PortContractError('FORBIDDEN_V75_OR_NON_EQUITY_FUNDING')
